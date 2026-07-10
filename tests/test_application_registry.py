from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.kb.application_registry import (  # noqa: E402
    applications_db_path,
    find_by_company,
    find_company_overlap,
    find_exact,
    import_vault_folders,
    make_dedupe_key,
    upsert_application,
)
from lib.kb.classify import classify_document  # noqa: E402
from lib.kb.catalog import load_taxonomy  # noqa: E402


class ApplicationRegistryTests(unittest.TestCase):
    def test_upsert_and_company_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "applications.db"
            rec = upsert_application(
                db,
                company="AcmeCorp",
                job_title="Senior Manager, Engineering - AI & Automation",
                job_id="na",
                status="applied",
                job_date="20260101",
                vault_path="private/application_history/applications/20260101/AcmeCorp",
            )
            self.assertTrue(rec.opportunity_id.startswith("opp:"))
            hits = find_by_company(db, "AcmeCorp")
            self.assertEqual(len(hits), 1)
            overlap = find_company_overlap(db, "AcmeCorp (Bloomberg: ACME)")
            self.assertEqual(len(overlap), 1)

    def test_dedupe_exact_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "applications.db"
            upsert_application(db, company="Acme", job_title="EM", job_id="123", status="applied")
            exact = find_exact(db, company="Acme", job_title="EM", job_id="123")
            self.assertIsNotNone(exact)
            key = make_dedupe_key(company="Acme", job_title="EM", job_id="123")
            self.assertEqual(exact.dedupe_key, key)

    def test_register_external_ats_dedupe(self) -> None:
        """External ATS rows use synthetic fixtures only — never real posting URLs."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "applications.db"
            rec = upsert_application(
                db,
                company="Example Corp",
                job_title="Senior Product Manager, Platform",
                job_id="REQ-00042",
                apply_url="https://careers.example.com/jobs/REQ-00042",
                status="rejected",
                job_date="20260113",
                notes="ATS example_portal | external registration",
            )
            self.assertTrue(rec.opportunity_id.startswith("opp:"))
            exact = find_exact(
                db,
                company="Example Corp",
                job_title="Senior Product Manager, Platform",
                job_id="REQ-00042",
            )
            self.assertIsNotNone(exact)
            self.assertEqual(exact.status, "rejected")

    def test_import_vault_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp) / ".kb"
            vault = (
                kb
                / "private/application_history/applications/20260101/AcmeCorp"
            )
            vault.mkdir(parents=True)
            (vault / "pm-resume.docx").write_bytes(b"fake")
            (vault / "cover.docx").write_bytes(b"fake")
            index = kb / "_index"
            index.mkdir(parents=True)
            extracted = index / "extracted"
            extracted.mkdir()
            cover_hash = "abc"
            (extracted / f"{cover_hash}.txt").write_text(
                "apply for the Senior Manager, Engineering - AI & Automation role at AcmeCorp\n",
                encoding="utf-8",
            )
            catalog = {
                "documents": {
                    "private/application_history/applications/20260101/AcmeCorp/cover.docx": {
                        "extracted_text_path": f"extracted/{cover_hash}.txt",
                    }
                }
            }
            import json

            (index / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
            db = applications_db_path(index)
            imported = import_vault_folders(kb, db)
            self.assertEqual(len(imported), 1)
            self.assertEqual(imported[0].company, "AcmeCorp")
            self.assertIn("Senior Manager", imported[0].job_title)


class ClassifyLongestPrefixTests(unittest.TestCase):
    def test_application_history_not_career_goals(self) -> None:
        taxonomy = load_taxonomy(HERMES_PKG / "kb" / "taxonomy.yaml")
        rel = "private/application_history/applications/20260101/AcmeCorp/cover.docx"
        result = classify_document(
            kb_root=Path("/tmp/kb"),
            rel_path=rel,
            filename="cover.docx",
            text_sample="I applied for the role at AcmeCorp",
            taxonomy=taxonomy,
        )
        self.assertEqual(result.category_id, "application_history")


if __name__ == "__main__":
    unittest.main()
