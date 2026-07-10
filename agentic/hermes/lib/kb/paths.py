from __future__ import annotations

from pathlib import Path

KB_MARKER = ".kb_initialized"
INDEX_DIR_NAME = "_index"
INDEX_DB_DIR_NAME = "index_db"
INBOX_DIR_NAME = "inbox"
SECRETS_DIR_NAME = "secrets"
APPLICATIONS_DB_FILENAME = "applications.db"
CATALOG_FILENAME = "catalog.json"
RELOCATION_FILENAME = "relocation_proposals.json"
EXTRACTED_DIR_NAME = "extracted"

SKIP_DIR_NAMES = {INDEX_DIR_NAME, INDEX_DB_DIR_NAME, "__pycache__", ".git", "secrets"}
SKIP_FILE_NAMES = {KB_MARKER, CATALOG_FILENAME, RELOCATION_FILENAME}

TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml"}
PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".bmp", ".heic"}


def repo_kb_paths(repo: Path) -> tuple[Path, Path, Path, Path, Path]:
    """Return (kb_root, kb_index, kb_inbox, index_db, taxonomy_path)."""
    hermes_pkg = repo / "agentic" / "hermes"
    kb_root = hermes_pkg / ".kb"
    return (
        kb_root,
        kb_root / INDEX_DIR_NAME,
        kb_root / INBOX_DIR_NAME,
        kb_root / INDEX_DB_DIR_NAME,
        hermes_pkg / "kb" / "taxonomy.yaml",
    )


def rel_under_kb(kb_root: Path, path: Path) -> str:
    return path.relative_to(kb_root).as_posix()


def is_scannable_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name in SKIP_FILE_NAMES:
        return False
    if path.name.startswith("."):
        return False
    return True
