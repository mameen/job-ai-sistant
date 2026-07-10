"""BM25 keyword retrieval over ``chunks.jsonl``.

Used with Chroma vector search in ``query_rag_hybrid()`` (reciprocal rank fusion).
Corpus is rebuilt from ``chunks.jsonl`` on each query — fine for ~few-k chunks;
no separate index file required at this scale.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

# Okapi BM25 tuning (standard defaults)
BM25_K1 = 1.5
BM25_B = 0.75

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Bm25Hit:
    chunk_id: int
    source_path: str
    text: str
    score: float


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def bm25_search(
    chunks_path: Path,
    query: str,
    *,
    top_k: int = 10,
) -> list[Bm25Hit]:
    """Score all chunks with BM25; return top_k by descending score."""
    records = _load_chunks(chunks_path)
    if not records:
        return []

    query_terms = tokenize(query)
    if not query_terms:
        return []

    # Tokenize corpus once
    docs: list[list[str]] = []
    for rec in records:
        docs.append(tokenize(str(rec.get("text") or "")))

    n_docs = len(docs)
    avg_dl = sum(len(d) for d in docs) / n_docs if n_docs else 0.0

    # Document frequency per query term
    df: dict[str, int] = {}
    for term in set(query_terms):
        df[term] = sum(1 for d in docs if term in d)

    scored: list[tuple[int, float]] = []
    for idx, doc_tokens in enumerate(docs):
        dl = len(doc_tokens)
        if dl == 0:
            continue
        tf_map: dict[str, int] = {}
        for t in doc_tokens:
            tf_map[t] = tf_map.get(t, 0) + 1

        score = 0.0
        for term in query_terms:
            if term not in tf_map:
                continue
            tf = tf_map[term]
            idf = math.log(1 + (n_docs - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avg_dl)
            score += idf * (tf * (BM25_K1 + 1)) / denom

        if score > 0:
            scored.append((idx, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    hits: list[Bm25Hit] = []
    for idx, score in scored[:top_k]:
        rec = records[idx]
        hits.append(
            Bm25Hit(
                chunk_id=int(rec["id"]),
                source_path=str(rec.get("source_path") or ""),
                text=str(rec.get("text") or ""),
                score=score,
            )
        )
    return hits


def _load_chunks(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
