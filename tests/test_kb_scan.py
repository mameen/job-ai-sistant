from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
FIXTURES = Path(__file__).resolve().parent / "data" / "kb_scan"


def _import_scan_kb():
    import sys

    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))
    from lib.kb import scan_kb

    return scan_kb


class KbScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        shutil.copytree(HERMES_PKG / "kb", self.repo / "agentic" / "hermes" / "kb")
        shutil.copytree(FIXTURES, self.repo / "agentic" / "hermes" / ".kb")
        (self.repo / "agentic" / "hermes" / ".kb" / "_index").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_scan_indexes_inbox_resume(self) -> None:
        scan_kb = _import_scan_kb()
        result = scan_kb(self.repo, scan_id="test001")
        self.assertEqual(result.scanned, 3)
        catalog = json.loads(
            (self.repo / "agentic" / "hermes" / ".kb" / "_index" / "catalog.json").read_text(encoding="utf-8")
        )
        docs = catalog["documents"]
        self.assertIn("inbox/jane-doe-resume.txt", docs)
        inbox_doc = docs["inbox/jane-doe-resume.txt"]
        self.assertEqual(inbox_doc["category_id"], "master_resume")
        self.assertFalse(inbox_doc["placement_ok"])
        self.assertTrue(inbox_doc["suggested_path"])
        self.assertEqual(inbox_doc["extract_status"], "ok")

    def test_scan_leaves_canonical_markdown_placed(self) -> None:
        scan_kb = _import_scan_kb()
        scan_kb(self.repo, scan_id="test002")
        catalog = json.loads(
            (self.repo / "agentic" / "hermes" / ".kb" / "_index" / "catalog.json").read_text(encoding="utf-8")
        )
        skills = catalog["documents"]["public/skills.md"]
        self.assertEqual(skills["category_id"], "skills")
        self.assertTrue(skills["placement_ok"])

    def test_relocation_proposals_for_inbox(self) -> None:
        scan_kb = _import_scan_kb()
        scan_kb(self.repo, scan_id="test003")
        proposals = json.loads(
            (self.repo / "agentic" / "hermes" / ".kb" / "_index" / "relocation_proposals.json").read_text(
                encoding="utf-8"
            )
        )
        pending = [p for p in proposals["proposals"] if p["status"] == "pending"]
        sources = {p["source_path"] for p in pending}
        self.assertIn("inbox/jane-doe-resume.txt", sources)


if __name__ == "__main__":
    unittest.main()
