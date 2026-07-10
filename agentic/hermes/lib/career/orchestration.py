"""Career Zazu orchestration — board filtering and STATUS (Digest-safe)."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PRODUCT_ID = "career_zazu"
DIGEST_PRODUCT_ID = "ai_digest"

# Hermes kanban assignees — logical partition (shared physical board).
CAREER_ASSIGNEES = frozenset(
    {
        "zazu_knowledge_manager",
        "zazu_researcher",
        "zazu_coach",
    }
)
DIGEST_ASSIGNEES = frozenset(
    {
        "ai_news_concierge",
        "ai_news_researcher",
        "ai_news_librarian",
        "ai_news_synthesizer",
    }
)

CAREER_TITLE_PREFIX = "Career:"


def _hermes_bin() -> str | None:
    return shutil.which("hermes")


def kanban_list(*, raise_on_error: bool = False) -> list[dict[str, Any]]:
    hermes = _hermes_bin()
    if not hermes:
        if raise_on_error:
            raise RuntimeError("hermes not on PATH")
        return []
    proc = subprocess.run(
        [hermes, "kanban", "list", "--json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        if raise_on_error:
            raise RuntimeError(proc.stderr or proc.stdout or "kanban list failed")
        return []
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        if raise_on_error:
            raise
        return []


def career_board_rows(rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Career Zazu tasks only — excludes AI Digest rows on the shared kanban."""
    rows = rows if rows is not None else kanban_list()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        assignee = str(row.get("assignee") or "")
        title = str(row.get("title") or "")
        if assignee in DIGEST_ASSIGNEES:
            continue
        if assignee in CAREER_ASSIGNEES:
            filtered.append(row)
            continue
        if title.startswith(CAREER_TITLE_PREFIX):
            filtered.append(row)
    return filtered


def digest_board_rows(rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """AI Digest tasks only — mirror of Digest orchestration filter (for isolation tests)."""
    rows = rows if rows is not None else kanban_list()
    digest_titles = {"Librarian: merge & classify", "Synthesize digest"}
    return [
        r
        for r in rows
        if str(r.get("assignee") or "") in DIGEST_ASSIGNEES
        or str(r.get("title", "")).startswith("Research:")
        or str(r.get("title", "")) in digest_titles
    ]


def _iso_mtime(path: Path) -> str | None:
    if not path.is_file():
        return None
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _latest_proposal_run(proposals_root: Path) -> str | None:
    if not proposals_root.is_dir():
        return None
    runs = sorted(
        (p.name for p in proposals_root.iterdir() if p.is_dir() and p.name.isdigit()),
        reverse=True,
    )
    return runs[0] if runs else None


def career_status(
    *,
    repo: Path,
    kb_index: Path,
    generated_researched: Path,
    generated_proposals: Path,
    generated_intake: Path | None = None,
) -> dict[str, Any]:
    """Deterministic Career STATUS snapshot for CKM — not LLM inference."""
    from lib.kb.application_registry import applications_db_path, list_applications
    from lib.kb.learning_registry import list_learning_events, topic_response_rates

    db_path = applications_db_path(kb_index)
    search_latest = generated_researched / "search_latest.md"
    search_jobspy = generated_researched / "search_jobspy.json"
    intake_root = generated_intake or (repo / "agentic" / "hermes" / ".generated" / "intake")
    email_poll_latest = intake_root / "email_poll_latest.json"

    rows = kanban_list()
    career_rows = career_board_rows(rows)
    digest_rows = digest_board_rows(rows)

    status_counts: dict[str, int] = {}
    try:
        for rec in list_applications(db_path, limit=10_000):
            status_counts[rec.status] = status_counts.get(rec.status, 0) + 1
    except Exception:
        status_counts = {}

    return {
        "ok": True,
        "product": PRODUCT_ID,
        "coexistence": {
            "shared_kanban": True,
            "career_task_count": len(career_rows),
            "digest_task_count": len(digest_rows),
            "rule": "Filter by assignee (zazu_* vs ai_news_*) and Career: title prefix",
            "digest_product": DIGEST_PRODUCT_ID,
        },
        "intents": {
            "DISCOVER": "manage.py search -q …",
            "EVALUATE": "hermes -p zazu_researcher chat (EVALUATE_OPPORTUNITY)",
            "APPLY": "manage.py apply [--coach]",
            "RECORD_OUTCOME": "manage.py applications record-outcome",
            "ANALYZE": "manage.py career topics",
            "STEWARD": "manage.py kb-scan",
            "STATUS": "manage.py career status",
            "EMAIL_POLL": "manage.py email poll --vault-key …",
        },
        "artifacts": {
            "search_latest": {
                "path": str(search_latest.relative_to(repo)) if search_latest.is_file() else None,
                "mtime": _iso_mtime(search_latest),
            },
            "search_jobspy": {
                "path": str(search_jobspy.relative_to(repo)) if search_jobspy.is_file() else None,
                "mtime": _iso_mtime(search_jobspy),
            },
            "email_poll_latest": {
                "path": str(email_poll_latest.relative_to(repo)) if email_poll_latest.is_file() else None,
                "mtime": _iso_mtime(email_poll_latest),
            },
            "latest_proposal_run": _latest_proposal_run(generated_proposals),
        },
        "registry": {
            "db": str(db_path.relative_to(repo)) if db_path.is_file() else str(db_path),
            "status_counts": status_counts,
        },
        "topics": [
            {
                "topic": s.topic,
                "total": s.total,
                "applied": s.applied,
                "interviewing": s.interviewing,
                "offered": s.offered,
                "rejected": s.rejected,
                "response_rate": s.response_rate,
            }
            for s in topic_response_rates(db_path)
        ],
        "learning_events_recent": [
            {
                "event_id": e.event_id,
                "source_type": e.source_type,
                "source_ref": e.source_ref,
                "target": e.target,
                "action": e.action,
                "explanation": e.explanation,
                "created_at": e.created_at,
            }
            for e in list_learning_events(db_path, limit=10)
        ],
        "kanban_career_tasks": [
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "assignee": r.get("assignee"),
                "status": r.get("status"),
            }
            for r in career_rows
        ],
    }
