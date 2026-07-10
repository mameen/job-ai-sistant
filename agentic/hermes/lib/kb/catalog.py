from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .paths import CATALOG_FILENAME, EXTRACTED_DIR_NAME, RELOCATION_FILENAME


@dataclass
class CatalogDocument:
    sha256: str
    size_bytes: int
    mtime: str
    mime: str
    extension: str
    layer: str
    category_id: str
    category_confidence: float
    placement_ok: bool
    suggested_path: str | None
    extracted_text_path: str | None
    extract_status: str
    extract_notes: str
    extract_backend: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
            "mime": self.mime,
            "extension": self.extension,
            "layer": self.layer,
            "category_id": self.category_id,
            "category_confidence": round(self.category_confidence, 3),
            "placement_ok": self.placement_ok,
            "suggested_path": self.suggested_path,
            "extracted_text_path": self.extracted_text_path,
            "extract_status": self.extract_status,
            "extract_notes": self.extract_notes,
            "extract_backend": self.extract_backend,
        }


def load_catalog(index_dir: Path) -> dict[str, Any]:
    path = index_dir / CATALOG_FILENAME
    if not path.is_file():
        return {"schema_version": 1, "documents": {}}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("schema_version", 1)
    data.setdefault("documents", {})
    return data


def save_catalog(index_dir: Path, catalog: dict[str, Any], *, scan_id: str | None = None) -> Path:
    index_dir.mkdir(parents=True, exist_ok=True)
    catalog["schema_version"] = 1
    catalog["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if scan_id:
        catalog["scan_id"] = scan_id
    out = index_dir / CATALOG_FILENAME
    out.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def extracted_text_path(index_dir: Path, sha256: str) -> Path:
    return index_dir / EXTRACTED_DIR_NAME / f"{sha256}.txt"


def write_extracted_text(index_dir: Path, sha256: str, text: str) -> str:
    dest = extracted_text_path(index_dir, sha256)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    # path relative to .kb/_index/
    return f"{EXTRACTED_DIR_NAME}/{sha256}.txt"


def load_relocation_proposals(index_dir: Path) -> list[dict[str, Any]]:
    path = index_dir / RELOCATION_FILENAME
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("proposals", []))


def save_relocation_proposals(index_dir: Path, proposals: list[dict[str, Any]]) -> Path:
    index_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "proposals": proposals,
    }
    out = index_dir / RELOCATION_FILENAME
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def load_taxonomy(taxonomy_path: Path) -> dict[str, Any]:
    with taxonomy_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def slugify_filename(name: str) -> str:
    stem = Path(name).stem
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem).strip("-").lower()
    return cleaned or "document"
