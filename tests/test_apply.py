from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.generated.apply import (  # noqa: E402
    extract_job_id_from_url,
    parse_search_consider,
    parse_search_consider_all,
    write_proposal_triplet,
)
from lib.generated.docx_io import write_plain_docx  # noqa: E402


class ApplyTests(unittest.TestCase):
    def test_extract_job_id_greenhouse(self) -> None:
        url = "https://job-boards.greenhouse.io/smartsheet/jobs/7766865"
        self.assertEqual(extract_job_id_from_url(url), "7766865")

    def test_extract_job_id_builtin(self) -> None:
        url = "https://builtinseattle.com/jobs/senior-engineering-manager-kernel-and-virt-at-digitalocean-3497678"
        self.assertEqual(extract_job_id_from_url(url), "3497678")

    def test_parse_search_consider(self) -> None:
        fixture = REPO / "tests" / "data" / "search_latest_snippet.md"
        picked = parse_search_consider(fixture)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertIn("Smartsheet", picked["company"])
        self.assertEqual(picked["job_id"], "7766865")

    def test_parse_search_consider_letter_summary_table(self) -> None:
        fixture = REPO / "tests" / "data" / "search_summary_letter_rows.md"
        picked = parse_search_consider(fixture)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked["company"], "Deepgram")
        self.assertIn("Active Learning", picked["title"])

    def test_parse_search_consider_all(self) -> None:
        fixture = REPO / "tests" / "data" / "search_summary_letter_rows.md"
        rows = parse_search_consider_all(fixture)
        self.assertEqual(len(rows), 2)
        companies = {row["company"] for row in rows}
        self.assertEqual(companies, {"Deepgram", "Runpod"})

    def test_write_proposal_triplet_naming(self) -> None:
        try:
            from docx import Document  # noqa: F401
        except ImportError:
            self.skipTest("python-docx not installed")

        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp) / ".kb"
            tmpl = kb / "private" / "originals" / "resume-repo"
            tmpl.mkdir(parents=True)
            write_plain_docx(tmpl / "pm-resume.docx", paragraphs=["Resume template line."])
            write_plain_docx(tmpl / "cover.docx", paragraphs=["Cover template line."])
            (kb / "public").mkdir()
            (kb / "public" / "master_resume.md").write_text(
                "# Master resume\n\n## Content\n\nReal resume body from KB.\n",
                encoding="utf-8",
            )
            proposals = Path(tmp) / "proposals"
            run_dir, paths = write_proposal_triplet(
                kb_root=kb,
                repo=Path(tmp) / "repo",
                proposals_root=proposals,
                company="Smartsheet",
                job_title="Manager, Engineering",
                job_id="7766865",
                job_date="20260708",
                run_prefix="20260708120000",
            )
            self.assertEqual(run_dir.name, "20260708120000")
            self.assertEqual(len(paths), 3)
            names = {p.name for p in paths}
            self.assertIn("smartsheet_manager_engineering_7766865_20260708_resume.docx", names)
            self.assertIn("smartsheet_manager_engineering_7766865_20260708_cover.docx", names)
            self.assertIn("smartsheet_manager_engineering_7766865_20260708_brief.docx", names)


    def test_brief_substantial_from_kb(self) -> None:
        from lib.generated.apply import build_application_brief_md  # noqa: E402

        kb = REPO / "agentic" / "hermes" / ".kb"
        if not kb.is_dir():
            self.skipTest("local .kb not present")
        brief = build_application_brief_md(
            kb,
            REPO,
            company="Smartsheet",
            job_title="Manager, Engineering",
            job_id="7766865",
            url="https://example.com/job",
        )
        self.assertIn("OPPORTUNITY_INTELLIGENCE", brief)
        self.assertIn("STAR_STORIES", brief)
        self.assertIn("RECOMMENDATION", brief)
        self.assertGreater(len(brief), 1500)


if __name__ == "__main__":
    unittest.main()
