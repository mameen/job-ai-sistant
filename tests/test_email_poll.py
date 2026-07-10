from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

from lib.career.email_intake import InboundMessage  # noqa: E402
from lib.career.email_mime import parse_gmail_api_message, parse_graph_api_message, parse_rfc822_bytes  # noqa: E402
from lib.career.email_poll import load_poll_state, poll_connector, run_email_poll  # noqa: E402


class EmailMimeTests(unittest.TestCase):
    def test_parse_rfc822_fixture(self) -> None:
        raw = (REPO / "tests" / "fixtures" / "recruiter_sample.eml").read_bytes()
        msg = parse_rfc822_bytes(raw, message_id="imap:test:1", provider="imap")
        self.assertIn("Engineering Manager", msg.subject)
        self.assertIn("jane.recruiter@acme.com", msg.from_addr)
        self.assertIn("https://jobs.lever.co/acme/eng-manager-123", msg.urls_found[0])

    def test_parse_gmail_api_message(self) -> None:
        api_msg = {
            "id": "abc123",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Staff Engineer at Beta"},
                    {"name": "From", "value": "hr@beta.com"},
                    {"name": "Date", "value": "Wed, 09 Jul 2026 08:00:00 +0000"},
                ],
                "mimeType": "text/plain",
                "body": {
                    "data": "SGkgdGhlcmUgaHR0cHM6Ly9ib2FyZHMuZ3JlZW5ob3VzZS5pby9iZXRhL2pvYnMvMQ=="
                },
            },
        }
        msg = parse_gmail_api_message(api_msg)
        self.assertEqual(msg.message_id, "gmail:abc123")
        self.assertIn("greenhouse.io", msg.urls_found[0])

    def test_parse_graph_api_message(self) -> None:
        item = {
            "id": "graph-1",
            "subject": "Director at Gamma",
            "from": {"emailAddress": {"address": "talent@gamma.com"}},
            "receivedDateTime": "2026-07-09T08:00:00Z",
            "body": {"contentType": "text", "content": "Role link https://jobs.lever.co/gamma/1"},
        }
        msg = parse_graph_api_message(item)
        self.assertEqual(msg.provider, "outlook")
        self.assertIn("gamma", msg.urls_found[0])


class EmailPollTests(unittest.TestCase):
    def test_poll_connector_dedupes_seen(self) -> None:
        class FakeConnector:
            provider = "imap"

            def list_unread(self, *, limit: int = 20) -> list[InboundMessage]:
                return [
                    InboundMessage(
                        message_id="imap:1",
                        channel="email",
                        from_addr="a@b.com",
                        subject="Role",
                        body="https://jobs.lever.co/x/1",
                        received_at="2026-07-09T08:00:00Z",
                        urls_found=["https://jobs.lever.co/x/1"],
                        provider="imap",
                    ),
                    InboundMessage(
                        message_id="imap:2",
                        channel="email",
                        from_addr="c@d.com",
                        subject="Other",
                        body="hello",
                        received_at="2026-07-09T08:01:00Z",
                        provider="imap",
                    ),
                ]

        fresh, fetched, skipped = poll_connector(
            FakeConnector(), limit=10, seen_ids={"imap:1"}
        )
        self.assertEqual(len(fetched), 2)
        self.assertEqual(skipped, 1)
        self.assertEqual(len(fresh), 1)
        self.assertEqual(fresh[0].message_id, "imap:2")

    def test_run_email_poll_writes_artifact_and_state(self) -> None:
        class FakeConnector:
            provider = "gmail"

            def list_unread(self, *, limit: int = 20) -> list[InboundMessage]:
                return [
                    InboundMessage(
                        message_id="gmail:fixture",
                        channel="email",
                        from_addr="jane@acme.com",
                        subject="Engineering Manager at Acme",
                        body="Apply https://jobs.lever.co/acme/1",
                        received_at="2026-07-09T08:00:00Z",
                        urls_found=["https://jobs.lever.co/acme/1"],
                        provider="gmail",
                    )
                ]

        runtime = REPO / "agentic" / "hermes" / ".runtime" / "test_email_poll"
        intake = REPO / "agentic" / "hermes" / ".generated" / "intake_test"
        runtime.mkdir(parents=True, exist_ok=True)
        intake.mkdir(parents=True, exist_ok=True)
        state_file = runtime / "email_poll_state.json"
        if state_file.is_file():
            state_file.unlink()
        for old in intake.glob("email_poll_*.json"):
            old.unlink()

        connector = FakeConnector()
        result = run_email_poll(
            connector=connector,
            vault_key="gmail_oauth",
            runtime_dir=runtime,
            intake_dir=intake,
            limit=5,
        )
        self.assertEqual(result["count"], 1)
        artifact = Path(result["artifact"])
        self.assertTrue(artifact.is_file())
        envelope = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(envelope["schema"], "email_poll/v1")
        self.assertEqual(envelope["opportunities"][0]["source_kind"], "recruiter_message")
        seen = load_poll_state(state_file)
        self.assertIn("gmail:fixture", seen)

        result2 = run_email_poll(
            connector=connector,
            vault_key="gmail_oauth",
            runtime_dir=runtime,
            intake_dir=intake,
            limit=5,
        )
        self.assertEqual(result2["count"], 0)
        self.assertEqual(result2["skipped_seen"], 1)

        state_file.unlink(missing_ok=True)
        for old in intake.glob("email_poll_*.json"):
            old.unlink()


if __name__ == "__main__":
    unittest.main()
