from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.kb.secrets_vault import (  # noqa: E402
    delete_entry,
    list_entries,
    load_entry,
    set_entry,
    unlock_vault,
    validate_entry_key,
    vault_path,
)


class SecretsVaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kb_root = REPO / "agentic" / "hermes" / ".runtime" / "test_kb_secrets"
        self.kb_root.mkdir(parents=True, exist_ok=True)
        self.path = vault_path(self.kb_root)
        if self.path.is_file():
            self.path.unlink()

    def tearDown(self) -> None:
        if self.path.is_file():
            self.path.unlink()

    def test_validate_entry_key(self) -> None:
        self.assertEqual(validate_entry_key("gmail_oauth"), "gmail_oauth")
        with self.assertRaises(ValueError):
            validate_entry_key("bad-key")

    def test_roundtrip_set_list_load_delete(self) -> None:
        phrase = "test-passphrase-12chars"
        payload = {"refresh_token": "rt-abc", "client_id": "cid", "client_secret": "sec"}
        set_entry(
            self.path,
            entry_key="gmail_oauth",
            entry_type="oauth_gmail",
            payload=payload,
            passphrase=phrase,
        )
        self.assertTrue(self.path.is_file())
        unlock = unlock_vault(self.path, phrase)
        self.assertTrue(unlock["ok"])
        self.assertEqual(unlock["entries"], 1)

        rows = list_entries(self.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], "gmail_oauth")
        self.assertEqual(rows[0]["type"], "oauth_gmail")
        self.assertNotIn("refresh_token", json.dumps(rows))

        entry_type, loaded = load_entry(self.path, entry_key="gmail_oauth", passphrase=phrase)
        self.assertEqual(entry_type, "oauth_gmail")
        self.assertEqual(loaded["refresh_token"], "rt-abc")

        self.assertTrue(delete_entry(self.path, entry_key="gmail_oauth", passphrase=phrase))
        self.assertEqual(list_entries(self.path), [])

    def test_wrong_passphrase_fails_unlock(self) -> None:
        set_entry(
            self.path,
            entry_key="yahoo_imap",
            entry_type="imap_app_password",
            payload={"host": "imap.mail.yahoo.com", "username": "u", "password": "p"},
            passphrase="correct-passphrase-1",
        )
        with self.assertRaises(Exception):
            unlock_vault(self.path, "wrong-passphrase-1")


if __name__ == "__main__":
    unittest.main()
