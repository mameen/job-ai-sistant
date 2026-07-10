from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .catalog import (
    CatalogDocument,
    load_catalog,
    load_relocation_proposals,
    load_taxonomy,
    save_catalog,
    save_relocation_proposals,
    write_extracted_text,
)
from .classify import classify_document, detect_layer
from .extract import detect_mime, extract_text
from .paths import (
    INDEX_DIR_NAME,
    SKIP_DIR_NAMES,
    is_scannable_file,
    rel_under_kb,
    repo_kb_paths,
)


@dataclass
class ScanResult:
    scanned: int
    added: int
    updated: int
    unchanged: int
    removed: int
    proposals: int
    catalog_path: Path
    relocation_path: Path


def scan_kb(
    repo: Path,
    *,
    scan_id: str | None = None,
    force_extract: bool = False,
    deep_extract: bool = False,
) -> ScanResult:
    kb_root, index_dir, _inbox, _index_db, taxonomy_path = repo_kb_paths(repo)
    if not kb_root.is_dir():
        raise FileNotFoundError(f"Career KB missing: {kb_root}")

    taxonomy = load_taxonomy(taxonomy_path)
    catalog = load_catalog(index_dir)
    documents: dict[str, Any] = dict(catalog.get("documents") or {})
    seen: set[str] = set()

    added = updated = unchanged = 0

    for path in sorted(_iter_kb_files(kb_root)):
        rel = rel_under_kb(kb_root, path)
        seen.add(rel)
        sha = _sha256(path)
        mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(microsecond=0)
        mtime_s = mtime.isoformat().replace("+00:00", "Z")

        prior = documents.get(rel)
        content_changed = not prior or prior.get("sha256") != sha

        text = ""
        extract_status = "skipped"
        extract_notes = ""
        extract_backend = "none"
        extracted_rel: str | None = prior.get("extracted_text_path") if prior else None

        if content_changed or force_extract or not extracted_rel:
            if deep_extract:
                from .rich_extract import extract_text_deep

                text, extract_status, extract_notes, extract_backend = extract_text_deep(path)
            else:
                text, extract_status, extract_notes = extract_text(path)
                extract_backend = "basic" if text.strip() else "none"
            if text.strip():
                extracted_rel = write_extracted_text(index_dir, sha, text)
            elif extract_status in {"unsupported", "error"}:
                extracted_rel = None

        sample = text if text.strip() else path.name
        classification = classify_document(
            kb_root=kb_root,
            rel_path=rel,
            filename=path.name,
            text_sample=sample,
            taxonomy=taxonomy,
        )

        record = CatalogDocument(
            sha256=sha,
            size_bytes=path.stat().st_size,
            mtime=mtime_s,
            mime=detect_mime(path),
            extension=path.suffix.lower(),
            layer=detect_layer(rel),
            category_id=classification.category_id,
            category_confidence=classification.confidence,
            placement_ok=classification.placement_ok,
            suggested_path=classification.suggested_path,
            extracted_text_path=extracted_rel,
            extract_status=extract_status,
            extract_notes=extract_notes,
            extract_backend=extract_backend,
        )
        new_dict = record.to_dict()

        if not prior:
            added += 1
        elif prior != new_dict:
            updated += 1
        else:
            unchanged += 1

        documents[rel] = new_dict

    removed = 0
    for rel in list(documents.keys()):
        if rel not in seen:
            del documents[rel]
            removed += 1

    catalog["documents"] = documents
    catalog_path = save_catalog(index_dir, catalog, scan_id=scan_id)

    proposals = _build_relocation_proposals(documents)
    existing = load_relocation_proposals(index_dir)
    merged = _merge_proposals(existing, proposals)
    relocation_path = save_relocation_proposals(index_dir, merged)

    return ScanResult(
        scanned=len(seen),
        added=added,
        updated=updated,
        unchanged=unchanged,
        removed=removed,
        proposals=len([p for p in merged if p.get("status") == "pending"]),
        catalog_path=catalog_path,
        relocation_path=relocation_path,
    )


def _iter_kb_files(kb_root: Path):
    for path in kb_root.rglob("*"):
        rel_parts = path.relative_to(kb_root).parts
        if rel_parts and rel_parts[0] == INDEX_DIR_NAME:
            continue
        if any(part in SKIP_DIR_NAMES for part in rel_parts):
            continue
        if path.is_dir():
            continue
        if is_scannable_file(path):
            yield path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_relocation_proposals(documents: dict[str, Any]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for rel, doc in sorted(documents.items()):
        if doc.get("placement_ok"):
            continue
        suggested = doc.get("suggested_path")
        if not suggested or suggested == rel:
            continue
        proposals.append(
            {
                "source_path": rel,
                "suggested_path": suggested,
                "category_id": doc.get("category_id"),
                "confidence": doc.get("category_confidence"),
                "reason": f"classified as {doc.get('category_id')}",
                "status": "pending",
            }
        )
    return proposals


def _merge_proposals(
    existing: list[dict[str, Any]],
    fresh: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_source = {p["source_path"]: p for p in existing if p.get("status") != "pending"}
    for proposal in fresh:
        src = proposal["source_path"]
        prior = by_source.get(src)
        if prior and prior.get("status") in {"approved", "rejected"}:
            continue
        by_source[src] = proposal
    return sorted(by_source.values(), key=lambda p: p.get("source_path", ""))
