"""Email intake connectors — recruiter_message → opportunity_artifact/v1.

Credentials are read from the encrypted vault via lib.kb.secrets_vault.
"""

from __future__ import annotations

import hashlib
import imaplib
import re
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from lib.kb.secrets_vault import load_entry, resolve_passphrase, vault_path

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

DEFAULT_GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)
DEFAULT_OUTLOOK_SCOPES = ("https://graph.microsoft.com/Mail.Read",)
GRAPH_MAIL_URL = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"


@dataclass
class InboundMessage:
    """Normalized recruiter email before opportunity mapping."""

    message_id: str
    channel: str  # email
    from_addr: str
    subject: str
    body: str
    received_at: str
    urls_found: list[str] = field(default_factory=list)
    provider: str = ""
    raw_headers: dict[str, str] = field(default_factory=dict)


class EmailConnector(ABC):
    """Poll unread recruiter mail from one provider account."""

    provider: str = "abstract"

    @abstractmethod
    def list_unread(self, *, limit: int = 20) -> list[InboundMessage]:
        """Return newest unread messages (provider-specific)."""


class GmailOAuthConnector(EmailConnector):
    provider = "gmail"

    def __init__(self, oauth_payload: dict[str, Any]) -> None:
        self._oauth = oauth_payload

    def list_unread(self, *, limit: int = 20) -> list[InboundMessage]:
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Gmail poll requires google-auth and google-api-python-client — "
                "pip install -r requirements-email.txt"
            ) from exc

        from .email_mime import parse_gmail_api_message

        scopes = self._oauth.get("scopes") or list(DEFAULT_GMAIL_SCOPES)
        creds = Credentials(
            token=None,
            refresh_token=str(self._oauth["refresh_token"]),
            token_uri=str(
                self._oauth.get("token_uri") or "https://oauth2.googleapis.com/token"
            ),
            client_id=str(self._oauth["client_id"]),
            client_secret=str(self._oauth["client_secret"]),
            scopes=list(scopes),
        )
        # security-reviewed: Gmail API over HTTPS; tokens from encrypted local vault
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        listing = (
            service.users()
            .messages()
            .list(userId="me", q="is:unread", maxResults=max(1, int(limit)))
            .execute()
        )
        messages: list[InboundMessage] = []
        for item in listing.get("messages") or []:
            mid = item.get("id")
            if not mid:
                continue
            full = (
                service.users()
                .messages()
                .get(userId="me", id=mid, format="full")
                .execute()
            )
            messages.append(parse_gmail_api_message(full))
        return messages


class OutlookGraphConnector(EmailConnector):
    provider = "outlook"

    def __init__(self, oauth_payload: dict[str, Any]) -> None:
        self._oauth = oauth_payload

    def list_unread(self, *, limit: int = 20) -> list[InboundMessage]:
        try:
            import msal
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "Outlook poll requires msal and requests — pip install -r requirements-email.txt"
            ) from exc

        from .email_mime import parse_graph_api_message

        tenant = str(self._oauth.get("tenant_id") or "common")
        scopes = self._oauth.get("scopes") or list(DEFAULT_OUTLOOK_SCOPES)
        app = msal.ConfidentialClientApplication(
            str(self._oauth["client_id"]),
            authority=f"https://login.microsoftonline.com/{tenant}",
            client_credential=str(self._oauth["client_secret"]),
        )
        token_result = app.acquire_token_by_refresh_token(
            str(self._oauth["refresh_token"]),
            scopes=list(scopes),
        )
        if "access_token" not in token_result:
            err = token_result.get("error_description") or token_result.get("error")
            raise RuntimeError(f"Outlook token refresh failed: {err}")

        # security-reviewed: Microsoft Graph over HTTPS; bearer from vault-stored refresh token
        resp = requests.get(
            GRAPH_MAIL_URL,
            params={
                "$filter": "isRead eq false",
                "$top": max(1, int(limit)),
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,receivedDateTime,body,isRead,internetMessageId",
            },
            headers={"Authorization": f"Bearer {token_result['access_token']}"},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        return [parse_graph_api_message(item) for item in payload.get("value") or []]


class ImapAppPasswordConnector(EmailConnector):
    provider = "imap"

    def __init__(self, imap_payload: dict[str, Any]) -> None:
        self._imap = imap_payload

    def list_unread(self, *, limit: int = 20) -> list[InboundMessage]:
        from .email_mime import parse_rfc822_bytes

        host = str(self._imap["host"])
        port = int(self._imap.get("port") or 993)
        username = str(self._imap["username"])
        password = str(self._imap["password"])
        use_ssl = bool(self._imap.get("use_ssl", True))
        mailbox = str(self._imap.get("mailbox") or "INBOX")

        # security-reviewed: IMAP credentials from encrypted vault; TLS when use_ssl=true
        if use_ssl:
            conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())
        else:
            conn = imaplib.IMAP4(host, port)
        try:
            conn.login(username, password)
            status, _ = conn.select(mailbox, readonly=True)
            if status != "OK":
                raise RuntimeError(f"IMAP select {mailbox!r} failed: {status}")
            status, data = conn.search(None, "UNSEEN")
            if status != "OK":
                raise RuntimeError(f"IMAP search UNSEEN failed: {status}")
            uids = [uid for uid in (data[0] or b"").split() if uid]
            uids = uids[-max(1, int(limit)) :]
            messages: list[InboundMessage] = []
            for uid in reversed(uids):
                status, msg_data = conn.fetch(uid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                if not isinstance(raw, (bytes, bytearray)):
                    continue
                message_id = f"imap:{host}:{uid.decode('ascii', errors='ignore')}"
                messages.append(
                    parse_rfc822_bytes(bytes(raw), message_id=message_id, provider="imap")
                )
            return messages
        finally:
            try:
                conn.logout()
            except imaplib.IMAP4.error:
                pass


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_RE.findall(text or ""):
        cleaned = match.rstrip(").,;]")
        if cleaned not in seen:
            seen.add(cleaned)
            urls.append(cleaned)
    return urls


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_message_id(msg: InboundMessage) -> str:
    digest = hashlib.sha256(
        f"{msg.from_addr}|{msg.received_at}|{msg.subject}|{msg.body[:200]}".encode()
    ).hexdigest()[:16]
    return f"msg:{digest}"


def message_to_opportunity(msg: InboundMessage) -> dict[str, Any]:
    """Map inbound mail to opportunity_artifact/v1 (recruiter_message)."""
    urls = msg.urls_found or extract_urls(msg.body)
    apply_url = urls[0] if urls else ""
    opportunity_id_source = apply_url or f"{msg.from_addr}|{msg.subject}|{msg.received_at}"
    digest = hashlib.sha256(opportunity_id_source.encode()).hexdigest()[:16]
    discovered = msg.received_at or _now_iso()

    company = _guess_company(msg)
    title = _guess_title(msg)

    return {
        "schema": "opportunity_artifact/v1",
        "opportunity_id": f"opp:{digest}",
        "source_kind": "recruiter_message",
        "source_url": urls[0] if urls else None,
        "apply_url": apply_url or None,
        "canonical_url": None,
        "title": title,
        "company": company,
        "location": None,
        "employment_type": None,
        "job_description": msg.body,
        "recruiter_message": {
            "channel": msg.channel,
            "from": msg.from_addr,
            "subject": msg.subject,
            "body": msg.body,
            "urls_found": urls,
            "message_id": msg.message_id or _stable_message_id(msg),
            "provider": msg.provider,
        },
        "provenance": [
            {
                "kind": "message_body",
                "field": "job_description",
                "at": discovered,
            },
        ],
        "discovered_at": discovered,
        "dedupe_key": f"{company}|{title}|{apply_url or msg.message_id}",
        "researcher_notes": f"email intake via {msg.provider or 'email'}",
    }


def _guess_company(msg: InboundMessage) -> str:
    subj = (msg.subject or "").strip()
    for prefix in ("Re:", "Fwd:", "FW:"):
        if subj.lower().startswith(prefix.lower()):
            subj = subj[len(prefix) :].strip()
    if " at " in subj:
        return subj.split(" at ", 1)[1].split(" - ", 1)[0].strip() or "Unknown"
    domain = ""
    if "@" in msg.from_addr:
        domain = msg.from_addr.split("@", 1)[1].strip().lower()
        domain = domain.split(">", 1)[0]
    if domain and domain not in ("gmail.com", "outlook.com", "yahoo.com", "hotmail.com"):
        host = domain.split(".", 1)[0]
        return host.replace("-", " ").title()
    return "Unknown"


def _guess_title(msg: InboundMessage) -> str:
    subj = (msg.subject or "").strip()
    for prefix in ("Re:", "Fwd:", "FW:"):
        if subj.lower().startswith(prefix.lower()):
            subj = subj[len(prefix) :].strip()
    if " at " in subj:
        return subj.split(" at ", 1)[0].strip() or "Role from recruiter email"
    return subj or "Role from recruiter email"


def connector_for_vault_entry(entry_type: str, payload: dict[str, Any]) -> EmailConnector:
    if entry_type == "oauth_gmail":
        return GmailOAuthConnector(payload)
    if entry_type == "oauth_outlook":
        return OutlookGraphConnector(payload)
    if entry_type == "imap_app_password":
        return ImapAppPasswordConnector(payload)
    raise ValueError(f"entry type {entry_type!r} is not an email connector")


def load_email_connector(
    kb_root,
    *,
    vault_key: str,
    passphrase: str | None = None,
) -> EmailConnector:
    """Build a connector from a vault entry. Passphrase from env if omitted."""
    from pathlib import Path

    root = Path(kb_root)
    phrase = passphrase or resolve_passphrase(prompt=False)
    entry_type, payload = load_entry(vault_path(root), entry_key=vault_key, passphrase=phrase)
    return connector_for_vault_entry(entry_type, payload)


def is_likely_job_posting_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    hints = (
        "linkedin.com",
        "indeed.com",
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "myworkdayjobs.com",
        "ziprecruiter.com",
    )
    return any(h in host for h in hints)
