from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request

from .bm25 import bm25_search
from .ollama_config import ollama_api_root

COLLECTION_NAME = "career_kb"
RAG_META_FILENAME = "rag_meta.json"
RRF_K = 60  # reciprocal rank fusion constant (standard default)


@dataclass
class RagIndexResult:
    index_db_path: Path
    chunk_count: int
    embedded_count: int
    embed_model: str
    collection: str


def build_rag_index(
    index_db_path: Path,
    chunks_path: Path,
    *,
    base_url: str,
    embed_model: str,
    batch_size: int = 16,
) -> RagIndexResult:
    """Embed chunks with Ollama and persist to ChromaDB at ``index_db_path``."""
    try:
        import chromadb  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "chromadb required for RAG index — pip install -r requirements-kb-extract.txt"
        ) from exc

    if not chunks_path.is_file():
        raise FileNotFoundError(f"chunks file missing: {chunks_path}")

    records = _load_chunks(chunks_path)
    index_db_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(index_db_path))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:  # noqa: BLE001 — collection may not exist
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    ids: list[str] = []
    documents: list[str] = []
    embeddings: list[list[float]] = []
    metadatas: list[dict[str, Any]] = []

    api_root = ollama_api_root(base_url)
    embedded = 0

    for batch in _batches(records, batch_size):
        texts = [str(r["text"]) for r in batch]
        batch_embeddings = _embed_batch(api_root, embed_model, texts)
        for rec, emb in zip(batch, batch_embeddings, strict=True):
            chunk_id = int(rec["id"])
            sha = str(rec.get("sha256") or "")
            doc_id = f"{sha[:16]}_{chunk_id}" if sha else f"chunk_{chunk_id}"
            ids.append(doc_id)
            documents.append(str(rec["text"]))
            embeddings.append(emb)
            metadatas.append(
                {
                    "source_path": str(rec.get("source_path") or ""),
                    "category_id": str(rec.get("category_id") or ""),
                    "chunk_id": chunk_id,
                }
            )
            embedded += 1

        if ids:
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            ids, documents, embeddings, metadatas = [], [], [], []

    meta = {
        "schema_version": 1,
        "collection": COLLECTION_NAME,
        "embed_model": embed_model,
        "ollama_api": api_root,
        "chunk_count": len(records),
        "embedded_count": embedded,
        "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "index_db_path": "index_db",
        "hybrid": True,
        "bm25_corpus": "_index/chunks.jsonl",
        "rrf_k": RRF_K,
    }
    meta_path = index_db_path / RAG_META_FILENAME
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    return RagIndexResult(
        index_db_path=index_db_path,
        chunk_count=len(records),
        embedded_count=embedded,
        embed_model=embed_model,
        collection=COLLECTION_NAME,
    )


def query_rag(
    index_db_path: Path,
    query: str,
    *,
    base_url: str,
    embed_model: str,
    n_results: int = 8,
) -> list[dict[str, Any]]:
    """Semantic search over the career KB index (for zazu_knowledge_manager / agents)."""
    import chromadb  # type: ignore[import-untyped]

    client = chromadb.PersistentClient(path=str(index_db_path))
    collection = client.get_collection(COLLECTION_NAME)
    api_root = ollama_api_root(base_url)
    q_emb = _embed_batch(api_root, embed_model, [query])[0]
    result = collection.query(query_embeddings=[q_emb], n_results=n_results)
    hits: list[dict[str, Any]] = []
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists, strict=False):
        hits.append({"text": doc, "metadata": meta, "distance": dist})
    return hits


def _chunk_key(rec: dict[str, Any]) -> str:
    """Stable fusion key — matches Chroma document id."""
    sha = str(rec.get("sha256") or "")
    cid = int(rec.get("id") or 0)
    return f"{sha[:16]}_{cid}" if sha else f"chunk_{cid}"


def query_rag_hybrid(
    index_db_path: Path,
    chunks_path: Path,
    query: str,
    *,
    base_url: str,
    embed_model: str,
    n_results: int = 8,
    rrf_k: int = RRF_K,
) -> list[dict[str, Any]]:
    """Hybrid retrieval: BM25 (keyword) + Chroma (vector), merged with RRF.

    BM25 catches exact tokens (company names, req ids); vectors catch paraphrase.
    Corpus: ``chunks.jsonl`` from ``extract_kb`` step 2.
    """
    records = _load_chunks(chunks_path)
    if not records:
        return []

    key_by_chunk_id = {int(r["id"]): _chunk_key(r) for r in records}

    vector_hits = query_rag(
        index_db_path,
        query,
        base_url=base_url,
        embed_model=embed_model,
        n_results=max(n_results, 12),
    )
    vector_ranked = [
        key_by_chunk_id[int(cid)]
        for hit in vector_hits
        if (cid := (hit.get("metadata") or {}).get("chunk_id")) is not None
        and int(cid) in key_by_chunk_id
    ]

    bm25_hits = bm25_search(chunks_path, query, top_k=max(n_results, 12))
    bm25_ranked = [key_by_chunk_id[h.chunk_id] for h in bm25_hits if h.chunk_id in key_by_chunk_id]

    scores: dict[str, float] = {}
    text_by_key = {key_by_chunk_id[int(r["id"])]: str(r.get("text") or "") for r in records}
    meta_by_key = {
        key_by_chunk_id[int(r["id"])]: {
            "source_path": str(r.get("source_path") or ""),
            "category_id": str(r.get("category_id") or ""),
            "chunk_id": int(r["id"]),
        }
        for r in records
    }

    for rank, key in enumerate(vector_ranked, 1):
        scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
    for rank, key in enumerate(bm25_ranked, 1):
        scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)

    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:n_results]
    return [
        {"text": text_by_key.get(key, ""), "metadata": meta_by_key.get(key, {}), "rrf_score": score}
        for key, score in merged
    ]


def _load_chunks(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def _batches(items: list[Any], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _embed_batch(api_root: str, model: str, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    url = f"{api_root}/api/embeddings"
    for text in texts:
        body = json.dumps({"model": model, "prompt": text}).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=180) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama embeddings failed ({exc.code}): {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Ollama unreachable at {url}: {exc}") from exc
        embedding = payload.get("embedding")
        if not embedding:
            raise RuntimeError(f"Ollama returned no embedding for model {model!r}")
        out.append(embedding)
    return out
