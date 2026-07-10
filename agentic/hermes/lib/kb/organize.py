from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RESUME_PRIORITY = (
    "private/originals/resume-repo/pm-resume.docx",
    "private/originals/resume-repo/pm-resume.pdf",
    "private/application_history/onedrive-applications/pm-resume.docx",
    "private/application_history/onedrive-applications/pm-resume.pdf",
    "public/master_resume.md",
)


@dataclass
class OrganizeResult:
    updated_files: list[str]
    resume_source: str | None


def organize_kb(
    kb_root: Path,
    catalog: dict[str, Any],
    index_dir: Path,
    *,
    force: bool = False,
) -> OrganizeResult:
    """Distill vault extractions into canonical public/private markdown."""
    documents: dict[str, Any] = catalog.get("documents") or {}
    resume_rel, resume_text = _pick_resume_text(documents, index_dir)
    updated: list[str] = []

    if resume_text:
        master_path = kb_root / "public" / "master_resume.md"
        if force or _needs_update(master_path):
            master_path.write_text(_format_master_resume(resume_rel, resume_text), encoding="utf-8")
            updated.append("public/master_resume.md")

        skills_path = kb_root / "public" / "skills.md"
        if force or _needs_update(skills_path):
            skills_path.write_text(_format_skills(resume_text), encoding="utf-8")
            updated.append("public/skills.md")

        edu_path = kb_root / "public" / "education.md"
        if force or _needs_update(edu_path):
            edu_path.write_text(_format_education(resume_rel, resume_text), encoding="utf-8")
            updated.append("public/education.md")

        cert_path = kb_root / "public" / "certifications.md"
        if force or _needs_update(cert_path):
            cert_path.write_text(_format_certifications(resume_rel, resume_text), encoding="utf-8")
            updated.append("public/certifications.md")

    _sync_flags_from_prompts(kb_root, updated, force=force)

    return OrganizeResult(updated_files=updated, resume_source=resume_rel)


def _pick_resume_text(
    documents: dict[str, Any],
    index_dir: Path,
) -> tuple[str | None, str]:
    for rel in RESUME_PRIORITY:
        doc = documents.get(rel)
        if not doc:
            continue
        text = _read_extracted(index_dir, doc)
        if len(text.strip()) >= 200:
            return rel, text
    best_rel: str | None = None
    best_text = ""
    for rel, doc in documents.items():
        if doc.get("category_id") not in {"master_resume", "career_goals"}:
            continue
        if "resume" not in rel.lower():
            continue
        text = _read_extracted(index_dir, doc)
        if len(text.strip()) > len(best_text.strip()):
            best_rel, best_text = rel, text
    return best_rel, best_text


def _read_extracted(index_dir: Path, doc: dict[str, Any]) -> str:
    rel = doc.get("extracted_text_path")
    if not rel:
        return ""
    path = index_dir / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _needs_update(path: Path) -> bool:
    if not path.is_file():
        return True
    text = path.read_text(encoding="utf-8")
    placeholders = ("_(", "<!-- Replace", "Template", "placeholder")
    return any(p in text for p in placeholders) or len(text.strip()) < 120


def _format_master_resume(source_rel: str | None, text: str) -> str:
    header = "# Master resume\n\n"
    if source_rel:
        header += f"**Auto-distilled from:** `{source_rel}`  \n"
        header += "Edit by hand or re-run `kb-extract --force-organize` after vault changes.\n\n"
    body = text.strip()
    if not body.startswith("#"):
        body = "## Content\n\n" + body
    return header + body + "\n"


def _format_skills(text: str) -> str:
    section = _extract_section(
        text,
        start_markers=("Areas of Expertise", "AREAS OF EXPERTISE", "Skills"),
        end_markers=("Experience", "EXPERIENCES", "Education", "Senior Software"),
    )
    header = "# Skills\n\nDistilled from master resume extraction.\n\n"
    if section:
        return header + section.strip() + "\n"
    return header + "_See master_resume.md — skills section not auto-detected._\n"


def _format_education(source_rel: str | None, text: str) -> str:
    section = _extract_section(
        text,
        start_markers=("Education", "EDUCATION"),
        end_markers=("Certifications", "Selected Technical", "Selected AI"),
    )
    header = "# Education\n\n"
    if source_rel:
        header += f"**Source:** `{source_rel}`\n\n"
    if section:
        return header + section.strip() + "\n"
    return header + "| Institution | Degree | Dates | Notes |\n|---|---|---|---|\n"


def _format_certifications(source_rel: str | None, text: str) -> str:
    section = _extract_section(
        text,
        start_markers=("Certifications", "CERTIFICATIONS"),
        end_markers=("Selected AI", "Selected Technical", "Technical Stack"),
    )
    header = "# Certifications\n\n"
    if source_rel:
        header += f"**Source:** `{source_rel}`\n\n"
    if section:
        lines = [ln.strip() for ln in section.splitlines() if ln.strip()]
        rows = ["| Certification | Issuer | Date | Notes |", "|---|---|---|---|"]
        for ln in lines:
            if ln.startswith("|"):
                continue
            rows.append(f"| {ln} | | | |")
        return header + "\n".join(rows) + "\n"
    return header + "| Certification | Issuer | Date | Verification URL |\n|---|---|---|---|\n"


def _extract_section(
    text: str,
    *,
    start_markers: tuple[str, ...],
    end_markers: tuple[str, ...],
) -> str:
    lower = text.lower()
    start_idx = -1
    for marker in start_markers:
        idx = lower.find(marker.lower())
        if idx >= 0 and (start_idx < 0 or idx < start_idx):
            start_idx = idx
    if start_idx < 0:
        return ""
    tail = text[start_idx:]
    end_idx = len(tail)
    for marker in end_markers:
        idx = tail.lower().find(marker.lower(), 1)
        if idx > 0:
            end_idx = min(end_idx, idx)
    return tail[:end_idx].strip()


def _sync_flags_from_prompts(kb_root: Path, updated: list[str], *, force: bool) -> None:
    prompts = kb_root / "private" / "prompts" / "job_fitness.md"
    if not prompts.is_file():
        return
    text = prompts.read_text(encoding="utf-8")
    red_path = kb_root / "private" / "red_flags.md"
    yellow_path = kb_root / "private" / "yellow_flags.md"
    if force or _needs_update(red_path):
        red_path.write_text(_flags_from_prompt(text, kind="red"), encoding="utf-8")
        updated.append("private/red_flags.md")
    if force or _needs_update(yellow_path):
        yellow_path.write_text(_flags_from_prompt(text, kind="yellow"), encoding="utf-8")
        updated.append("private/yellow_flags.md")


def _flags_from_prompt(prompt: str, *, kind: str) -> str:
    title = "Red flags" if kind == "red" else "Yellow flags"
    label = "RED FLAGS" if kind == "red" else "YELLOW FLAGS"
    end_markers = ("YELLOW FLAGS", "*Output Rule*", "Output Rule", "---") if kind == "red" else (
        "*Output Rule*",
        "Output Rule",
        "---",
        "## PHASE 2",
    )
    block = _extract_section(
        prompt,
        start_markers=(label,),
        end_markers=end_markers,
    )
    lines = [f"# {title}", ""]
    if kind == "red":
        lines.append("Hard disqualifiers (from `private/prompts/job_fitness.md`).")
    else:
        lines.append("Caution flags (from `private/prompts/job_fitness.md`).")
    lines.append("")
    for raw in block.splitlines():
        m = re.match(r"^\*\s+(.*)", raw.strip())
        if m:
            lines.append(f"- {m.group(1).strip()}")
    lines.append("")
    return "\n".join(lines)
