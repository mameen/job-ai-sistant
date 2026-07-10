from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str
    model: str
    embed_model: str
    context_length: int

    @property
    def api_root(self) -> str:
        """Ollama native API root (without /v1)."""
        return self.base_url.rstrip("/").removesuffix("/v1")


def load_ollama_config(repo: Path) -> OllamaConfig:
    """Resolve Ollama settings from env (same vars as manage.py) with yaml fallback."""
    roles_path = repo / "agentic" / "hermes" / "admin" / "config" / "hermes_roles.yaml"
    block: dict[str, Any] = {}
    if roles_path.is_file():
        with roles_path.open(encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        target = (os.environ.get("OLLAMA_TARGET") or "").strip().lower()
        key = "ollama_remote" if target == "remote" else "ollama"
        block = spec.get(key) or spec.get("ollama") or {}

    base_url = os.environ.get("OLLAMA_BASE_URL") or block.get("base_url") or "http://localhost:11434/v1"
    model = os.environ.get("OLLAMA_MODEL") or block.get("default_model") or "llama3.1:latest"
    embed_model = os.environ.get("OLLAMA_EMBED_MODEL") or "nomic-embed-text"
    ctx_raw = os.environ.get("OLLAMA_CONTEXT_LENGTH") or str(block.get("context_length") or 131072)
    return OllamaConfig(
        base_url=base_url,
        model=model,
        embed_model=embed_model,
        context_length=int(ctx_raw),
    )
