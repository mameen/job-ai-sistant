from __future__ import annotations

from pathlib import Path

from .paths import IMAGE_EXTENSIONS, PDF_EXTENSIONS


def extract_text_deep(path: Path) -> tuple[str, str, str, str]:
    """Deep extraction: basic → unstructured → OCR.

    Returns (text, status, notes, backend) where backend is
    basic | unstructured | tesseract | none.
    """
    from .extract import extract_text

    text, status, notes = extract_text(path)
    if status == "ok" and len(text.strip()) >= 80:
        return text, status, notes, "basic"

    ext = path.suffix.lower()
    needs_rich = ext in PDF_EXTENSIONS | IMAGE_EXTENSIONS or status in {
        "partial",
        "unsupported",
        "error",
    }
    if needs_rich:
        rich_text, rich_status, rich_notes, backend = _extract_unstructured(path)
        if rich_text.strip() and len(rich_text.strip()) >= len(text.strip()):
            return rich_text, rich_status, rich_notes, backend

    if ext in IMAGE_EXTENSIONS:
        ocr_text, ocr_status, ocr_notes = _extract_tesseract(path)
        if ocr_text.strip() and len(ocr_text.strip()) >= len(text.strip()):
            return ocr_text, ocr_status, ocr_notes, "tesseract"

    if text.strip():
        return text, status, notes, "basic"
    return text, status or "unsupported", notes, "none"


def _extract_unstructured(path: Path) -> tuple[str, str, str, str]:
    try:
        from unstructured.partition.auto import partition  # type: ignore[import-untyped]
    except ImportError:
        return (
            "",
            "unsupported",
            "install unstructured for rich PDF/image parsing: pip install -r requirements-kb-extract.txt",
            "none",
        )

    try:
        elements = partition(filename=str(path))
        chunks = [str(el).strip() for el in elements if str(el).strip()]
        text = "\n\n".join(chunks).strip()
        if not text:
            return "", "partial", "unstructured returned no text elements", "unstructured"
        return text, "ok", f"unstructured ({len(chunks)} element(s))", "unstructured"
    except Exception as exc:  # noqa: BLE001
        return "", "error", f"unstructured: {exc}", "unstructured"


def _extract_tesseract(path: Path) -> tuple[str, str, str]:
    try:
        import pytesseract  # type: ignore[import-untyped]
        from PIL import Image  # type: ignore[import-untyped]
    except ImportError:
        return (
            "",
            "unsupported",
            "install pytesseract+Pillow; system tesseract binary required",
        )

    try:
        text = pytesseract.image_to_string(Image.open(path)).strip()
        if not text:
            return "", "partial", "tesseract OCR returned empty text"
        return text, "ok", "tesseract OCR"
    except Exception as exc:  # noqa: BLE001
        return "", "error", f"tesseract: {exc}"
