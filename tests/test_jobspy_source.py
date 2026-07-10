from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.career.jobspy_source import (  # noqa: E402
    build_jobspy_envelope,
    format_jobspy_prompt_block,
    make_opportunity_id,
    normalize_jobspy_row,
    parse_site_list,
    write_jobspy_artifact,
)


class JobSpySourceTests(unittest.TestCase):
    def test_make_opportunity_id_is_stable(self) -> None:
        url = "https://www.linkedin.com/jobs/view/12345"
        self.assertEqual(make_opportunity_id(url), make_opportunity_id(url))
        self.assertTrue(make_opportunity_id(url).startswith("opp:"))

    def test_normalize_jobspy_row_maps_opportunity_v1(self) -> None:
        row = {
            "id": "ln-99",
            "site": "linkedin",
            "job_url": "https://www.linkedin.com/jobs/view/12345",
            "job_url_direct": "https://jobs.lever.co/acme/abc",
            "title": "Software Engineering Manager, AI/ML",
            "company": "Acme Corp",
            "location": "Seattle, WA",
            "date_posted": "2026-07-08",
            "job_type": ["fulltime"],
            "description": "Lead AI platform teams.",
            "is_remote": False,
            "job_level": "mid-senior level",
        }
        opp = normalize_jobspy_row(row, fetched_at="2026-07-09T08:00:00Z")
        assert opp is not None
        self.assertEqual(opp["schema"], "opportunity_artifact/v1")
        self.assertEqual(opp["source_kind"], "aggregator")
        self.assertEqual(opp["apply_url"], "https://jobs.lever.co/acme/abc")
        self.assertEqual(opp["canonical_url"], "https://jobs.lever.co/acme/abc")
        self.assertEqual(opp["aggregator"]["platform"], "linkedin")
        self.assertIn("date_posted=2026-07-08", opp["researcher_notes"])

    def test_normalize_skips_incomplete_rows(self) -> None:
        self.assertIsNone(normalize_jobspy_row({"title": "Only title"}))

    def test_parse_site_list_defaults_and_validates(self) -> None:
        self.assertEqual(parse_site_list(""), ["linkedin", "indeed", "google"])
        self.assertEqual(parse_site_list("linkedin"), ["linkedin"])
        with self.assertRaises(ValueError):
            parse_site_list("linkedin,unknown_board")

    def test_prompt_block_lists_seed_hits(self) -> None:
        envelope = build_jobspy_envelope(
            query="SEM AI",
            sites=["linkedin"],
            location="United States",
            posted_within_days=10,
            opportunities=[
                normalize_jobspy_row(
                    {
                        "site": "linkedin",
                        "job_url": "https://www.linkedin.com/jobs/view/1",
                        "title": "Engineering Manager",
                        "company": "Beta",
                        "location": "Remote",
                        "date_posted": "2026-07-08",
                    },
                    fetched_at="2026-07-09T08:00:00Z",
                )
            ],
            errors=[],
        )
        block = format_jobspy_prompt_block(envelope)
        self.assertIn("JobSpy aggregator", block)
        self.assertIn("Beta", block)
        self.assertIn("linkedin.com/jobs/view/1", block)

    def test_write_jobspy_artifact_roundtrip(self) -> None:
        path = REPO / "agentic" / "hermes" / ".runtime" / "test_search_jobspy.json"
        envelope = build_jobspy_envelope(
            query="test",
            sites=["indeed"],
            location=None,
            posted_within_days=7,
            opportunities=[],
            errors=["demo warning"],
        )
        write_jobspy_artifact(path, envelope)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["schema"], "search_jobspy/v1")
        self.assertEqual(loaded["errors"], ["demo warning"])
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
