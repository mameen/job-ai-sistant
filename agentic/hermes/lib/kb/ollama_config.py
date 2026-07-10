from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip("\"'")
        os.environ[key] = value


def load_ollama_config(repo: Path) -> dict[str, str]:
    """Read Ollama settings from .env (same vars as manage.py setup)."""
    _load_dotenv(repo / ".env")
    roles_path = repo / "agentic" / "hermes" / "admin" / "config" / "hermes_roles.yaml"
    spec: dict[str, Any] = {}
    if roles_path.is_file():
        with roles_path.open(encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}

    target = (os.environ.get("OLLAMA_TARGET") or "").strip().lower()
    use_remote = target == "remote"
    block = (spec.get("ollama_remote") if use_remote else None) or spec.get("ollama") or {}

    base_url = os.environ.get("OLLAMA_BASE_URL") or block.get("base_url") or "http://localhost:11434/v1"
    embed_base_url = os.environ.get("OLLAMA_EMBED_BASE_URL") or base_url
    chat_model = os.environ.get("OLLAMA_MODEL") or block.get("default_model") or "llama3.1:latest"
    embed_model = os.environ.get("OLLAMA_EMBED_MODEL") or "nomic-embed-text"

    return {
        "base_url": base_url,
        "embed_base_url": embed_base_url,
        "chat_model": chat_model,
        "embed_model": embed_model,
    }


def ollama_api_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return root[:-3]
    return root
