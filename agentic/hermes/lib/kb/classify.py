from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import slugify_filename
from .paths import INBOX_DIR_NAME


@dataclass
class Classification:
    category_id: str
    confidence: float
    placement_ok: bool
    suggested_path: str | None
    reason: str


def detect_layer(rel_path: str) -> str:
    if rel_path.startswith("public/"):
        return "public"
    if rel_path.startswith("private/"):
        return "private"
    if rel_path.startswith(f"{INBOX_DIR_NAME}/") or rel_path == INBOX_DIR_NAME:
        return "inbox"
    return "unknown"


def classify_document(
    *,
    kb_root: Path,
    rel_path: str,
    filename: str,
    text_sample: str,
    taxonomy: dict[str, Any],
) -> Classification:
    categories: list[dict[str, Any]] = list(taxonomy.get("categories") or [])
    layer = detect_layer(rel_path)
    name_lower = filename.lower()
    text_lower = text_sample.lower()[:8000]

    # Exact canonical file match
    for cat in categories:
        for canonical in cat.get("canonical_files") or []:
            if rel_path == canonical:
                return Classification(
                    category_id=cat["id"],
                    confidence=1.0,
                    placement_ok=True,
                    suggested_path=None,
                    reason="canonical file path",
                )

    # Directory placement match — longest target_dir prefix wins (private/ vs private/application_history/)
    best_cat: dict[str, Any] | None = None
    best_prefix_len = -1
    for cat in categories:
        if cat.get("fallback"):
            continue
        target_dir = str(cat.get("target_dir") or "").strip("/")
        if not target_dir:
            continue
        prefix = f"{target_dir}/"
        if rel_path.startswith(prefix) and rel_path != prefix.rstrip("/"):
            if len(target_dir) > best_prefix_len:
                best_prefix_len = len(target_dir)
                best_cat = cat
    if best_cat is not None:
        return Classification(
            category_id=best_cat["id"],
            confidence=0.95,
            placement_ok=True,
            suggested_path=None,
            reason=f"under {best_cat.get('target_dir')}/",
        )

    # Score by filename hints + keywords
    best_id = "original_public"
    best_score = 0.0
    best_cat: dict[str, Any] | None = None
    for cat in categories:
        if cat.get("fallback"):
            continue
        score = _score_category(cat, name_lower, text_lower)
        if score > best_score:
            best_score = score
            best_id = cat["id"]
            best_cat = cat

    if best_cat is None or best_score < 0.15:
        best_cat = _fallback_category(categories, layer)
        best_id = best_cat["id"]
        best_score = 0.2
        reason = "low keyword match — fallback category"
    else:
        reason = f"keyword/filename score {best_score:.2f}"

    placement_ok, suggested = _placement_for(
        rel_path=rel_path,
        layer=layer,
        category=best_cat,
        filename=filename,
        inbox_dir=str(taxonomy.get("inbox_dir") or INBOX_DIR_NAME),
    )
    confidence = min(0.99, 0.35 + best_score)

    return Classification(
        category_id=best_id,
        confidence=confidence,
        placement_ok=placement_ok,
        suggested_path=suggested,
        reason=reason,
    )


def _score_category(cat: dict[str, Any], name_lower: str, text_lower: str) -> float:
    score = 0.0
    for hint in cat.get("file_hints") or []:
        hint_l = str(hint).lower()
        if hint_l and hint_l in name_lower:
            score += 0.45
    for kw in cat.get("keywords") or []:
        kw_l = str(kw).lower()
        if not kw_l:
            continue
        if kw_l in name_lower:
            score += 0.35
        if kw_l in text_lower:
            score += 0.25
        # multi-word keywords
        if " " in kw_l and kw_l in text_lower:
            score += 0.15
    return score


def _fallback_category(categories: list[dict[str, Any]], layer: str) -> dict[str, Any]:
    want = "original_private" if layer == "private" else "original_public"
    for cat in categories:
        if cat.get("id") == want:
            return cat
    for cat in categories:
        if cat.get("fallback") and cat.get("layer") == layer:
            return cat
    return categories[-1]


def _placement_for(
    *,
    rel_path: str,
    layer: str,
    category: dict[str, Any],
    filename: str,
    inbox_dir: str,
) -> tuple[bool, str | None]:
    target_dir = str(category.get("target_dir") or "").strip("/")
    cat_layer = category.get("layer")
    slug = slugify_filename(filename)
    ext = Path(filename).suffix.lower()

    if layer == "inbox" or layer == "unknown":
        suggested = f"{target_dir}/{slug}{ext}" if target_dir else f"{inbox_dir}/{filename}"
        return False, suggested

    if cat_layer and layer != cat_layer:
        suggested = f"{target_dir}/{slug}{ext}"
        return False, suggested

    canonical_files = [str(p) for p in (category.get("canonical_files") or [])]
    if canonical_files and rel_path not in canonical_files:
        # Same layer but wrong folder — e.g. resume PDF in public/ root
        if not rel_path.startswith(f"{target_dir}/"):
            if any(rel_path.endswith(Path(c).name) for c in canonical_files):
                return False, canonical_files[0]
            suggested = f"{target_dir}/{slug}{ext}"
            return False, suggested

    if target_dir and not rel_path.startswith(f"{target_dir}/"):
        if rel_path in canonical_files:
            return True, None
        suggested = f"{target_dir}/{slug}{ext}"
        return False, suggested

    return True, None
