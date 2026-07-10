"""SQLite application registry — applied roles, outcomes, dedupe."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

APPLICATIONS_DB_FILENAME = "applications.db"

STATUSES = (
    "considered",
    "applied",
    "interviewing",
    "offered",
    "rejected",
    "withdrawn",
    "skipped",
)


@dataclass
class ApplicationRecord:
    opportunity_id: str
    company: str
    job_title: str
    job_id: str | None
    apply_url: str | None
    dedupe_key: str
    status: str
    job_date: str | None
    proposal_run: str | None
    resume_path: str | None
    cover_path: str | None
    brief_path: str | None
    vault_path: str | None
    notes: str | None
    created_at: str
    updated_at: str


def applications_db_path(index_dir: Path) -> Path:
    return index_dir / APPLICATIONS_DB_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug_segment(value: str, *, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned[:max_len].rstrip("_") if cleaned else "na"


def normalize_company(company: str) -> str:
    base = re.sub(r"\s*\([^)]*\)", "", company or "").strip()
    return slug_segment(base)


def make_dedupe_key(*, company: str, job_title: str, job_id: str | None) -> str:
    cid = normalize_company(company)
    title = slug_segment(job_title)
    jid = slug_segment(job_id or "na")
    return f"{cid}|{title}|{jid}"


def make_opportunity_id(dedupe_key: str) -> str:
    digest = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:16]
    return f"opp:{digest}"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS applications (
                opportunity_id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                job_title TEXT NOT NULL,
                job_id TEXT,
                apply_url TEXT,
                dedupe_key TEXT NOT NULL,
                status TEXT NOT NULL,
                job_date TEXT,
                proposal_run TEXT,
                resume_path TEXT,
                cover_path TEXT,
                brief_path TEXT,
                vault_path TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_applications_company
                ON applications (company);
            CREATE INDEX IF NOT EXISTS idx_applications_dedupe
                ON applications (dedupe_key);
            CREATE INDEX IF NOT EXISTS idx_applications_status
                ON applications (status);
            CREATE TABLE IF NOT EXISTS application_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY (opportunity_id) REFERENCES applications(opportunity_id)
            );
            CREATE INDEX IF NOT EXISTS idx_application_events_opp
                ON application_events (opportunity_id);
            """
        )
        conn.commit()


def _row_to_record(row: sqlite3.Row) -> ApplicationRecord:
    return ApplicationRecord(
        opportunity_id=str(row["opportunity_id"]),
        company=str(row["company"]),
        job_title=str(row["job_title"]),
        job_id=row["job_id"],
        apply_url=row["apply_url"],
        dedupe_key=str(row["dedupe_key"]),
        status=str(row["status"]),
        job_date=row["job_date"],
        proposal_run=row["proposal_run"],
        resume_path=row["resume_path"],
        cover_path=row["cover_path"],
        brief_path=row["brief_path"],
        vault_path=row["vault_path"],
        notes=row["notes"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def upsert_application(
    db_path: Path,
    *,
    company: str,
    job_title: str,
    job_id: str | None = None,
    apply_url: str | None = None,
    status: str = "applied",
    job_date: str | None = None,
    proposal_run: str | None = None,
    resume_path: str | None = None,
    cover_path: str | None = None,
    brief_path: str | None = None,
    vault_path: str | None = None,
    notes: str | None = None,
) -> ApplicationRecord:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}, got {status!r}")

    init_db(db_path)
    dedupe_key = make_dedupe_key(company=company, job_title=job_title, job_id=job_id)
    opportunity_id = make_opportunity_id(dedupe_key)
    now = _now_iso()

    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT * FROM applications WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE applications SET
                    company = ?, job_title = ?, job_id = ?, apply_url = ?,
                    dedupe_key = ?, status = ?, job_date = ?,
                    proposal_run = COALESCE(?, proposal_run),
                    resume_path = COALESCE(?, resume_path),
                    cover_path = COALESCE(?, cover_path),
                    brief_path = COALESCE(?, brief_path),
                    vault_path = COALESCE(?, vault_path),
                    notes = COALESCE(?, notes),
                    updated_at = ?
                WHERE opportunity_id = ?
                """,
                (
                    company,
                    job_title,
                    job_id,
                    apply_url,
                    dedupe_key,
                    status,
                    job_date,
                    proposal_run,
                    resume_path,
                    cover_path,
                    brief_path,
                    vault_path,
                    notes,
                    now,
                    opportunity_id,
                ),
            )
            if existing["status"] != status:
                _insert_event(conn, opportunity_id, status, notes)
        else:
            conn.execute(
                """
                INSERT INTO applications (
                    opportunity_id, company, job_title, job_id, apply_url,
                    dedupe_key, status, job_date, proposal_run,
                    resume_path, cover_path, brief_path, vault_path, notes,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    opportunity_id,
                    company,
                    job_title,
                    job_id,
                    apply_url,
                    dedupe_key,
                    status,
                    job_date,
                    proposal_run,
                    resume_path,
                    cover_path,
                    brief_path,
                    vault_path,
                    notes,
                    now,
                    now,
                ),
            )
            _insert_event(conn, opportunity_id, status, notes)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM applications WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()
        assert row is not None
        return _row_to_record(row)


def _insert_event(
    conn: sqlite3.Connection,
    opportunity_id: str,
    status: str,
    notes: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO application_events (opportunity_id, status, notes, recorded_at)
        VALUES (?, ?, ?, ?)
        """,
        (opportunity_id, status, notes, _now_iso()),
    )


def record_outcome(
    db_path: Path,
    *,
    opportunity_id: str | None = None,
    company: str | None = None,
    status: str,
    notes: str | None = None,
) -> ApplicationRecord | None:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}, got {status!r}")
    init_db(db_path)

    with connect(db_path) as conn:
        row = None
        if opportunity_id:
            row = conn.execute(
                "SELECT * FROM applications WHERE opportunity_id = ?",
                (opportunity_id,),
            ).fetchone()
        elif company:
            row = _find_best_company_match(conn, company)
        if row is None:
            return None

        oid = str(row["opportunity_id"])
        now = _now_iso()
        conn.execute(
            "UPDATE applications SET status = ?, notes = COALESCE(?, notes), updated_at = ? WHERE opportunity_id = ?",
            (status, notes, now, oid),
        )
        _insert_event(conn, oid, status, notes)
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM applications WHERE opportunity_id = ?",
            (oid,),
        ).fetchone()
        return _row_to_record(updated) if updated else None


def find_by_company(db_path: Path, company: str) -> list[ApplicationRecord]:
    init_db(db_path)
    needle = normalize_company(company)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY updated_at DESC",
        ).fetchall()
    hits = [ _row_to_record(r) for r in rows if normalize_company(r["company"]) == needle ]
    return hits


def find_company_overlap(db_path: Path, company: str) -> list[ApplicationRecord]:
    """Any prior application at this employer (any role)."""
    return find_by_company(db_path, company)


def find_exact(db_path: Path, *, company: str, job_title: str, job_id: str | None) -> ApplicationRecord | None:
    init_db(db_path)
    dedupe_key = make_dedupe_key(company=company, job_title=job_title, job_id=job_id)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
    return _row_to_record(row) if row else None


def list_applications(db_path: Path, *, limit: int = 100) -> list[ApplicationRecord]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_record(r) for r in rows]


def _find_best_company_match(conn: sqlite3.Connection, company: str) -> sqlite3.Row | None:
    needle = normalize_company(company)
    rows = conn.execute("SELECT * FROM applications ORDER BY updated_at DESC").fetchall()
    for row in rows:
        if normalize_company(str(row["company"])) == needle:
            return row
    return None


def format_registry_summary(db_path: Path, *, limit: int = 40) -> str:
    """Compact text block for agent prompts."""
    records = list_applications(db_path, limit=limit)
    if not records:
        return "(empty — no applications recorded yet)"

    lines = [
        "| company | title | job_id | status | job_date | notes |",
        "|---|---|---|---|---|---|",
    ]
    for rec in records:
        note = (rec.notes or "").replace("|", "/").replace("\n", " ")[:80]
        lines.append(
            f"| {rec.company} | {rec.job_title} | {rec.job_id or 'na'} | {rec.status} | {rec.job_date or 'na'} | {note} |"
        )
    return "\n".join(lines)


def import_vault_folders(kb_root: Path, db_path: Path) -> list[ApplicationRecord]:
    """Import company folders from application_history (e.g. onedrive-applications/YYYYMMDD/Company/)."""
    init_db(db_path)
    history = kb_root / "private" / "application_history"
    if not history.is_dir():
        return []

    imported: list[ApplicationRecord] = []
    date_dir_re = re.compile(r"^\d{8}$")

    for date_dir in history.rglob("*"):
        if not date_dir.is_dir():
            continue
        if not date_dir_re.match(date_dir.name):
            continue
        for company_dir in date_dir.iterdir():
            if not company_dir.is_dir() or company_dir.name.startswith("."):
                continue
            vault_rel = company_dir.relative_to(kb_root).as_posix()
            resume = next(company_dir.glob("*resume*.docx"), None) or next(
                company_dir.glob("*resume*.pdf"), None
            )
            cover = next(company_dir.glob("*cover*.docx"), None)

            title = _infer_title_from_vault(kb_root, vault_rel, company_dir.name)
            notes = f"imported from vault {vault_rel}"
            rec = upsert_application(
                db_path,
                company=company_dir.name,
                job_title=title,
                job_id="na",
                status="applied",
                job_date=date_dir.name,
                vault_path=vault_rel,
                resume_path=resume.relative_to(kb_root).as_posix() if resume else None,
                cover_path=cover.relative_to(kb_root).as_posix() if cover else None,
                notes=notes,
            )
            imported.append(rec)
    return imported


def _infer_title_from_vault(kb_root: Path, vault_rel: str, company: str) -> str:
    """Try catalog extracted text for role title; fallback to unknown."""
    index_dir = kb_root / "_index"
    catalog_path = index_dir / "catalog.json"
    if not catalog_path.is_file():
        return f"unknown role at {company}"

    import json

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    documents: dict[str, Any] = catalog.get("documents") or {}
    for rel, meta in documents.items():
        if not rel.startswith(vault_rel):
            continue
        extracted_rel = meta.get("extracted_text_path")
        if not extracted_rel:
            continue
        extracted = index_dir / str(extracted_rel)
        if not extracted.is_file():
            continue
        text = extracted.read_text(encoding="utf-8", errors="replace")[:4000]
        match2 = re.search(r"apply for (?:the )?(.+?) role at", text, re.IGNORECASE)
        if match2:
            return match2.group(1).strip()
    return f"unknown role at {company}"
