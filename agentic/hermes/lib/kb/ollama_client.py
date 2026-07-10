from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .config import OllamaConfig


def embed_texts(cfg: OllamaConfig, texts: list[str]) -> list[list[float]]:
    """Batch embed via Ollama /api/embeddings (one request per text)."""
    vectors: list[list[float]] = []
    for text in texts:
        vectors.append(_embed_one(cfg, text))
    return vectors


def _embed_one(cfg: OllamaConfig, text: str) -> list[float]:
    payload = json.dumps({"model": cfg.embed_model, "prompt": text}).encode("utf-8")
    url = f"{cfg.api_root}/api/embeddings"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama embeddings failed ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama unreachable at {url}: {exc}") from exc

    embedding = data.get("embedding")
    if not isinstance(embedding, list):
        raise RuntimeError(f"Ollama embeddings returned unexpected payload: {data!r}")
    return [float(x) for x in embedding]


def chat_json(cfg: OllamaConfig, system: str, user: str) -> str:
    """Single-turn chat; returns assistant message content."""
    payload: dict[str, Any] = {
        "model": cfg.model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    url = f"{cfg.api_root}/api/chat"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama chat failed ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama unreachable at {url}: {exc}") from exc

    message = data.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"Ollama chat returned unexpected payload: {data!r}")
    return content.strip()
