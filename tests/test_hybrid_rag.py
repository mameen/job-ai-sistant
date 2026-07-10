from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.kb.bm25 import bm25_search  # noqa: E402
from lib.kb.search_preflight import company_path_hits, path_hits_from_catalog  # noqa: E402


class Bm25Tests(unittest.TestCase):
    def test_bm25_ranks_exact_company_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chunks = Path(tmp) / "chunks.jsonl"
            records = [
                {"id": 1, "source_path": "a.md", "text": "generic engineering manager resume"},
                {
                    "id": 2,
                    "source_path": "private/application_history/20260101/AcmeCorp/cover.docx",
                    "text": "excited to apply for the Senior Manager role at AcmeCorp",
                },
            ]
            chunks.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
            hits = bm25_search(chunks, "AcmeCorp application", top_k=2)
            self.assertGreaterEqual(len(hits), 1)
            self.assertIn("AcmeCorp", hits[0].source_path)


class SearchPreflightTests(unittest.TestCase):
    def test_path_hits_find_company_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "documents": {
                            "private/application_history/applications/20260101/AcmeCorp/cover.docx": {},
                            "public/master_resume.md": {},
                        }
                    }
                ),
                encoding="utf-8",
            )
            hits = path_hits_from_catalog(catalog_path, "AcmeCorp manager", limit=5)
            self.assertTrue(any("AcmeCorp" in h for h in hits))
            folders = company_path_hits("AcmeCorp", catalog_path)
            self.assertTrue(any("AcmeCorp" in f for f in folders))


if __name__ == "__main__":
    unittest.main()
