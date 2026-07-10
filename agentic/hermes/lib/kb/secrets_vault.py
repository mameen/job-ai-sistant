"""Encrypted secrets vault — AES-256-GCM + PBKDF2 (local, gitignored).

Security: decrypted payloads must never be logged or passed to LLM prompts.
Only infrastructure adapters (email poll, optional session loaders) call load_entry.
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import UTC, datetime
from getpass import getpass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SCHEMA = "secrets_vault/v1"
VAULT_FILENAME = "vault.json"
SECRETS_DIR_NAME = "secrets"
ENTRY_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
KDF_ITERATIONS = 600_000
SALT_BYTES = 16
NONCE_BYTES = 12

ENTRY_TYPES = frozenset(
    {
        "oauth_gmail",
        "oauth_outlook",
        "imap_app_password",
        "linkedin_session",
        "proxy_list",
    }
)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def secrets_dir(kb_root: Path) -> Path:
    return kb_root / "private" / SECRETS_DIR_NAME


def vault_path(kb_root: Path) -> Path:
    return secrets_dir(kb_root) / VAULT_FILENAME


def validate_entry_key(key: str) -> str:
    cleaned = (key or "").strip().lower()
    if not ENTRY_KEY_RE.fullmatch(cleaned):
        raise ValueError(
            "entry key must match ^[a-z][a-z0-9_]{1,47}$ (e.g. gmail_oauth, yahoo_imap)"
        )
    return cleaned


def validate_entry_type(entry_type: str) -> str:
    cleaned = (entry_type or "").strip().lower()
    if cleaned not in ENTRY_TYPES:
        raise ValueError(f"unsupported entry type {cleaned!r} — allowed: {', '.join(sorted(ENTRY_TYPES))}")
    return cleaned


def resolve_passphrase(*, prompt: bool = True) -> str:
    """Read vault passphrase from env or interactive prompt."""
    env_val = (os.environ.get("CAREER_VAULT_PASSPHRASE") or "").strip()
    if env_val:
        return env_val
    if not prompt:
        raise RuntimeError(
            "CAREER_VAULT_PASSPHRASE not set — export it or run interactively"
        )
    first = getpass("Vault passphrase: ")
    second = getpass("Confirm passphrase: ")
    if first != second:
        raise RuntimeError("passphrases do not match")
    if len(first) < 12:
        raise RuntimeError("passphrase must be at least 12 characters")
    return first


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    # security-reviewed: PBKDF2-SHA256 600k iterations for local vault key derivation
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def _encrypt_payload(key: bytes, payload: dict[str, Any]) -> tuple[str, str]:
    nonce = os.urandom(NONCE_BYTES)
    aes = AESGCM(key)
    plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ciphertext = aes.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce).decode("ascii"), base64.b64encode(ciphertext).decode("ascii")


def _decrypt_payload(key: bytes, nonce_b64: str, ciphertext_b64: str) -> dict[str, Any]:
    nonce = base64.b64decode(nonce_b64)
    ciphertext = base64.b64decode(ciphertext_b64)
    aes = AESGCM(key)
    plaintext = aes.decrypt(nonce, ciphertext, None)
    data = json.loads(plaintext.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("decrypted entry is not a JSON object")
    return data


def _new_vault_document(*, salt: bytes) -> dict[str, Any]:
    now = _now_iso()
    return {
        "schema": SCHEMA,
        "created_at": now,
        "updated_at": now,
        "kdf": {
            "name": "pbkdf2-sha256",
            "salt": base64.b64encode(salt).decode("ascii"),
            "iterations": KDF_ITERATIONS,
        },
        "entries": {},
    }


def load_vault_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("vault file must be a JSON object")
    if data.get("schema") != SCHEMA:
        raise ValueError(f"unsupported vault schema: {data.get('schema')!r}")
    return data


def save_vault_document(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at"] = _now_iso()
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def unlock_vault(path: Path, passphrase: str) -> dict[str, Any]:
    """Verify passphrase by decrypting every entry (or empty vault)."""
    doc = load_vault_document(path)
    if not doc:
        return {"ok": True, "entries": 0, "message": "vault not created yet"}
    salt = base64.b64decode(doc["kdf"]["salt"])
    key = _derive_key(passphrase, salt)
    entries = doc.get("entries") or {}
    for entry_key, entry in entries.items():
        _decrypt_payload(key, entry["nonce"], entry["ciphertext"])
    return {"ok": True, "entries": len(entries), "message": "vault unlocked"}


def list_entries(path: Path) -> list[dict[str, str]]:
    doc = load_vault_document(path)
    if not doc:
        return []
    rows: list[dict[str, str]] = []
    for key, entry in sorted((doc.get("entries") or {}).items()):
        rows.append(
            {
                "key": key,
                "type": str(entry.get("type") or ""),
                "updated_at": str(entry.get("updated_at") or ""),
            }
        )
    return rows


def set_entry(
    path: Path,
    *,
    entry_key: str,
    entry_type: str,
    payload: dict[str, Any],
    passphrase: str,
) -> None:
    key_name = validate_entry_key(entry_key)
    type_name = validate_entry_type(entry_type)
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    doc = load_vault_document(path)
    if not doc:
        salt = os.urandom(SALT_BYTES)
        doc = _new_vault_document(salt=salt)
    salt = base64.b64decode(doc["kdf"]["salt"])
    key = _derive_key(passphrase, salt)
    nonce_b64, ciphertext_b64 = _encrypt_payload(key, payload)

    entries = doc.setdefault("entries", {})
    entries[key_name] = {
        "type": type_name,
        "updated_at": _now_iso(),
        "nonce": nonce_b64,
        "ciphertext": ciphertext_b64,
    }
    save_vault_document(path, doc)


def delete_entry(path: Path, *, entry_key: str, passphrase: str) -> bool:
    key_name = validate_entry_key(entry_key)
    doc = load_vault_document(path)
    if not doc:
        return False
    entries = doc.get("entries") or {}
    if key_name not in entries:
        return False
    # Verify passphrase before mutating
    salt = base64.b64decode(doc["kdf"]["salt"])
    key = _derive_key(passphrase, salt)
    for entry in entries.values():
        _decrypt_payload(key, entry["nonce"], entry["ciphertext"])
    del entries[key_name]
    save_vault_document(path, doc)
    return True


def load_entry(
    path: Path,
    *,
    entry_key: str,
    passphrase: str,
) -> tuple[str, dict[str, Any]]:
    """Return (entry_type, decrypted_payload). Caller must not log the payload."""
    key_name = validate_entry_key(entry_key)
    doc = load_vault_document(path)
    if not doc:
        raise FileNotFoundError("vault not created — run: manage.py secrets set …")
    entry = (doc.get("entries") or {}).get(key_name)
    if not entry:
        raise KeyError(f"vault entry not found: {key_name}")
    salt = base64.b64decode(doc["kdf"]["salt"])
    key = _derive_key(passphrase, salt)
    payload = _decrypt_payload(key, entry["nonce"], entry["ciphertext"])
    return str(entry.get("type") or ""), payload
