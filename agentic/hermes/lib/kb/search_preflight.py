"""Search preflight — hybrid KB retrieval + path hits for zazu_researcher prompts.

Runs **before** Hermes ``search`` so the researcher sees deterministic context:
SQLite registry, BM25+vector RAG excerpts, and ``application_history`` paths.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .application_registry import applications_db_path, format_registry_summary
from .ollama_config import load_ollama_config
from .rag_index import query_rag_hybrid

# Skip when matching catalog paths to the user query
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "for",
        "to",
        "in",
        "at",
        "of",
        "on",
        "with",
        "manager",
        "engineering",
        "software",
        "senior",
        "role",
        "job",
        "remote",
        "hybrid",
    }
)


@dataclass
class SearchPreflight:
    query: str
    registry_block: str
    rag_block: str
    path_block: str

    def as_prompt_sections(self) -> str:
        return (
            f"## Application registry (SQLite)\n{self.registry_block}\n\n"
            f"## KB hybrid retrieval (BM25 + vector RAG)\n{self.rag_block}\n\n"
            f"## Application history path hits\n{self.path_block}"
        )


def _query_tokens(query: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    return [t for t in tokens if len(t) > 2 and t not in _STOPWORDS]


def path_hits_from_catalog(
    catalog_path: Path,
    query: str,
    *,
    limit: int = 12,
) -> list[str]:
    """Return vault paths (especially application_history) matching query tokens."""
    if not catalog_path.is_file():
        return []

    tokens = _query_tokens(query)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    documents: dict = catalog.get("documents") or {}

    scored: list[tuple[int, str]] = []
    for rel in documents:
        rel_lower = rel.lower()
        score = 0
        if "application_history" in rel_lower:
            score += 2
        for tok in tokens:
            if tok in rel_lower:
                score += 3
        if score > 0:
            scored.append((score, rel))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [rel for _, rel in scored[:limit]]


def company_path_hits(query: str, catalog_path: Path) -> list[str]:
    """Company folders under application_history matching query tokens."""
    hits = path_hits_from_catalog(catalog_path, query, limit=20)
    folders: list[str] = []
    seen: set[str] = set()
    for rel in hits:
        parts = Path(rel).parts
        if "application_history" not in parts:
            continue
        for i, part in enumerate(parts):
            if re.fullmatch(r"\d{8}", part) and i + 1 < len(parts):
                folder_rel = str(Path(*parts[: i + 2]))
                if folder_rel not in seen:
                    seen.add(folder_rel)
                    folders.append(folder_rel)
                break
    return folders[:12]


def format_hybrid_hits(hits: list[dict], *, max_chars: int = 400) -> str:
    if not hits:
        return "(no hybrid hits — run kb-extract to build index)"
    lines: list[str] = []
    for i, hit in enumerate(hits, 1):
        meta = hit.get("metadata") or {}
        path = meta.get("source_path") or "?"
        text = (hit.get("text") or "").replace("\n", " ")[:max_chars]
        rrf = hit.get("rrf_score")
        tail = f" rrf={rrf:.4f}" if isinstance(rrf, (int, float)) else ""
        lines.append(f"{i}. `{path}`{tail}\n   {text}")
    return "\n".join(lines)


def build_search_preflight(
    repo: Path,
    query: str,
    *,
    n_hybrid: int = 8,
) -> SearchPreflight:
    """Build deterministic KB context blocks for ``manage.py search``."""
    kb_root = repo / "agentic" / "hermes" / ".kb"
    index_dir = kb_root / "_index"
    index_db = kb_root / "index_db"
    chunks_path = index_dir / "chunks.jsonl"
    catalog_path = index_dir / "catalog.json"

    registry_block = format_registry_summary(applications_db_path(index_dir))

    rag_block = "(RAG index missing — run kb-extract)"
    if index_db.is_dir() and chunks_path.is_file():
        try:
            ollama = load_ollama_config(repo)
            hits = query_rag_hybrid(
                index_db,
                chunks_path,
                query,
                base_url=ollama["embed_base_url"],
                embed_model=ollama["embed_model"],
                n_results=n_hybrid,
            )
            rag_block = format_hybrid_hits(hits)
        except Exception as exc:  # noqa: BLE001 — surface embed/chroma errors in prompt
            rag_block = f"(hybrid retrieval failed: {exc})"

    folders = company_path_hits(query, catalog_path)
    if folders:
        path_block = "\n".join(f"- `{f}/`" for f in folders)
    else:
        paths = path_hits_from_catalog(catalog_path, query)
        path_block = "\n".join(f"- `{p}`" for p in paths) if paths else "(none)"

    return SearchPreflight(
        query=query,
        registry_block=registry_block,
        rag_block=rag_block,
        path_block=path_block,
    )
