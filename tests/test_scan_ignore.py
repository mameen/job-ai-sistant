#!/usr/bin/env python3
"""Tests for .piiignore / .ignorepii path matching."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_spec = importlib.util.spec_from_file_location("scan_ignore", _SCRIPTS / "scan_ignore.py")
assert _spec and _spec.loader
scan_ignore = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_ignore)


class ScanIgnoreTest(unittest.TestCase):
    def test_kb_exempt(self) -> None:
        patterns = scan_ignore.load_patterns(ROOT)
        self.assertTrue(scan_ignore.is_ignored("agentic/hermes/.kb/private/goals.md", patterns))
        self.assertTrue(scan_ignore.is_ignored(".kb/public/resume.md", patterns))

    def test_source_not_exempt(self) -> None:
        patterns = scan_ignore.load_patterns(ROOT)
        self.assertFalse(scan_ignore.is_ignored("agentic/hermes/admin/manage.py", patterns))

    def test_fixture_exempt(self) -> None:
        patterns = scan_ignore.load_patterns(ROOT)
        self.assertTrue(scan_ignore.is_ignored("tests/fixtures/recruiter_sample.eml", patterns))

    def test_forbidden_commit_paths(self) -> None:
        self.assertIsNotNone(
            scan_ignore.forbidden_commit_reason("agentic/hermes/.kb/private/resume.docx")
        )
        self.assertIsNotNone(
            scan_ignore.forbidden_commit_reason(".venv/lib/python3.11/site-packages/foo.py")
        )
        self.assertIsNone(scan_ignore.forbidden_commit_reason("agentic/hermes/admin/manage.py"))

    def test_forbidden_venv_prefix_not_confused_with_venv(self) -> None:
        reason = scan_ignore.forbidden_commit_reason(".venv/lib/foo.py")
        self.assertIsNotNone(reason)
        self.assertIn(".venv/", reason)

    def test_piiignore_off_by_default(self) -> None:
        patterns = scan_ignore.load_patterns(ROOT)
        self.assertFalse(
            scan_ignore.should_skip_audit_path(
                "tests/fixtures/recruiter_sample.eml",
                patterns,
                observe_piiignore=False,
            )
        )
        self.assertTrue(
            scan_ignore.should_skip_audit_path(
                "tests/fixtures/recruiter_sample.eml",
                patterns,
                observe_piiignore=True,
            )
        )

    def test_forbidden_env_file(self) -> None:
        self.assertIsNotNone(scan_ignore.forbidden_commit_reason(".env"))

    def test_forbidden_observe_piiignore_still_scans(self) -> None:
        patterns = scan_ignore.load_patterns(ROOT)
        rel = "agentic/hermes/.kb/private/x.md"
        self.assertFalse(
            scan_ignore.should_skip_audit_path(rel, patterns, observe_piiignore=True)
        )
        patterns = scan_ignore.load_patterns(ROOT)
        warnings = scan_ignore.local_sensitive_warnings(
            ROOT, patterns, observe_piiignore=False
        )
        kb = [w for w in warnings if "agentic/hermes/.kb" in w or ".kb/" in w]
        self.assertTrue(kb, "expected warning when .kb exists locally")


if __name__ == "__main__":
    unittest.main()
