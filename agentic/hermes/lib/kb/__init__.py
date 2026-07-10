"""Career KB ingestion — scan, extract, classify, index, RAG."""

from .extract_kb import extract_kb
from .application_registry import (
    applications_db_path,
    find_company_overlap,
    format_registry_summary,
    import_vault_folders,
    list_applications,
    record_outcome,
    upsert_application,
)
from .rag_index import query_rag, query_rag_hybrid
from .scan import scan_kb
from .search_preflight import build_search_preflight

__all__ = [
    "applications_db_path",
    "build_search_preflight",
    "extract_kb",
    "find_company_overlap",
    "format_registry_summary",
    "import_vault_folders",
    "list_applications",
    "query_rag",
    "query_rag_hybrid",
    "record_outcome",
    "scan_kb",
    "upsert_application",
]
