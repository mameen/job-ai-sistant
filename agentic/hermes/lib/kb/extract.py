from __future__ import annotations

import mimetypes
from pathlib import Path

from .paths import DOCX_EXTENSIONS, IMAGE_EXTENSIONS, PDF_EXTENSIONS, TEXT_EXTENSIONS


def detect_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def extract_text(path: Path) -> tuple[str, str, str]:
    """Return (text, status, notes). status: ok | partial | unsupported | error."""
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return _read_text(path)
    if ext in PDF_EXTENSIONS:
        return _extract_pdf(path)
    if ext in DOCX_EXTENSIONS:
        return _extract_docx(path)
    if ext in IMAGE_EXTENSIONS:
        return "", "unsupported", "image — classify from filename; OCR/vision via zazu_knowledge_manager"
    return "", "unsupported", f"no extractor for {ext or 'unknown extension'}"


def _read_text(path: Path) -> tuple[str, str, str]:
    try:
        text = path.read_text(encoding="utf-8")
        return text, "ok", ""
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="latin-1")
            return text, "partial", "decoded as latin-1"
        except OSError as exc:
            return "", "error", str(exc)
    except OSError as exc:
        return "", "error", str(exc)


def _extract_pdf(path: Path) -> tuple[str, str, str]:
    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]
    except ImportError:
        return "", "unsupported", "install pypdf for PDF text extraction (pip install pypdf)"

    try:
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                chunks.append(page_text)
        text = "\n\n".join(chunks).strip()
        if not text:
            return "", "partial", "pdf parsed but no extractable text (scanned PDF?)"
        return text, "ok", f"{len(reader.pages)} page(s)"
    except Exception as exc:  # noqa: BLE001 — surface parse failures in catalog
        return "", "error", str(exc)


def _extract_docx(path: Path) -> tuple[str, str, str]:
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError:
        return (
            "",
            "unsupported",
            "install python-docx for Word extraction (pip install python-docx)",
        )

    try:
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs).strip()
        if not text:
            return "", "partial", "docx parsed but no paragraph text"
        return text, "ok", f"{len(paragraphs)} paragraph(s)"
    except Exception as exc:  # noqa: BLE001
        return "", "error", str(exc)
