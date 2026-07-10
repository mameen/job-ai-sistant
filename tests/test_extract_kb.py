from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
FIXTURES = Path(__file__).resolve().parent / "data" / "kb_scan"


def _import_extract_kb():
    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))
    from lib.kb.extract_kb import extract_kb

    return extract_kb


class ExtractKbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        shutil = __import__("shutil")
        shutil.copytree(HERMES_PKG / "kb", self.repo / "agentic" / "hermes" / "kb")
        shutil.copytree(FIXTURES, self.repo / "agentic" / "hermes" / ".kb")
        kb = self.repo / "agentic" / "hermes" / ".kb"
        (kb / "_index").mkdir(parents=True, exist_ok=True)
        (kb / "index_db").mkdir(parents=True, exist_ok=True)
        (kb / "private" / "prompts").mkdir(parents=True, exist_ok=True)
        (kb / "private" / "prompts" / "job_fitness.md").write_text(
            "### Guardrails:\n* **RED FLAGS (Hard No):**\n    * No banks.\n"
            "* **YELLOW FLAGS (Dispreferred):**\n    * No startups.\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_extract_kb_skip_rag_organizes(self) -> None:
        extract_kb = _import_extract_kb()
        result = extract_kb(self.repo, scan_id="extract_test", skip_rag=True)
        self.assertGreater(result.scanned, 0)
        self.assertTrue(result.chunks_path.is_file())
        master = self.repo / "agentic" / "hermes" / ".kb" / "public" / "master_resume.md"
        self.assertTrue(master.is_file())
        self.assertIn("jane", master.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
