"""JobSpy aggregator adapter — deterministic DISCOVER source for manage.py search.

Fetches structured postings via python-jobspy (LinkedIn, Indeed, Google Jobs, …)
and normalizes each row to ``opportunity_artifact/v1`` for the Job Researcher prompt.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "search_jobspy/v1"
DEFAULT_JOBSPY_SITES = ("linkedin", "indeed", "google")
SUPPORTED_JOBSPY_SITES = frozenset(
    {
        "linkedin",
        "indeed",
        "google",
        "zip_recruiter",
        "glassdoor",
        "bayt",
        "naukri",
        "bdjobs",
    }
)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_opportunity_id(apply_url: str) -> str:
    digest = hashlib.sha256(apply_url.strip().encode()).hexdigest()[:16]
    return f"opp:{digest}"


def make_dedupe_key(company: str, title: str, apply_url: str) -> str:
    return f"{company.strip()}|{title.strip()}|{apply_url.strip()}"


def _clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _stringify_job_type(job_type: Any) -> str | None:
    if job_type is None:
        return None
    if isinstance(job_type, list):
        parts = [str(item.value if hasattr(item, "value") else item) for item in job_type if item]
        return ", ".join(parts) if parts else None
    return str(job_type)


def normalize_jobspy_row(row: dict[str, Any], *, fetched_at: str | None = None) -> dict[str, Any] | None:
    """Map one JobSpy dataframe row to ``opportunity_artifact/v1``."""
    title = str(row.get("title") or "").strip()
    company = str(row.get("company") or "").strip()
    job_url = str(row.get("job_url") or "").strip()
    job_url_direct = str(row.get("job_url_direct") or "").strip()
    apply_url = job_url_direct or job_url

    if not title or not company or not apply_url:
        return None

    site = str(row.get("site") or "aggregator").strip().lower()
    location = str(row.get("location") or "").strip() or None
    description = row.get("description")
    if description is not None:
        description = str(description).strip() or None

    is_remote = row.get("is_remote")
    if is_remote is True and location:
        location = f"{location} (remote)"
    elif is_remote is True:
        location = "Remote"

    when = fetched_at or _now_iso()
    date_posted = _clean_scalar(row.get("date_posted"))

    provenance: list[dict[str, Any]] = [
        {
            "kind": "aggregator_fetch",
            "platform": site,
            "url": job_url or apply_url,
            "status": "ok",
            "at": when,
        }
    ]
    if job_url_direct and job_url_direct != job_url:
        provenance.append(
            {
                "kind": "fetched",
                "url": job_url_direct,
                "status": "ok",
                "at": when,
            }
        )

    notes: list[str] = []
    job_level = row.get("job_level")
    if job_level:
        notes.append(f"job_level={_clean_scalar(job_level)}")
    if date_posted:
        notes.append(f"date_posted={date_posted}")
    min_amount = _clean_scalar(row.get("min_amount"))
    max_amount = _clean_scalar(row.get("max_amount"))
    if min_amount or max_amount:
        currency = row.get("currency") or "USD"
        notes.append(f"salary={min_amount}-{max_amount} {currency}")

    return {
        "schema": "opportunity_artifact/v1",
        "opportunity_id": make_opportunity_id(apply_url),
        "source_kind": "aggregator",
        "source_url": job_url or apply_url,
        "apply_url": apply_url,
        "canonical_url": job_url_direct or None,
        "title": title,
        "company": company,
        "location": location,
        "employment_type": _stringify_job_type(row.get("job_type")),
        "job_description": description or "",
        "recruiter_message": None,
        "provenance": provenance,
        "discovered_at": when,
        "dedupe_key": make_dedupe_key(company, title, apply_url),
        "researcher_notes": "; ".join(notes),
        "aggregator": {
            "platform": site,
            "jobspy_id": _clean_scalar(row.get("id")),
            "date_posted": date_posted,
        },
    }


def parse_site_list(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return list(DEFAULT_JOBSPY_SITES)
    sites = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unknown = [s for s in sites if s not in SUPPORTED_JOBSPY_SITES]
    if unknown:
        raise ValueError(
            f"unsupported jobspy site(s): {', '.join(unknown)} "
            f"(supported: {', '.join(sorted(SUPPORTED_JOBSPY_SITES))})"
        )
    return sites


def fetch_jobspy_opportunities(
    *,
    query: str,
    sites: list[str] | None = None,
    location: str | None = None,
    posted_within_days: int = 10,
    results_wanted: int = 25,
    linkedin_fetch_description: bool = False,
    proxies: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Call JobSpy and return normalized opportunities plus non-fatal error strings."""
    sites = sites or list(DEFAULT_JOBSPY_SITES)
    errors: list[str] = []
    fetched_at = _now_iso()

    try:
        from jobspy import scrape_jobs
    except ImportError:
        return [], ["python-jobspy not installed — pip install -r requirements.txt"]

    hours_old = max(1, int(posted_within_days)) * 24

    try:
        frame = scrape_jobs(
            site_name=sites,
            search_term=query,
            location=location,
            results_wanted=max(1, int(results_wanted)),
            hours_old=hours_old,
            linkedin_fetch_description=linkedin_fetch_description,
            proxies=proxies,
            verbose=0,
        )
    except Exception as exc:  # noqa: BLE001 — surface aggregator failure without aborting search
        return [], [f"jobspy scrape failed: {exc}"]

    if frame is None or frame.empty:
        return [], ["jobspy returned no rows (rate limit or no matches)"]

    opportunities: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in frame.to_dict(orient="records"):
        cleaned = {key: _clean_scalar(val) for key, val in row.items()}
        opp = normalize_jobspy_row(cleaned, fetched_at=fetched_at)
        if not opp:
            continue
        oid = opp["opportunity_id"]
        if oid in seen_ids:
            continue
        seen_ids.add(oid)
        opportunities.append(opp)

    if not opportunities:
        errors.append("jobspy rows did not normalize to opportunities (missing title/company/url)")
    return opportunities, errors


def build_jobspy_envelope(
    *,
    query: str,
    sites: list[str],
    location: str | None,
    posted_within_days: int,
    opportunities: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "query": query,
        "sites": sites,
        "location": location,
        "posted_within_days": posted_within_days,
        "fetched_at": _now_iso(),
        "count": len(opportunities),
        "errors": errors,
        "opportunities": opportunities,
    }


def write_jobspy_artifact(path: Path, envelope: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def format_jobspy_prompt_block(
    envelope: dict[str, Any],
    *,
    max_listings: int = 40,
) -> str:
    """Markdown section injected into zazu_researcher SEARCH_OPPORTUNITIES prompt."""
    lines = [
        "## JobSpy aggregator (deterministic pre-fetch)",
        f"- schema: `{envelope.get('schema')}`",
        f"- sites: {', '.join(envelope.get('sites') or [])}",
        f"- fetched_at: {envelope.get('fetched_at')}",
        f"- count: {envelope.get('count', 0)}",
    ]
    if envelope.get("location"):
        lines.append(f"- location filter: {envelope['location']}")
    for err in envelope.get("errors") or []:
        lines.append(f"- warning: {err}")

    opportunities = envelope.get("opportunities") or []
    if not opportunities:
        lines.append("\n(no JobSpy rows — continue with web_search on ATS boards)")
        return "\n".join(lines)

    lines.append("\nTreat these as **seed hits** — verify dates, dedupe against registry, then enrich via web_search.")
    lines.append("| company | title | location | posted | platform | apply_url |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for opp in opportunities[:max_listings]:
        agg = opp.get("aggregator") or {}
        posted = agg.get("date_posted") or "?"
        platform = agg.get("platform") or "?"
        loc = (opp.get("location") or "").replace("|", "/")
        lines.append(
            f"| {opp.get('company', '?')} | {opp.get('title', '?')} | {loc} | {posted} | "
            f"{platform} | {opp.get('apply_url', '?')} |"
        )
    if len(opportunities) > max_listings:
        lines.append(f"\n… and {len(opportunities) - max_listings} more in the JSON artifact.")
    return "\n".join(lines)
