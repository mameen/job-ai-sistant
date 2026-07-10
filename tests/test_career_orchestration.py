from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.career.orchestration import (  # noqa: E402
    CAREER_ASSIGNEES,
    DIGEST_ASSIGNEES,
    career_board_rows,
    digest_board_rows,
)


class CareerOrchestrationTests(unittest.TestCase):
    def test_board_partition_filters(self) -> None:
        rows = [
            {"id": "1", "title": "Research: aisearch", "assignee": "ai_news_researcher", "status": "done"},
            {"id": "2", "title": "Career: discover EM roles", "assignee": "zazu_researcher", "status": "open"},
            {"id": "3", "title": "Librarian: merge & classify", "assignee": "ai_news_librarian", "status": "open"},
            {"id": "4", "title": "Random task", "assignee": "other", "status": "open"},
        ]
        career = career_board_rows(rows)
        digest = digest_board_rows(rows)
        self.assertEqual(len(career), 1)
        self.assertEqual(career[0]["id"], "2")
        self.assertEqual(len(digest), 2)
        digest_ids = {r["id"] for r in digest}
        self.assertEqual(digest_ids, {"1", "3"})
        self.assertFalse(CAREER_ASSIGNEES & DIGEST_ASSIGNEES)


if __name__ == "__main__":
    unittest.main()
