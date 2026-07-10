"""Email poll orchestration — unread mail → intake artifacts + dedupe state."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .email_intake import EmailConnector, InboundMessage, message_to_opportunity

POLL_SCHEMA = "email_poll/v1"
STATE_SCHEMA = "email_poll_state/v1"
STATE_FILENAME = "email_poll_state.json"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _poll_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def state_path(runtime_dir: Path) -> Path:
    return runtime_dir / STATE_FILENAME


def load_poll_state(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != STATE_SCHEMA:
        return set()
    ids = data.get("seen_message_ids") or []
    return {str(i) for i in ids}


def save_poll_state(path: Path, seen_ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": STATE_SCHEMA,
        "updated_at": _now_iso(),
        "seen_message_ids": sorted(seen_ids),
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def poll_connector(
    connector: EmailConnector,
    *,
    limit: int,
    seen_ids: set[str],
    job_filter: bool = False,
) -> tuple[list[InboundMessage], list[InboundMessage], int]:
    """Return (new_messages, all_fetched, skipped_seen_count)."""
    fetched = connector.list_unread(limit=limit)
    skipped = 0
    fresh: list[InboundMessage] = []
    for msg in fetched:
        if msg.message_id in seen_ids:
            skipped += 1
            continue
        if job_filter:
            from .email_intake import is_likely_job_posting_url

            urls = msg.urls_found
            if urls and not any(is_likely_job_posting_url(u) for u in urls):
                if not _looks_like_recruiter_subject(msg.subject):
                    continue
        fresh.append(msg)
    return fresh, fetched, skipped


def _looks_like_recruiter_subject(subject: str) -> bool:
    subj = (subject or "").lower()
    hints = (
        "opportunity",
        "role",
        "position",
        "hiring",
        "engineer",
        "manager",
        "recruiter",
        "interview",
        "application",
    )
    return any(h in subj for h in hints)


def build_poll_envelope(
    *,
    vault_key: str,
    connector: EmailConnector,
    messages: list[InboundMessage],
    skipped_seen: int,
    fetched_total: int,
) -> dict[str, Any]:
    opportunities = [message_to_opportunity(m) for m in messages]
    return {
        "schema": POLL_SCHEMA,
        "vault_key": vault_key,
        "connector": connector.provider,
        "fetched_at": _now_iso(),
        "fetched_total": fetched_total,
        "skipped_seen": skipped_seen,
        "count": len(opportunities),
        "opportunities": opportunities,
    }


def write_poll_artifact(intake_dir: Path, envelope: dict[str, Any]) -> Path:
    intake_dir.mkdir(parents=True, exist_ok=True)
    stamp = _poll_stamp()
    path = intake_dir / f"email_poll_{stamp}.json"
    path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest = intake_dir / "email_poll_latest.json"
    latest.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_email_poll(
    *,
    connector: EmailConnector,
    vault_key: str,
    runtime_dir: Path,
    intake_dir: Path,
    limit: int = 20,
    job_filter: bool = False,
) -> dict[str, Any]:
    state_file = state_path(runtime_dir)
    seen = load_poll_state(state_file)
    messages, fetched, skipped = poll_connector(
        connector,
        limit=limit,
        seen_ids=seen,
        job_filter=job_filter,
    )
    envelope = build_poll_envelope(
        vault_key=vault_key,
        connector=connector,
        messages=messages,
        skipped_seen=skipped,
        fetched_total=len(fetched),
    )
    artifact = write_poll_artifact(intake_dir, envelope)
    for msg in messages:
        seen.add(msg.message_id)
    save_poll_state(state_file, seen)
    return {
        "artifact": str(artifact),
        "count": envelope["count"],
        "skipped_seen": skipped,
        "fetched_total": len(fetched),
    }
