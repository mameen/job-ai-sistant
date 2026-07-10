#!/usr/bin/env python3
"""Fixture-backed tests for scripts/check_secrets.py — no mocks."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_spec = importlib.util.spec_from_file_location("check_secrets", _SCRIPTS / "check_secrets.py")
assert _spec and _spec.loader
check_secrets = importlib.util.module_from_spec(_spec)
sys.modules["check_secrets"] = check_secrets
_spec.loader.exec_module(check_secrets)


def _fake_github_pat() -> str:
    return "ghp_" + ("a" * 36)


def _fake_openai_key() -> str:
    return "sk-" + ("b" * 24)


def _fake_home_path() -> str:
    return '{"source": "/' + "Users/alice/src/job-ai-sistant/app" + '"}'


class CheckSecretsTest(unittest.TestCase):
    def test_clean_fixture_passes(self) -> None:
        path = ROOT / "tests/fixtures/recruiter_sample.eml"
        self.assertEqual(check_secrets.scan_paths([path]), [])

    def test_blocks_github_pat(self) -> None:
        findings = check_secrets.scan_line("config.yaml", 1, f"token: {_fake_github_pat()}")
        self.assertTrue(findings)
        self.assertTrue(any(f.kind == "secret" for f in findings))

    def test_blocks_home_path(self) -> None:
        findings = check_secrets.scan_line("agentic/hermes/admin/manage.py", 3, _fake_home_path())
        self.assertTrue(any("home path" in f.detail for f in findings))

    def test_allows_example_json_credentials(self) -> None:
        path = ROOT / "agentic/hermes/kb/scaffold/private/secrets/oauth_gmail.example.json"
        self.assertEqual(check_secrets.scan_paths([path]), [])

    def test_blocks_vault_json_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vault.json"
            path.write_text('{"entries":[]}\n', encoding="utf-8")
            findings = check_secrets.scan_paths([path])
            self.assertTrue(any("forbidden sensitive file" in f.detail for f in findings))

    def test_blocks_non_example_secrets_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oauth_gmail.json"
            path.write_text(
                '{"client_secret":"real-secret-value-here","refresh_token":"abc"}\n',
                encoding="utf-8",
            )
            findings = check_secrets.scan_paths([path])
            self.assertTrue(findings)

    def test_allows_placeholder_assignment(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".env.example", delete=False) as fh:
            fh.write("# OPENAI_API_KEY=sk-...\n")
            path = Path(fh.name)
        try:
            self.assertEqual(check_secrets.scan_paths([path]), [])
        finally:
            path.unlink(missing_ok=True)

    def test_blocks_venv_path(self) -> None:
        findings = check_secrets.scan_paths(
            [ROOT / ".venv/lib/python3.11/site-packages/pkg/module.py"]
        )
        self.assertTrue(any("forbidden local-only path" in f.detail for f in findings))


if __name__ == "__main__":
    unittest.main()
