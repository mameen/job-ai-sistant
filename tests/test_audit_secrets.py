#!/usr/bin/env python3
"""Tests for scripts/audit_secrets.py policy (forbidden paths, tracked-only scope)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_spec = importlib.util.spec_from_file_location("audit_secrets", _SCRIPTS / "audit_secrets.py")
assert _spec and _spec.loader
audit_secrets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit_secrets)


class AuditSecretsPolicyTest(unittest.TestCase):
    def test_alarm_forbidden_staged_kb(self) -> None:
        with mock.patch.object(
            audit_secrets,
            "_staged_paths",
            return_value=["agentic/hermes/.kb/_index/catalog.json"],
        ):
            with self.assertRaises(SystemExit) as ctx:
                audit_secrets._alarm_forbidden(audit_secrets._staged_paths())
            self.assertEqual(ctx.exception.code, 1)

    def test_alarm_forbidden_staged_venv(self) -> None:
        with self.assertRaises(SystemExit):
            audit_secrets._alarm_forbidden([".venv/lib/python3.11/site-packages/foo.py"])

    def test_tracked_only_excludes_local_kb_on_disk(self) -> None:
        tracked = audit_secrets._tracked_paths()
        self.assertNotIn("agentic/hermes/.kb/_index/applications.db", tracked)
        self.assertNotIn(".kb/_index/catalog.json", tracked)

    def test_all_scan_uses_tracked_paths_only(self) -> None:
        source = (ROOT / "scripts" / "audit_secrets.py").read_text(encoding="utf-8")
        self.assertIn("ls-files", source)
        self.assertIn("_scannable_tracked_paths", source)
        self.assertNotIn('"scan", "--baseline", str(BASELINE), "--all-files"', source)

    def test_staged_alarms_before_piiignore_filter(self) -> None:
        """Staging .kb must fail even though .piiignore would exempt it with --observe-piiignore."""
        with mock.patch.object(
            audit_secrets,
            "_staged_paths",
            return_value=["agentic/hermes/.kb/private/notes.md"],
        ):
            with self.assertRaises(SystemExit):
                audit_secrets._staged_scannable_paths(observe_piiignore=True)


if __name__ == "__main__":
    unittest.main()
