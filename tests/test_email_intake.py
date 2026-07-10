from __future__ import annotations

import sys
import unittest

REPO = __import__("pathlib").Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.career.email_intake import (  # noqa: E402
    GmailOAuthConnector,
    ImapAppPasswordConnector,
    InboundMessage,
    connector_for_vault_entry,
    extract_urls,
    is_likely_job_posting_url,
    message_to_opportunity,
)


class EmailIntakeTests(unittest.TestCase):
    def test_extract_urls(self) -> None:
        body = "See https://jobs.lever.co/acme/123 and https://greenhouse.io/x."
        urls = extract_urls(body)
        self.assertEqual(len(urls), 2)
        self.assertIn("https://jobs.lever.co/acme/123", urls)

    def test_message_to_opportunity_recruiter_shape(self) -> None:
        msg = InboundMessage(
            message_id="msg:abc",
            channel="email",
            from_addr="recruiter@acme.com",
            subject="Engineering Manager at Acme",
            body="We are hiring.\nhttps://jobs.lever.co/acme/role",
            received_at="2026-07-09T08:00:00Z",
            urls_found=["https://jobs.lever.co/acme/role"],
            provider="gmail",
        )
        opp = message_to_opportunity(msg)
        self.assertEqual(opp["schema"], "opportunity_artifact/v1")
        self.assertEqual(opp["source_kind"], "recruiter_message")
        self.assertEqual(opp["company"], "Acme")
        self.assertEqual(opp["title"], "Engineering Manager")
        self.assertEqual(opp["apply_url"], "https://jobs.lever.co/acme/role")
        self.assertEqual(opp["recruiter_message"]["channel"], "email")

    def test_connector_for_vault_entry_types(self) -> None:
        gmail = connector_for_vault_entry("oauth_gmail", {"refresh_token": "x", "client_id": "a", "client_secret": "b"})
        self.assertIsInstance(gmail, GmailOAuthConnector)
        imap = connector_for_vault_entry(
            "imap_app_password",
            {"host": "imap.example.com", "username": "u", "password": "p"},
        )
        self.assertIsInstance(imap, ImapAppPasswordConnector)

    def test_is_likely_job_posting_url(self) -> None:
        self.assertTrue(is_likely_job_posting_url("https://boards.greenhouse.io/acme/jobs/1"))
        self.assertFalse(is_likely_job_posting_url("https://example.com/blog"))


if __name__ == "__main__":
    unittest.main()
