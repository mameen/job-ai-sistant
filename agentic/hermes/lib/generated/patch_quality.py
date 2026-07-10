"""Coach patch validation and light sanitization before DOCX merge."""

from __future__ import annotations

import re
from pathlib import Path

from .docx_io import parse_section_markdown

# Section ids required in each patch kind (manifest contract).
REQUIRED_RESUME_SECTIONS = ("SUMMARY", "AREAS_OF_EXPERTISE", "EXPERIENCES", "EDUCATION")
REQUIRED_COVER_SECTIONS = ("COVER_P1", "COVER_P2", "COVER_P3", "COVER_P4", "COVER_P5")
REQUIRED_BRIEF_SECTIONS = (
    "OPPORTUNITY_INTELLIGENCE",
    "FLAG_ANALYSIS",
    "LEVEL_MAPPING",
    "EMPLOYER_SUMMARY",
    "TOP_MATCHING_EXPERIENCE",
    "JD_ALIGNMENT",
    "GAPS_MITIGATIONS",
    "STAR_STORIES",
    "INTERVIEW_INTELLIGENCE",
    "COMPENSATION_NEXT_STEPS",
    "RECOMMENDATION",
)

# Known coach mistakes → correction (word boundaries).
_AUTOFIX_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bcalendric\b", re.I), "Calendly scheduling"),
    (re.compile(r"\bimprove rate\b", re.I), "improved output rate"),
    (re.compile(r"\boutside GSA\b", re.I), "outside the Greater Seattle Area"),
    (re.compile(r"\bem dash\b", re.I), "dash"),
)

_BANNED_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\[COMPANY\]|\[ROLE TITLE\]"), "unfilled bracket placeholder"),
    (re.compile(r"\{\{SECTION:"), "unmerged template marker"),
)


def sanitize_patch_text(text: str) -> tuple[str, list[str]]:
    """Apply safe autofixes; return (cleaned_text, notes)."""
    notes: list[str] = []
    out = text
    for pattern, replacement in _AUTOFIX_PATTERNS:
        if pattern.search(out):
            out = pattern.sub(replacement, out)
            notes.append(f"autofix: {pattern.pattern} → {replacement!r}")
    return out, notes


def validate_patch_text(text: str, *, kind: str) -> list[str]:
    """Return human-readable validation errors (empty = OK)."""
    errors: list[str] = []
    required = {
        "resume": REQUIRED_RESUME_SECTIONS,
        "cover": REQUIRED_COVER_SECTIONS,
        "brief": REQUIRED_BRIEF_SECTIONS,
    }.get(kind, ())

    sections = parse_section_markdown(text)
    for section_id in required:
        if section_id not in sections or not sections[section_id].strip():
            errors.append(f"missing or empty section ## {section_id}")

    for pattern, label in _BANNED_PATTERNS:
        if pattern.search(text):
            errors.append(f"contains {label}")

    # Obvious non-words / typos the coach invents.
    if re.search(r"\bcalendric\b", text, re.I):
        errors.append("suspect word 'calendric' — use 'Calendly' or 'scheduling'")

    return errors


def prepare_patch_file(path: Path, *, kind: str) -> list[str]:
    """Sanitize patch on disk; return validation errors after sanitize."""
    raw = path.read_text(encoding="utf-8")
    cleaned, notes = sanitize_patch_text(raw)
    if cleaned != raw:
        path.write_text(cleaned, encoding="utf-8")
    errors = validate_patch_text(cleaned, kind=kind)
    return notes + [f"error: {e}" for e in errors]


def prepare_run_patches(run_dir: Path) -> dict[str, list[str]]:
    """Sanitize and validate all *_patch.md files in a proposal run."""
    report: dict[str, list[str]] = {}
    for kind in ("resume", "cover", "brief"):
        for patch_path in sorted(run_dir.glob(f"*_{kind}_patch.md")):
            report[patch_path.name] = prepare_patch_file(patch_path, kind=kind)
    return report
