"""Chunk extracted vault text for hybrid RAG (BM25 + vector).

Output: ``_index/chunks.jsonl`` — one JSON object per line, consumed by
``build_rag_index()`` (Chroma) and ``bm25_search()`` (keyword leg).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
CHUNKS_FILENAME = "chunks.jsonl"


def build_chunks(index_dir: Path, catalog: dict[str, Any]) -> tuple[Path, int]:
    """Write RAG-ready chunks from extracted text. Returns (path, chunk_count)."""
    out = index_dir / CHUNKS_FILENAME
    documents: dict[str, Any] = catalog.get("documents") or {}
    lines: list[str] = []
    chunk_id = 0

    for rel, doc in sorted(documents.items()):
        extracted_rel = doc.get("extracted_text_path")
        if not extracted_rel:
            continue
        text_path = index_dir / extracted_rel
        if not text_path.is_file():
            continue
        text = text_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        for piece in _chunk_text(text):
            chunk_id += 1
            record = {
                "id": chunk_id,
                "source_path": rel,
                "category_id": doc.get("category_id"),
                "sha256": doc.get("sha256"),
                "extract_backend": doc.get("extract_backend"),
                "text": piece,
            }
            lines.append(json.dumps(record, ensure_ascii=False))

    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return out, chunk_id


def _chunk_text(text: str) -> list[str]:
    normalized = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(normalized) <= CHUNK_SIZE:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + CHUNK_SIZE)
        if end < len(normalized):
            break_at = normalized.rfind("\n\n", start, end)
            if break_at > start + CHUNK_SIZE // 2:
                end = break_at
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(normalized):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def chunks_summary(index_dir: Path) -> dict[str, Any]:
    path = index_dir / CHUNKS_FILENAME
    if not path.is_file():
        return {"chunk_count": 0, "path": None}
    count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return {
        "chunk_count": count,
        "path": f"_index/{CHUNKS_FILENAME}",
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
