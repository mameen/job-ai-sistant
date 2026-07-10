from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.kb.application_registry import upsert_application  # noqa: E402
from lib.kb.learning_registry import (  # noqa: E402
    list_learning_events,
    normalize_topic,
    record_learning_event,
    set_application_topics,
    topic_response_rates,
)


class LearningRegistryTests(unittest.TestCase):
    def test_normalize_topic(self) -> None:
        self.assertEqual(normalize_topic("MCP Platform"), "mcp_platform")

    def test_topics_and_learning_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "applications.db"
            rec = upsert_application(
                db,
                company="Acme",
                job_title="EM",
                job_id="na",
                status="applied",
            )
            tags = set_application_topics(db, rec.opportunity_id, ["MCP", "remote"], source="user")
            self.assertEqual(tags, ["mcp", "remote"])

            event = record_learning_event(
                db,
                source_type="user_rejection",
                source_ref=rec.opportunity_id,
                target="status:rejected",
                action="auto_applied",
                explanation="No response after 30 days.",
            )
            self.assertTrue(event.event_id.startswith("le:"))

            events = list_learning_events(db, limit=5)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].explanation, "No response after 30 days.")

    def test_topic_response_rates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "applications.db"
            rec1 = upsert_application(db, company="A", job_title="EM", status="applied")
            rec2 = upsert_application(db, company="B", job_title="EM", status="interviewing")
            set_application_topics(db, rec1.opportunity_id, ["mcp"])
            set_application_topics(db, rec2.opportunity_id, ["mcp"])

            stats = {s.topic: s for s in topic_response_rates(db)}
            self.assertIn("mcp", stats)
            self.assertEqual(stats["mcp"].total, 2)


if __name__ == "__main__":
    unittest.main()
