"""Learning ledger + topic tags — auditable career preference propagation."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .application_registry import connect, init_db

LEARNING_ACTIONS = ("proposed", "auto_applied", "approved", "rejected")
LEARNING_SOURCE_TYPES = (
    "user_rejection",
    "user_outcome",
    "user_kb_edit",
    "coach_proposal",
    "search_signal",
    "topic_tag",
)
TOPIC_SOURCES = ("user", "researcher", "auto")


@dataclass
class LearningEvent:
    event_id: str
    source_type: str
    source_ref: str | None
    target: str
    action: str
    explanation: str
    created_at: str


@dataclass
class TopicStat:
    topic: str
    total: int
    applied: int
    interviewing: int
    offered: int
    rejected: int
    response_rate: float | None  # (interviewing+offered)/applied for terminal-ish view


def normalize_topic(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned[:48] if cleaned else "na"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _make_event_id(*, source_ref: str, target: str, created_at: str) -> str:
    day = created_at[:10].replace("-", "")
    digest = hashlib.sha256(f"{source_ref}|{target}|{created_at}".encode()).hexdigest()[:8]
    return f"le:{day}:{digest}"


def init_learning_tables(db_path: Path) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS application_topics (
                opportunity_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (opportunity_id, topic),
                FOREIGN KEY (opportunity_id) REFERENCES applications(opportunity_id)
            );
            CREATE INDEX IF NOT EXISTS idx_application_topics_topic
                ON application_topics (topic);

            CREATE TABLE IF NOT EXISTS learning_events (
                event_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_ref TEXT,
                target TEXT NOT NULL,
                action TEXT NOT NULL,
                explanation TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_learning_events_source_ref
                ON learning_events (source_ref);
            CREATE INDEX IF NOT EXISTS idx_learning_events_target
                ON learning_events (target);
            CREATE INDEX IF NOT EXISTS idx_learning_events_action
                ON learning_events (action);
            CREATE INDEX IF NOT EXISTS idx_learning_events_created
                ON learning_events (created_at);
            """
        )
        conn.commit()


def set_application_topics(
    db_path: Path,
    opportunity_id: str,
    topics: list[str],
    *,
    source: str = "auto",
) -> list[str]:
    if source not in TOPIC_SOURCES:
        raise ValueError(f"source must be one of {TOPIC_SOURCES}, got {source!r}")
    normalized = sorted({normalize_topic(t) for t in topics if normalize_topic(t) != "na"})
    if not normalized:
        return []

    init_learning_tables(db_path)
    now = _now_iso()
    with connect(db_path) as conn:
        for topic in normalized:
            conn.execute(
                """
                INSERT INTO application_topics (opportunity_id, topic, source, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(opportunity_id, topic) DO UPDATE SET
                    source = excluded.source,
                    created_at = excluded.created_at
                """,
                (opportunity_id, topic, source, now),
            )
        conn.commit()
    return normalized


def list_application_topics(db_path: Path, opportunity_id: str) -> list[str]:
    init_learning_tables(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT topic FROM application_topics WHERE opportunity_id = ? ORDER BY topic",
            (opportunity_id,),
        ).fetchall()
    return [str(r["topic"]) for r in rows]


def record_learning_event(
    db_path: Path,
    *,
    source_type: str,
    source_ref: str | None,
    target: str,
    action: str,
    explanation: str,
) -> LearningEvent:
    if source_type not in LEARNING_SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {LEARNING_SOURCE_TYPES}")
    if action not in LEARNING_ACTIONS:
        raise ValueError(f"action must be one of {LEARNING_ACTIONS}")
    if not explanation.strip():
        raise ValueError("explanation is required")

    init_learning_tables(db_path)
    now = _now_iso()
    event_id = _make_event_id(
        source_ref=source_ref or "",
        target=target,
        created_at=now,
    )
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO learning_events (
                event_id, source_type, source_ref, target, action, explanation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, source_type, source_ref, target, action, explanation.strip(), now),
        )
        conn.commit()
    return LearningEvent(
        event_id=event_id,
        source_type=source_type,
        source_ref=source_ref,
        target=target,
        action=action,
        explanation=explanation.strip(),
        created_at=now,
    )


def list_learning_events(db_path: Path, *, limit: int = 50) -> list[LearningEvent]:
    init_learning_tables(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM learning_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        LearningEvent(
            event_id=str(r["event_id"]),
            source_type=str(r["source_type"]),
            source_ref=r["source_ref"],
            target=str(r["target"]),
            action=str(r["action"]),
            explanation=str(r["explanation"]),
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]


def topic_response_rates(db_path: Path) -> list[TopicStat]:
    """Per-topic counts and rough response rate (interviews+offers / applied)."""
    init_learning_tables(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                t.topic AS topic,
                COUNT(DISTINCT a.opportunity_id) AS total,
                SUM(CASE WHEN a.status = 'applied' THEN 1 ELSE 0 END) AS applied,
                SUM(CASE WHEN a.status = 'interviewing' THEN 1 ELSE 0 END) AS interviewing,
                SUM(CASE WHEN a.status = 'offered' THEN 1 ELSE 0 END) AS offered,
                SUM(CASE WHEN a.status = 'rejected' THEN 1 ELSE 0 END) AS rejected
            FROM application_topics t
            JOIN applications a ON a.opportunity_id = t.opportunity_id
            GROUP BY t.topic
            ORDER BY t.topic
            """
        ).fetchall()

    stats: list[TopicStat] = []
    for r in rows:
        applied = int(r["applied"] or 0)
        interviewing = int(r["interviewing"] or 0)
        offered = int(r["offered"] or 0)
        denom = applied + interviewing + offered + int(r["rejected"] or 0)
        responses = interviewing + offered
        rate = (responses / denom) if denom else None
        stats.append(
            TopicStat(
                topic=str(r["topic"]),
                total=int(r["total"] or 0),
                applied=applied,
                interviewing=interviewing,
                offered=offered,
                rejected=int(r["rejected"] or 0),
                response_rate=round(rate, 3) if rate is not None else None,
            )
        )
    return stats
