"""RFC822 / provider API → InboundMessage parsing for email intake."""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Any

from .email_intake import InboundMessage, extract_urls

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (UnicodeError, TypeError, ValueError):
        return value


def _to_iso(dt: datetime | None) -> str:
    if dt is None:
        return _now_iso()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _html_to_text(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _extract_body_from_email(msg) -> str:
    """Walk multipart MIME and return best plain-text body."""
    if msg.is_multipart():
        plain_parts: list[str] = []
        html_parts: list[str] = []
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = (part.get_content_type() or "").lower()
            try:
                payload = part.get_payload(decode=True)
            except (TypeError, ValueError):
                continue
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain":
                plain_parts.append(text.strip())
            elif ctype == "text/html":
                html_parts.append(_html_to_text(text))
        if plain_parts:
            return "\n\n".join(p for p in plain_parts if p)
        if html_parts:
            return "\n\n".join(p for p in html_parts if p)
        return ""
    try:
        payload = msg.get_payload(decode=True)
    except (TypeError, ValueError):
        payload = None
    if not payload:
        raw = msg.get_payload()
        return str(raw).strip() if raw else ""
    charset = msg.get_content_charset() or "utf-8"
    try:
        text = payload.decode(charset, errors="replace")
    except LookupError:
        text = payload.decode("utf-8", errors="replace")
    if (msg.get_content_type() or "").lower() == "text/html":
        return _html_to_text(text)
    return text.strip()


def parse_rfc822_bytes(
    raw: bytes,
    *,
    message_id: str,
    provider: str,
) -> InboundMessage:
    """Parse raw RFC822 bytes (IMAP FETCH) into InboundMessage."""
    msg = message_from_bytes(raw)
    subject = _decode_header(msg.get("Subject"))
    from_addr = _decode_header(msg.get("From"))
    date_hdr = msg.get("Date")
    received_at = _now_iso()
    if date_hdr:
        try:
            received_at = _to_iso(parsedate_to_datetime(date_hdr))
        except (TypeError, ValueError, OverflowError):
            received_at = _now_iso()
    body = _extract_body_from_email(msg)
    urls = extract_urls(body)
    return InboundMessage(
        message_id=message_id,
        channel="email",
        from_addr=from_addr,
        subject=subject,
        body=body,
        received_at=received_at,
        urls_found=urls,
        provider=provider,
        raw_headers={
            "message-id": _decode_header(msg.get("Message-ID")),
            "subject": subject,
        },
    )


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return raw.decode("utf-8", errors="replace")


def _gmail_body_from_payload(payload: dict[str, Any]) -> str:
    mime = payload.get("mimeType") or ""
    body_data = (payload.get("body") or {}).get("data")
    if body_data and mime in ("text/plain", "text/html"):
        text = _b64url_decode(body_data)
        return _html_to_text(text) if mime == "text/html" else text.strip()
    parts = payload.get("parts") or []
    plain: list[str] = []
    html: list[str] = []
    for part in parts:
        part_mime = part.get("mimeType") or ""
        part_body = (part.get("body") or {}).get("data")
        if part_body and part_mime == "text/plain":
            plain.append(_b64url_decode(part_body).strip())
        elif part_body and part_mime == "text/html":
            html.append(_html_to_text(_b64url_decode(part_body)))
        elif part.get("parts"):
            nested = _gmail_body_from_payload(part)
            if nested:
                plain.append(nested)
    if plain:
        return "\n\n".join(plain)
    if html:
        return "\n\n".join(html)
    return ""


def parse_gmail_api_message(api_message: dict[str, Any]) -> InboundMessage:
    """Parse Gmail API users.messages.get (format=full) response."""
    mid = str(api_message.get("id") or "")
    headers = {
        (h.get("name") or "").lower(): h.get("value") or ""
        for h in (api_message.get("payload") or {}).get("headers") or []
    }
    subject = _decode_header(headers.get("subject"))
    from_addr = _decode_header(headers.get("from"))
    date_hdr = headers.get("date")
    received_at = _now_iso()
    if date_hdr:
        try:
            received_at = _to_iso(parsedate_to_datetime(date_hdr))
        except (TypeError, ValueError, OverflowError):
            received_at = _now_iso()
    body = _gmail_body_from_payload(api_message.get("payload") or {})
    urls = extract_urls(body)
    return InboundMessage(
        message_id=f"gmail:{mid}",
        channel="email",
        from_addr=from_addr,
        subject=subject,
        body=body,
        received_at=received_at,
        urls_found=urls,
        provider="gmail",
        raw_headers={"message-id": headers.get("message-id", "")},
    )


def parse_graph_api_message(item: dict[str, Any]) -> InboundMessage:
    """Parse Microsoft Graph message resource."""
    mid = str(item.get("id") or "")
    subject = str(item.get("subject") or "")
    from_obj = ((item.get("from") or {}).get("emailAddress") or {})
    from_addr = from_obj.get("address") or from_obj.get("name") or ""
    received_at = str(item.get("receivedDateTime") or _now_iso())
    if received_at and not received_at.endswith("Z"):
        received_at = received_at.replace("+00:00", "Z")
    body_obj = item.get("body") or {}
    content = str(body_obj.get("content") or "")
    if (body_obj.get("contentType") or "").lower() == "html":
        content = _html_to_text(content)
    urls = extract_urls(content)
    return InboundMessage(
        message_id=f"outlook:{mid}",
        channel="email",
        from_addr=from_addr,
        subject=subject,
        body=content.strip(),
        received_at=received_at,
        urls_found=urls,
        provider="outlook",
        raw_headers={"internetMessageId": str(item.get("internetMessageId") or "")},
    )
