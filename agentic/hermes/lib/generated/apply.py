"""Application Coach CLI helpers — proposal run + DOCX triplet."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .docx_io import write_application_triplet
from .naming import artifact_filename, proposal_run_dir


@dataclass
class ApplyBodies:
    """Text + template hints for the three application DOCX files."""

    resume_text: str
    cover_text: str
    brief_text: str
    cover_vault_path: Path | None = None  # prior application cover.docx to copy verbatim


def extract_job_id_from_url(url: str) -> str:
    """Best-effort ATS id from a job posting URL."""
    if not url:
        return "na"
    path = urlparse(url).path or url
    for pattern in (
        r"/jobs/(\d+)",
        r"/job/(\d+)",
        r"/job/([^/]+)/",
        r"req[_-]?id[=:](\w+)",
        r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    ):
        match = re.search(pattern, path, re.IGNORECASE)
        if match:
            return match.group(1)
    tail = path.rstrip("/").split("/")[-1]
    if tail and tail.isdigit():
        return tail
    slug_id = re.search(r"-(\d+)$", tail)
    if slug_id:
        return slug_id.group(1)
    return "na"


def _parse_opportunity_block(block: str) -> dict[str, str] | None:
    company = _field(block, "Company") or _title_company(block)
    title = _field(block, "Title") or _heading_title(block)
    url = _field(block, "URL")
    if title.startswith("#"):
        title = re.sub(r"^#+\s*\d+\.\s*", "", title)
        if "—" in title:
            title = title.split("—", 1)[0].strip()
        elif " - " in title:
            title = title.split(" - ", 1)[0].strip()
    if company and title:
        return {
            "company": company.strip(),
            "title": title.strip(),
            "url": url,
            "job_id": extract_job_id_from_url(url),
        }
    return None


def _block_has_actionable_verdict(block: str) -> bool:
    if re.search(r"\*\*(APPLY|CONSIDER)\b", block, re.IGNORECASE):
        return True
    if re.search(r"Verdict:\s*CONSIDER\b", block, re.IGNORECASE):
        return True
    if re.search(r"Recommendation:\s*\*\*APPLY\b", block, re.IGNORECASE):
        return True
    return False


def _strip_md_bold(text: str) -> str:
    return re.sub(r"\*+", "", text).strip()


def _find_url_for_company(text: str, company: str) -> str:
    needle = company.split()[0].lower()
    patterns = (
        r"-\s*(?:\*\*URL:\*\*|URL:)\s*(https?://\S+)",
        r"\|\s*\*\*URL\*\*\s*\|\s*(https?://\S+)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - 900)
            window = text[start : match.start()].lower()
            if needle in window:
                return match.group(1).rstrip(")")
    return ""


def _parse_recommendations_table(text: str) -> dict[str, str] | None:
    section = re.search(
        r"## Final Recommendations Summary.*?\n\|[^\n]+\n\|[-| ]+\|\n(?P<body>.*?)(?:\n\n|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section:
        return None
    for row in section.group("body").strip().splitlines():
        if not re.search(r"\*\*(APPLY|CONSIDER)\b", row, re.IGNORECASE):
            continue
        cells = [cell.strip() for cell in row.split("|")[1:-1]]
        if len(cells) < 4:
            continue
        company = _strip_md_bold(cells[1])
        company = re.sub(r"\s*\(#\d+\)", "", company).strip()
        title = _strip_md_bold(cells[2])
        url = _find_url_for_company(text, company)
        if company and title:
            return {
                "company": company,
                "title": title,
                "url": url,
                "job_id": extract_job_id_from_url(url),
            }
    return None


def _parse_highlights_list(text: str) -> dict[str, str] | None:
    section = re.search(
        r"###\s+HIGHLIGHTS:\s*\n(?P<body>.*?)(?:\n## |\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section:
        return None
    items = re.split(r"\n(?=\d+\.\s+\*\*)", section.group("body"))
    ranked: list[tuple[int, dict[str, str]]] = []
    for item in items:
        if not item.strip():
            continue
        header = re.match(
            r"\d+\.\s*\*\*(?P<company>[^*]+)\*\*\s*[—-]\s*(?P<title>.+)",
            item,
        )
        if not header:
            continue
        verdict_rank = 0
        if re.search(r"Recommendation:\s*\*\*APPLY\b", item, re.IGNORECASE):
            verdict_rank = 2
        elif re.search(r"\*\*CONSIDER\b", item, re.IGNORECASE):
            verdict_rank = 1
        else:
            continue
        url_match = re.search(r"-\s*URL:\s*(https?://\S+)", item, re.IGNORECASE)
        url = url_match.group(1).rstrip(")") if url_match else ""
        ranked.append(
            (
                verdict_rank,
                {
                    "company": header.group("company").strip(),
                    "title": header.group("title").strip(),
                    "url": url,
                    "job_id": extract_job_id_from_url(url),
                },
            )
        )
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[0][1]


def _split_opportunity_blocks(text: str) -> list[str]:
    return re.split(r"\n###\s+(?:\[\d+\]|\d+\.)\s+", text)[1:]


def _block_is_skipped(block: str) -> bool:
    if re.search(r"❌|RED FLAG", block.split("\n", 1)[0], re.IGNORECASE):
        return True
    if re.search(r"\*\*Recommendation\*\*[^\n]*SKIP\b", block, re.IGNORECASE):
        return True
    if re.search(r"\b(SKIP|SKIPPED|EXCLUDE)\b", block, re.IGNORECASE) and re.search(
        r"\*\*Recommendation\*\*", block, re.IGNORECASE
    ):
        return True
    return False


def _block_has_consider_recommendation(block: str) -> bool:
    if re.search(r"\*\*Recommendation\*\*[^\n]*(APPLY|CONSIDER)\b", block, re.IGNORECASE):
        return True
    if re.search(r"\bVerdict:\s*(APPLY|CONSIDER)\b", block, re.IGNORECASE):
        return True
    return False


def _is_skip_recommendation(cell: str) -> bool:
    if re.search(r"\b(SKIP|SKIPPED|EXCLUDE)\b", cell, re.IGNORECASE):
        return True
    if re.search(r"\bLOWER\b", cell, re.IGNORECASE) and not re.search(
        r"\b(APPLY|CONSIDER)\b", cell, re.IGNORECASE
    ):
        return True
    return False


def _is_actionable_recommendation(cell: str) -> bool:
    return bool(re.search(r"\b(APPLY|CONSIDER)\b", cell, re.IGNORECASE)) and not _is_skip_recommendation(
        cell
    )


def _clean_company_token(company: str) -> str:
    company = re.sub(r"^[^\w]+\s*", "", company.strip())
    company = re.sub(r"\s*\([^)]*\)", "", company).strip()
    return company


def _title_tokens_match(hint: str, full: str) -> bool:
    hint_tokens = [token for token in re.findall(r"[a-z0-9]+", hint.lower()) if len(token) > 2]
    full_lower = full.lower()
    if not hint_tokens:
        return True
    generic = {
        "manager",
        "software",
        "engineering",
        "senior",
        "lead",
        "team",
        "inc",
    }
    distinctive = [token for token in hint_tokens if token not in generic]
    if distinctive:
        return all(token in full_lower for token in distinctive)
    return all(token in full_lower for token in hint_tokens)


def _find_detail_posting(text: str, company: str, title_hint: str = "") -> dict[str, str]:
    needle = _company_match_key(company)
    if not needle:
        return {}
    for block in _split_opportunity_blocks(text):
        if _block_is_skipped(block):
            continue
        meta = _parse_posting_block(block)
        if not meta:
            continue
        block_key = _company_match_key(meta["company"])
        if block_key != needle and needle not in block_key and block_key not in needle:
            continue
        if title_hint and not _title_tokens_match(title_hint, meta["title"]):
            continue
        if re.search(r"\*\*RED\b|🔴\s*RED", block, re.IGNORECASE):
            continue
        return meta
    return {}


def _parse_candidate_opportunity_blocks(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for block in _split_opportunity_blocks(text):
        if _block_is_skipped(block):
            continue
        if not _block_has_consider_recommendation(block):
            continue
        meta = _parse_posting_block(block)
        if meta:
            rows.append(meta)
    return rows


def _summary_row_to_meta(text: str, company: str, title_hint: str) -> dict[str, str]:
    detail = _find_detail_posting(text, company, title_hint)
    title = detail.get("title") or title_hint
    url = detail.get("url", "")
    return {
        "company": _clean_company_token(company),
        "title": title,
        "url": url,
        "job_id": detail.get("job_id") or extract_job_id_from_url(url),
    }


def _parse_summary_table_rows(text: str) -> list[dict[str, str]]:
    section = re.search(
        r"## Summary Table\s*\n\|[^\n]+\n\|[-| ]+\|\n(?P<body>.*?)(?:\n---|\n## |\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section:
        return []
    rows: list[dict[str, str]] = []
    for line in section.group("body").strip().splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) < 4:
            continue
        recommendation = cells[-1]
        if not _is_actionable_recommendation(recommendation):
            continue
        company = _clean_company_token(_strip_md_bold(cells[1]))
        title_hint = _strip_md_bold(cells[2])
        rows.append(_summary_row_to_meta(text, company, title_hint))
    return rows


def parse_search_consider_all(search_path: Path) -> list[dict[str, str]]:
    """Return all APPLY/CONSIDER rows from search_latest.md."""
    if not search_path.is_file():
        return []
    text = search_path.read_text(encoding="utf-8")
    rows = _parse_summary_table_rows(text)
    if rows:
        return rows
    rows = _parse_candidate_opportunity_blocks(text)
    if rows:
        return rows
    single = parse_search_consider(search_path)
    return [single] if single else []


def _parse_posting_heading(line: str) -> tuple[str, str]:
    line = line.strip()
    if "—" in line:
        company, title = line.split("—", 1)
        return _clean_company_token(company), title.strip()
    if " - " in line:
        company, title = line.split(" - ", 1)
        return _clean_company_token(company), title.strip()
    return "", line.strip()


def _parse_posting_block(block: str) -> dict[str, str] | None:
    heading = block.split("\n", 1)[0].strip()
    heading = re.sub(r"^\[\d+\]\s*", "", heading)
    company, title = _parse_posting_heading(heading)
    company = _clean_company_token(_field(block, "Company") or company)
    title = _field(block, "Title") or title
    url = _field(block, "URL")
    if company and title:
        return {
            "company": company.strip(),
            "title": title.strip(),
            "url": url,
            "job_id": extract_job_id_from_url(url),
        }
    return None


def _parse_greenfield_table(text: str) -> dict[str, str] | None:
    section = re.search(
        r"### Companies Where Candidates Can Consider Fresh Applications.*?\n"
        r"\|[^\n]+\n\|[-| ]+\|\n(?P<body>.*?)(?:\n###|\n## |\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section:
        return None
    for row in section.group("body").strip().splitlines():
        if re.search(r"\*\*SKIP\b", row, re.IGNORECASE):
            continue
        if not re.search(r"\*\*(APPLY|CONSIDER)\b", row, re.IGNORECASE):
            continue
        cells = [cell.strip() for cell in row.split("|")[1:-1]]
        if len(cells) < 4:
            continue
        company = _strip_md_bold(cells[0])
        title = _strip_md_bold(cells[1])
        url = _find_url_for_company(text, company)
        if company and title:
            return {
                "company": company,
                "title": title,
                "url": url,
                "job_id": extract_job_id_from_url(url),
            }
    return None


def _parse_numbered_postings(text: str) -> dict[str, str] | None:
    blocks = re.split(r"\n###\s+\d+\.\s+", text)
    ranked: list[tuple[int, dict[str, str]]] = []
    for block in blocks[1:]:
        if re.search(r"\*\*SKIP\b", block, re.IGNORECASE):
            continue
        if re.search(r"Prior Application:\s*\*\*YELLOW\b", block, re.IGNORECASE):
            continue
        verdict_rank = 0
        if re.search(r"\*\*APPLY\b", block, re.IGNORECASE):
            verdict_rank = 2
        elif re.search(r"\*\*(CONSIDER|GREENFIELD)\b", block, re.IGNORECASE):
            verdict_rank = 1
        elif re.search(r"Prior Application:\s*\*\*GREENFIELD\b", block, re.IGNORECASE):
            verdict_rank = 1
        else:
            continue
        meta = _parse_posting_block(block)
        if meta:
            ranked.append((verdict_rank, meta))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[0][1]


def parse_search_consider(search_path: Path) -> dict[str, str] | None:
    """Return metadata for the top greenfield APPLY/CONSIDER hit in search_latest.md."""
    if not search_path.is_file():
        return None
    text = search_path.read_text(encoding="utf-8")

    rows = _parse_summary_table_rows(text)
    if rows:
        return rows[0]

    for parser in (
        _parse_greenfield_table,
        _parse_highlights_list,
        _parse_recommendations_table,
        _parse_numbered_postings,
    ):
        meta = parser(text)
        if meta:
            return meta

    block_match = re.search(r"##\s+1\..*?(?=##\s+2\.|\Z)", text, re.DOTALL)
    if not block_match:
        block_match = re.search(r"###\s+1\..*?(?=###\s+2\.|\Z)", text, re.DOTALL)
    detail_block = block_match.group(0) if block_match else ""

    if detail_block and _block_has_actionable_verdict(detail_block):
        meta = _parse_opportunity_block(detail_block)
        if meta:
            return meta

    table_match = re.search(
        r"\|\s*1\s*\|\s*(?P<title>[^|]+)\|\s*(?P<company>[^|]+)\|(?:[^|]*\|)+\s*\*\*(?:APPLY|CONSIDER)[^|]*\*\*",
        text,
        re.IGNORECASE,
    )
    if table_match:
        url = _field(detail_block, "URL") if detail_block else ""
        return {
            "company": table_match.group("company").strip(),
            "title": table_match.group("title").strip(),
            "url": url,
            "job_id": extract_job_id_from_url(url),
        }
    return None


def _field(block: str, label: str) -> str:
    match = re.search(rf"-\s*\*\*{re.escape(label)}:\*\*\s*(.+)", block)
    if match:
        return match.group(1).strip()
    match = re.search(
        rf"\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*(.+?)\s*\|",
        block,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _heading_title(block: str) -> str:
    line = block.split("\n", 1)[0]
    if "—" in line:
        return line.split("—", 1)[0].strip()
    if " - " in line:
        return line.split(" - ", 1)[0].strip()
    return line.strip()


def _title_company(block: str) -> str:
    line = block.split("\n", 1)[0]
    if "—" in line:
        return line.split("—", 1)[-1].strip()
    return ""


def _strip_md_header(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_content = False
    for line in lines:
        if not in_content:
            if line.strip().lower() == "## content":
                in_content = True
            continue
        out.append(line)
    body = "\n".join(out).strip()
    return body or text.strip()


def _read_kb_md(kb_root: Path, rel: str) -> str:
    path = kb_root / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _company_match_key(company: str) -> str:
    base = re.sub(r"\s*\([^)]*\)", "", company or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", base)


def find_company_vault_cover(kb_root: Path, company: str) -> Path | None:
    """Return ``cover.docx`` from a prior ``application_history/.../Company/`` folder."""
    history = kb_root / "private" / "application_history"
    if not history.is_dir():
        return None
    needle = _company_match_key(company)
    if not needle:
        return None
    best: Path | None = None
    for cover in history.rglob("cover.docx"):
        parent_key = _company_match_key(cover.parent.name)
        if parent_key == needle or needle in parent_key or parent_key in needle:
            best = cover
    return best


def _load_vault_cover_text(cover_path: Path) -> str:
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError:
        return ""
    doc = Document(str(cover_path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _search_fit_note(repo: Path, company: str) -> str:
    """Pull fit note for *company* from ``search_latest.md`` if present."""
    search_path = repo / "agentic" / "hermes" / ".generated" / "researched" / "search_latest.md"
    if not search_path.is_file():
        return ""
    text = search_path.read_text(encoding="utf-8")
    needle = _company_match_key(company)
    blocks = re.split(r"\n###\s+\d+\.\s+", text)
    for block in blocks[1:]:
        block_key = _company_match_key(_field(block, "Company") or _title_company(block))
        if needle and block_key and (needle in block_key or block_key in needle):
            fit = _field(block, "Fit note")
            flags = _field(block, "Flags")
            loc = _field(block, "Location")
            parts = [p for p in (fit, flags, loc) if p]
            return " ".join(parts)
    return ""


def _resume_highlight_bullets(master_md: str, *, limit: int = 8) -> list[str]:
    """Extract recent-role bullet lines from master resume markdown."""
    body = _strip_md_header(master_md)
    bullets: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] in "-•*":
            bullets.append(stripped.lstrip("-•* ").strip())
        elif re.match(r"^(Lead|Owned|Built|Drove|Contributed|Partnered|Senior|Engineering Manager)", stripped):
            bullets.append(stripped)
        if len(bullets) >= limit:
            break
    return bullets


def _md_section_bullets(md: str, max_items: int = 6) -> list[str]:
    items: list[str] = []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("- "):
            items.append(s[2:].strip())
        if len(items) >= max_items:
            break
    return items


def build_application_brief_md(
    kb_root: Path,
    repo: Path,
    *,
    company: str,
    job_title: str,
    job_id: str,
    url: str = "",
) -> str:
    """Build Application Brief section patch from Career KB + latest search research."""
    opp_lines = [
        f"Role: {job_title}",
        f"Company: {company}",
        f"Job ID: {job_id}",
    ]
    if url:
        opp_lines.append(f"Posting: {url}")

    fit = _search_fit_note(repo, company)
    if fit:
        opp_lines.append(f"Researcher assessment: {fit}")

    prior = find_company_vault_cover(kb_root, company)
    if prior:
        opp_lines.append(
            f"Prior application on file: {prior.relative_to(kb_root).as_posix()}"
        )
        opp_lines.append(
            "Adjust messaging for this requisition; do not treat as a greenfield employer."
        )

    flag_lines: list[str] = []
    yellow = _read_kb_md(kb_root, "private/yellow_flags.md")
    red = _read_kb_md(kb_root, "private/red_flags.md")
    for item in _md_section_bullets(yellow, 4):
        flag_lines.append(f"Yellow: {item}")
    for item in _md_section_bullets(red, 3):
        flag_lines.append(f"Red (avoid): {item}")
    if not flag_lines:
        flag_lines.append("Review job_fitness.md guardrails against the JD before final send.")

    level_lines = [
        f"Posted title: {job_title}",
        "Candidate level: Senior Software Engineering Manager (Adobe, 18 engineers across two teams).",
        "Confirm internal leveling, span of control, and compensation band during screening.",
    ]

    employer_lines = [
        f"{company} — summarize mission, product surface, and team scope from search_latest.md.",
        "Pull culture, funding stage, and remote/hybrid policy from the researcher report.",
    ]

    match_lines: list[str] = []
    master = _read_kb_md(kb_root, "public/master_resume.md")
    for bullet in _resume_highlight_bullets(master):
        match_lines.append(bullet)

    jd_lines: list[str] = []
    skills = _read_kb_md(kb_root, "public/skills.md")
    for row in skills.splitlines():
        s = row.strip()
        if s and not s.startswith("#") and ":" in s:
            jd_lines.append(s)

    goals = _read_kb_md(kb_root, "private/career_goals.md")
    for item in _md_section_bullets(goals, 3):
        jd_lines.append(f"Career goal alignment: {item}")

    gap_lines: list[str] = []
    for item in _md_section_bullets(yellow, 3):
        gap_lines.append(f"Yellow concern: {item} — probe team culture and pace in interviews.")
    if not gap_lines:
        gap_lines.append("Identify top 3 JD gaps vs KB; document honest mitigations (no fabrication).")

    star_lines = [
        "TyCo / Tidy-up (Adobe): GenAI typography — escape rate 49% to 19%, evaluation loops, cross-team delivery.",
        "mChat (Moderna): Internal LLM platform — 75% adoption, hybrid RAG + RAGAS, AWS/ChromaDB foundation.",
        "Platform reliability (Tableau): CI/CD, cloud migration, Browser Everywhere — enterprise release discipline.",
    ]

    interview_lines = [
        "Expect platform/infrastructure ownership, SLO culture, and team-building at 6–10+ engineers.",
        "Prepare: incident response, roadmap prioritization, stakeholder alignment (PM/Design/Research).",
        "Ask: on-call model, platform vs product split, AI roadmap, team tenure/stability.",
    ]

    comp_lines = [
        "Confirm level (Manager vs Senior Manager) and Bellevue hybrid vs remote US.",
        "Verify requisition is distinct from prior applications in vault.",
        "Run --coach to tailor resume/cover/brief patches; merge is deterministic locally.",
    ]

    rec_lines: list[str] = []
    if fit:
        rec_lines.append(f"Researcher signal: {fit}")
    rec_lines.append("Coach must complete RECOMMENDATION with APPLY / CONSIDER / SKIP and top 3 reasons.")

    sections: list[tuple[str, list[str]]] = [
        ("OPPORTUNITY_INTELLIGENCE", opp_lines),
        ("FLAG_ANALYSIS", flag_lines),
        ("LEVEL_MAPPING", level_lines),
        ("EMPLOYER_SUMMARY", employer_lines),
        ("TOP_MATCHING_EXPERIENCE", match_lines),
        ("JD_ALIGNMENT", jd_lines),
        ("GAPS_MITIGATIONS", gap_lines),
        ("STAR_STORIES", star_lines),
        ("INTERVIEW_INTELLIGENCE", interview_lines),
        ("COMPENSATION_NEXT_STEPS", comp_lines),
        ("RECOMMENDATION", rec_lines),
    ]

    blocks: list[str] = []
    for section_id, items in sections:
        blocks.append(f"## {section_id}")
        blocks.append("")
        for item in items:
            blocks.append(f"- {item}" if not item.startswith("- ") else item)
        blocks.append("")
    return "\n".join(blocks).strip()


def load_apply_bodies(
    kb_root: Path,
    repo: Path,
    *,
    company: str,
    job_title: str,
    job_id: str = "na",
    url: str = "",
) -> ApplyBodies:
    """Load resume/cover/brief content from Career KB (real data, no mocks)."""
    master_path = kb_root / "public" / "master_resume.md"
    if master_path.is_file():
        resume_text = _strip_md_header(master_path.read_text(encoding="utf-8"))
    else:
        resume_text = ""

    cover_vault = find_company_vault_cover(kb_root, company)
    if cover_vault is not None:
        cover_text = _load_vault_cover_text(cover_vault)
    else:
        cover_text = ""  # copy cover.docx template in docx_io

    brief_text = build_application_brief_md(
        kb_root,
        repo,
        company=company,
        job_title=job_title,
        job_id=job_id,
        url=url,
    )
    return ApplyBodies(
        resume_text=resume_text,
        cover_text=cover_text,
        brief_text=brief_text,
        cover_vault_path=cover_vault,
    )


def write_proposal_triplet(
    *,
    kb_root: Path,
    repo: Path,
    proposals_root: Path,
    company: str,
    job_title: str,
    job_id: str,
    job_date: str | None = None,
    run_prefix: str | None = None,
    url: str = "",
) -> tuple[Path, list[Path]]:
    """Create proposals/<run>/ and write the three DOCX files."""
    date_part = job_date or datetime.now().strftime("%Y%m%d")
    run_dir = proposal_run_dir(proposals_root, run_prefix)
    run_dir.mkdir(parents=True, exist_ok=True)

    bodies = load_apply_bodies(
        kb_root,
        repo,
        company=company,
        job_title=job_title,
        job_id=job_id or "na",
        url=url,
    )
    paths = write_application_triplet(
        kb_root=kb_root,
        run_dir=run_dir,
        company=company,
        job_title=job_title,
        job_id=job_id or "na",
        job_date=date_part,
        resume_text=bodies.resume_text,
        cover_text=bodies.cover_text,
        brief_text=bodies.brief_text,
        resume_from_template=True,
        cover_from_template=bodies.cover_vault_path,
    )
    if bodies.brief_text.strip():
        brief_name = artifact_filename(
            company=company,
            job_title=job_title,
            job_id=job_id or "na",
            job_date=date_part,
            kind="brief",
        )
        (run_dir / f"{Path(brief_name).stem}_seed.md").write_text(
            bodies.brief_text, encoding="utf-8"
        )
    return run_dir, paths


def planned_filenames(
    *,
    company: str,
    job_title: str,
    job_id: str,
    job_date: str,
) -> dict[str, str]:
    return {
        kind: artifact_filename(
            company=company,
            job_title=job_title,
            job_id=job_id,
            job_date=job_date,
            kind=kind,
        )
        for kind in ("resume", "cover", "brief")
    }
