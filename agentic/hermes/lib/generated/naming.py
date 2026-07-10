"""Generated artifact paths and naming conventions."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

GENERATED_DIR_NAME = ".generated"
RESEARCHED_DIR = "researched"
RECOMMENDED_DIR = "recommended"
PROPOSALS_DIR = "proposals"

ARTIFACT_KINDS = ("resume", "cover", "brief")


def hermes_paths(hermes_pkg: Path) -> tuple[Path, Path, Path, Path]:
    """Return (generated_root, researched, recommended, proposals)."""
    root = hermes_pkg / GENERATED_DIR_NAME
    return (
        root,
        root / RESEARCHED_DIR,
        root / RECOMMENDED_DIR,
        root / PROPOSALS_DIR,
    )


def slug_segment(value: str, *, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower())
    cleaned = cleaned.strip("_")
    if not cleaned:
        return "na"
    return cleaned[:max_len].rstrip("_")


def artifact_filename(
    *,
    company: str,
    job_title: str,
    job_id: str,
    job_date: str | datetime,
    kind: str,
    extension: str = "docx",
) -> str:
    if kind not in ARTIFACT_KINDS:
        raise ValueError(f"kind must be one of {ARTIFACT_KINDS}, got {kind!r}")
    if isinstance(job_date, datetime):
        date_part = job_date.strftime("%Y%m%d")
    else:
        date_part = re.sub(r"[^0-9]", "", job_date)[:8] or datetime.now().strftime("%Y%m%d")
    job_id_part = slug_segment(job_id) if job_id else "na"
    ext = extension.lstrip(".")
    return (
        f"{slug_segment(company)}_{slug_segment(job_title)}_{job_id_part}_{date_part}_{kind}.{ext}"
    )


def proposal_run_dir(proposals_root: Path, run_prefix: str | None = None) -> Path:
    prefix = run_prefix or datetime.now().strftime("%Y%m%d%H%M%S")
    return proposals_root / prefix
