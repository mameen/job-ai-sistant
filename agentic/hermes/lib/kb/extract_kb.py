"""Career KB vault extraction pipeline (``manage.py kb-extract``).

Pipeline (5 steps)
------------------
1. **Scan + classify** — walk ``.kb/``; extract text (basic → unstructured → OCR);
   classify with **longest ``target_dir`` prefix** (``application_history`` beats ``private``).
2. **Chunk** — write ``_index/chunks.jsonl`` for RAG (~1k chars, overlap 150).
3. **Vector index** — Ollama embeddings → ChromaDB at ``.kb/index_db/``.
4. **Registry sync** — import ``application_history/YYYYMMDD/Company/`` → SQLite
   ``_index/applications.db`` (dedupe for search/apply).
5. **Organize** — distill canonical ``public/*.md`` from best resume sources.

Retrieval (used by ``search`` preflight)
----------------------------------------
``query_rag_hybrid()`` fuses BM25 keyword scores + Chroma vectors (RRF) over the
same ``chunks.jsonl`` corpus. See ``search_preflight.py``.

Entry points: ``manage.py kb-extract``, ``bootstrap --extract-kb``, zazu_knowledge_manager.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .application_registry import applications_db_path, import_vault_folders
from .catalog import load_catalog, save_catalog
from .chunks import build_chunks, chunks_summary
from .ollama_config import load_ollama_config
from .organize import organize_kb
from .paths import INDEX_DB_DIR_NAME, repo_kb_paths
from .rag_index import RRF_K, build_rag_index
from .scan import scan_kb


@dataclass
class ExtractKbResult:
    """Summary returned after a full ``extract_kb`` run."""

    scanned: int
    deep_extracted: int
    chunk_count: int
    embedded_count: int
    registry_imported: int
    organized_files: list[str]
    catalog_path: Path
    chunks_path: Path
    index_db_path: Path
    applications_db_path: Path
    embed_model: str


def extract_kb(
    repo: Path,
    *,
    scan_id: str | None = None,
    force_organize: bool = False,
    skip_rag: bool = False,
    skip_registry: bool = False,
) -> ExtractKbResult:
    """Run the full vault pipeline (scan → chunk → index → registry → organize)."""
    kb_root, index_dir, _inbox, index_db_path, _taxonomy = repo_kb_paths(repo)
    if not kb_root.is_dir():
        raise FileNotFoundError(f"Career KB missing: {kb_root}")

    scan_id = scan_id or datetime.now().strftime("%Y%m%d%H%M%S")
    index_db_path.mkdir(parents=True, exist_ok=True)
    apps_db = applications_db_path(index_dir)

    # --- 1. scan + deep extract + classify (longest-prefix taxonomy) ---
    print("  [1/5] scan + deep extract + classify …")
    scan_result = scan_kb(
        repo,
        scan_id=scan_id,
        force_extract=True,
        deep_extract=True,
    )

    catalog = load_catalog(index_dir)
    deep_count = sum(
        1
        for doc in (catalog.get("documents") or {}).values()
        if doc.get("extract_backend") in {"unstructured", "tesseract"}
    )

    # --- 2. chunk corpus for BM25 + vector RAG ---
    print("  [2/5] chunk for hybrid RAG …")
    chunks_path, chunk_count = build_chunks(index_dir, catalog)

    embedded_count = 0
    embed_model = ""
    if skip_rag:
        print("  [3/5] vector index skipped (--skip-rag); BM25 uses chunks.jsonl only")
    else:
        print("  [3/5] embed + ChromaDB vector index …")
        ollama = load_ollama_config(repo)
        embed_model = ollama["embed_model"]
        rag = build_rag_index(
            index_db_path,
            chunks_path,
            base_url=ollama["embed_base_url"],
            embed_model=embed_model,
        )
        embedded_count = rag.embedded_count

    # --- 4. sync application registry from vault folders ---
    registry_imported = 0
    if skip_registry:
        print("  [4/5] application registry skipped (--skip-registry)")
    else:
        print("  [4/5] sync application registry (SQLite) …")
        imported = import_vault_folders(kb_root, apps_db)
        registry_imported = len(imported)

    # --- 5. canonical markdown ---
    print("  [5/5] organize canonical markdown …")
    org = organize_kb(kb_root, catalog, index_dir, force=force_organize)

    catalog["chunks"] = chunks_summary(index_dir)
    catalog["rag"] = {
        "index_db": INDEX_DB_DIR_NAME,
        "embed_model": embed_model or None,
        "embedded_count": embedded_count,
        "chunk_count": chunk_count,
        "hybrid": True,
        "bm25_corpus": "_index/chunks.jsonl",
        "rrf_k": RRF_K,
    }
    catalog["applications_db"] = "_index/applications.db"
    catalog_path = save_catalog(index_dir, catalog, scan_id=scan_id)

    return ExtractKbResult(
        scanned=scan_result.scanned,
        deep_extracted=deep_count,
        chunk_count=chunk_count,
        embedded_count=embedded_count,
        registry_imported=registry_imported,
        organized_files=org.updated_files,
        catalog_path=catalog_path,
        chunks_path=chunks_path,
        index_db_path=index_db_path,
        applications_db_path=apps_db,
        embed_model=embed_model,
    )
