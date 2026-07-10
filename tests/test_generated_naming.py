from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.generated.naming import artifact_filename  # noqa: E402


class GeneratedNamingTests(unittest.TestCase):
    def test_artifact_filename_resume(self) -> None:
        name = artifact_filename(
            company="Tailscale Inc",
            job_title="Engineering Manager, Strategic Projects",
            job_id="4700031005",
            job_date="20260707",
            kind="resume",
        )
        self.assertTrue(name.endswith("_resume.docx"))
        self.assertIn("tailscale", name)
        self.assertIn("4700031005", name)


if __name__ == "__main__":
    unittest.main()
