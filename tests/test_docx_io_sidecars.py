from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.generated.docx_io import coach_sidecar_status, write_plain_docx  # noqa: E402


class CoachSidecarTests(unittest.TestCase):
    def test_coach_sidecar_status(self) -> None:
        try:
            from docx import Document  # noqa: F401
        except ImportError:
            self.skipTest("python-docx not installed")

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_plain_docx(run_dir / "acme_role_na_20260708_resume.docx", paragraphs=["r"])
            write_plain_docx(run_dir / "acme_role_na_20260708_cover.docx", paragraphs=["c"])
            write_plain_docx(run_dir / "acme_role_na_20260708_brief.docx", paragraphs=["b"])
            (run_dir / "acme_role_na_20260708_resume.md").write_text("resume md", encoding="utf-8")
            (run_dir / "acme_role_na_20260708_cover.md").write_text("cover md", encoding="utf-8")

            status = coach_sidecar_status(run_dir)
            self.assertTrue(status["resume"])
            self.assertTrue(status["cover"])
            self.assertFalse(status["brief"])


if __name__ == "__main__":
    unittest.main()
