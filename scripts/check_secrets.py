#!/usr/bin/env python3
"""Scan git-staged (or given) files for secrets and sensitive PII/PHI.

Used by ``.githooks/pre-commit``. Run manually:

  python scripts/check_secrets.py --staged
  python scripts/check_secrets.py --all
  python scripts/check_secrets.py path/to/file.json
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from scan_ignore import (  # noqa: E402
    alarm_commit_paths,
    format_local_warnings,
    load_patterns,
    local_sensitive_warnings,
    forbidden_commit_reason,
    should_skip_audit_path,
)

# ── Repo-specific policy (Career Intelligence / Project Zazu) ────────────────
# Commit-forbidden paths live in scan_ignore.forbidden_commit_reason (single source).

_LAN_ALLOWLIST: tuple[str, ...] = (
    "agentic/hermes/admin/config/hermes_roles.yaml",
    "agentic/hermes/admin/config/hermes_roles.local.yaml.example",
    ".env.example",
    "docs/configuration.md",
    "SETUP.md",
    "README.md",
    "agentic/hermes/README.md",
    "agentic/hermes/admin/manage.py",
)

_FIXTURE_PREFIXES: tuple[str, ...] = ("tests/data/", "tests/fixtures/")

_SKIP_CONTENT_PREFIXES: tuple[str, ...] = (
    "tests/",
    "docs/",
    ".githooks/",
)

_ALLOWLISTED_EMAIL_DOMAINS = frozenset(
    {
        "example.com",
        "example.org",
        "example.net",
        "test.com",
        "localhost",
        "invalid",
        "acme.com",
        "cursor.com",
        "anthropic.com",
    }
)

# ── Shared heuristics ─────────────────────────────────────────────────────────

_PLACEHOLDER_MARKERS = (
    "paste",
    "example",
    "your",
    "here",
    "changeme",
    "placeholder",
    "redacted",
    "xxx",
    "token-here",
)

_PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "...",
        "changeme",
        "example",
        "placeholder",
        "redacted",
        "your-key-here",
        "your_key_here",
        "xxx",
        "sk-...",
        "sk-ant-...",
        "x",
        "p",
        "u",
        "a",
        "b",
        "sec",
        "rt-abc",
        "cid",
    }
)

_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|token|auth)\s*[=:]\s*['\"]?([^'\"#\s]{8,})"
)

_JSON_CRED_RE = re.compile(
    r'"(client_secret|refresh_token|password)"\s*:\s*"([^"]+)"'
)

_HUNK_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_SCANNER_TEST_FILE = "tests/test_check_secrets.py"


@dataclass(frozen=True)
class Finding:
    path: str
    line_no: int
    kind: str
    detail: str
    snippet: str


@dataclass(frozen=True)
class AddedLine:
    path: str
    line_no: int
    text: str


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_fixture(rel: str) -> bool:
    return rel.startswith(_FIXTURE_PREFIXES)


def _skip_email_scan(rel: str) -> bool:
    if rel.startswith("tests/") or _is_fixture(rel):
        return True
    return rel.endswith(".example.json") or rel.endswith(".example") or rel.endswith(".example.yaml")


def _lan_allowed(rel: str) -> bool:
    return rel in _LAN_ALLOWLIST or rel.endswith(".example") or rel.endswith(".example.yaml")


def _looks_like_placeholder(value: str) -> bool:
    lower = value.lower()
    if lower in _PLACEHOLDER_VALUES:
        return True
    if lower.startswith("your_"):
        return True
    if lower.endswith("..."):
        return True
    for m in _PLACEHOLDER_MARKERS:
        if lower == m or lower.startswith(f"{m}_") or lower.startswith(f"{m}-"):
            return True
    return False


def _skip_pii_rules(rel: str) -> bool:
    return rel.startswith("tests/") or _is_fixture(rel)


def _blocked_path(rel: str) -> str | None:
    return forbidden_commit_reason(rel)


def _staged_files() -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return []
    return [REPO / line.strip() for line in out.stdout.splitlines() if line.strip()]


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return []
    return [REPO / line.strip() for line in out.stdout.splitlines() if line.strip()]


def _worktree_files() -> list[Path]:
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return []
    paths: list[Path] = []
    for line in out.stdout.splitlines():
        if len(line) < 4:
            continue
        p = line[3:].strip()
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        if p:
            paths.append(REPO / p)
    return paths


def _staged_added_lines() -> list[AddedLine]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return []

    current = ""
    line_no = 0
    added: list[AddedLine] = []
    for line in out.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        m = _HUNK_RE.match(line)
        if m:
            line_no = int(m.group(1))
            continue
        if not current or not line:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added.append(AddedLine(current, line_no, line[1:]))
            line_no += 1
    return added


def _line_rules(rel: str) -> list[tuple[str, re.Pattern[str], str]]:
    rules: list[tuple[str, re.Pattern[str], str]] = [
        ("secret", re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
        ("secret", re.compile(r"ASIA[0-9A-Z]{16}"), "AWS temporary access key id"),
        ("secret", re.compile(r"ghp_[A-Za-z0-9]{36,}"), "GitHub personal access token"),
        ("secret", re.compile(r"github_pat_[A-Za-z0-9_]{22,}"), "GitHub fine-grained PAT"),
        ("secret", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
        ("secret", re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), "Anthropic API key"),
        (
            "secret",
            re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
            "private key block",
        ),
        ("secret", re.compile(r"Bearer [a-fA-F0-9]{32,}"), "bearer token"),
        (
            "pii",
            re.compile(r"/Users/[A-Za-z0-9._-]+/"),
            "absolute macOS home path (use repo-relative paths in committed files)",
        ),
        (
            "pii",
            re.compile(r"(?<![a-zA-Z])/home/[A-Za-z0-9._-]+/"),
            "absolute Linux home path (use repo-relative paths in committed files)",
        ),
        ("pii", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "US Social Security number pattern"),
        (
            "pii",
            re.compile(r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b"),
            "payment-card-like number (grouped digits)",
        ),
        (
            "phi",
            re.compile(r"(?i)\b(?:patient\s+id|medical\s+record(?:\s+number)?|mrn)\s*[:#]\s*\S+"),
            "patient / medical record identifier",
        ),
        (
            "pii",
            re.compile(
                r"\b[A-Za-z0-9._%+-]+@(?:gmail|yahoo|hotmail|outlook|icloud|protonmail|live)\."
            ),
            "personal email address",
        ),
        (
            "pii",
            re.compile(r"\b(?:\+1[-.\s]|1[-.\s])?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
            "US phone number pattern",
        ),
    ]

    if not _lan_allowed(rel):
        rules.append(
            (
                "pii",
                re.compile(r"\b(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b"),
                "private LAN IP address",
            )
        )

    if not _is_fixture(rel):
        rules.append(
            (
                "secret",
                re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
                "OpenAI-style API key",
            )
        )

    return rules


def _assignment_findings(rel: str, line: str, line_no: int) -> list[Finding]:
    if _is_fixture(rel):
        return []
    m = _ASSIGNMENT_RE.search(line)
    if not m:
        return []
    value = m.group(2).strip("'\"")
    if value.startswith("str(") or value.startswith("os.environ"):
        return []
    if _looks_like_placeholder(value):
        return []
    if value.startswith("${") and value.endswith("}"):
        return []
    return [
        Finding(
            path=rel,
            line_no=line_no,
            kind="secret",
            detail=f"credential assignment ({m.group(1)})",
            snippet=line.strip()[:120],
        )
    ]


def _json_credential_findings(rel: str, line: str, line_no: int) -> list[Finding]:
    if rel.endswith(".example.json") or _is_fixture(rel):
        return []
    findings: list[Finding] = []
    for m in _JSON_CRED_RE.finditer(line):
        field, value = m.group(1), m.group(2)
        if not _looks_like_placeholder(value):
            findings.append(
                Finding(
                    path=rel,
                    line_no=line_no,
                    kind="secret",
                    detail=f"non-placeholder JSON {field}",
                    snippet=line.strip()[:120],
                )
            )
    return findings


def _email_findings(rel: str, line: str, line_no: int) -> list[Finding]:
    if _skip_email_scan(rel):
        return []
    findings: list[Finding] = []
    for email in _EMAIL_RE.findall(line):
        domain = email.split("@", 1)[1].lower()
        if domain in _ALLOWLISTED_EMAIL_DOMAINS:
            continue
        findings.append(
            Finding(
                path=rel,
                line_no=line_no,
                kind="pii",
                detail=f"email with non-allowlisted domain ({domain})",
                snippet=line.strip()[:120],
            )
        )
        break
    return findings


def scan_line(rel: str, line_no: int, line: str) -> list[Finding]:
    """Scan a single line (used by pre-commit staged-diff mode and tests)."""
    findings: list[Finding] = []
    stripped = line.strip()
    if stripped.startswith("#") or stripped.startswith("//"):
        return findings

    findings.extend(_assignment_findings(rel, line, line_no))
    findings.extend(_json_credential_findings(rel, line, line_no))

    if not findings:
        for kind, pattern, detail in _line_rules(rel):
            if _skip_pii_rules(rel) and kind in {"pii", "phi"}:
                continue
            if pattern.search(line):
                if kind == "secret" and "Slack" in detail:
                    lower = line.lower()
                    if any(m in lower for m in ("paste", "placeholder", "your", "here", "example", "xxx", "token-here")):
                        break
                findings.append(
                    Finding(
                        path=rel,
                        line_no=line_no,
                        kind=kind,
                        detail=detail,
                        snippet=line.strip()[:120],
                    )
                )
                break

    if not findings:
        findings.extend(_email_findings(rel, line, line_no))
    return findings


def _blocked_filename_findings(path: Path) -> list[Finding]:
    rel = _rel(path)
    reason = _blocked_path(rel)
    if reason:
        return [
            Finding(
                path=rel,
                line_no=0,
                kind="secret",
                detail=reason,
                snippet=path.name,
            )
        ]
    return []


def _scan_file(path: Path) -> list[Finding]:
    rel = _rel(path)
    findings = _blocked_filename_findings(path)
    if findings:
        return findings

    if not path.is_file():
        return []

    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [
            Finding(
                path=rel,
                line_no=0,
                kind="error",
                detail=f"cannot read file: {exc}",
                snippet="",
            )
        ]

    if b"\x00" in raw[:8192]:
        return []

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []

    for line_no, line in enumerate(text.splitlines(), start=1):
        findings.extend(scan_line(rel, line_no, line))
    return findings


def _alarm_forbidden_paths(paths: list[Path]) -> None:
    alarm_commit_paths([_rel(p) for p in paths])


def scan_paths(paths: list[Path], *, observe_piiignore: bool = False) -> list[Finding]:
    patterns = load_patterns(REPO)
    all_findings: list[Finding] = []
    for path in paths:
        rel = _rel(path)
        blocked = _blocked_filename_findings(path)
        if blocked:
            all_findings.extend(blocked)
            continue
        if should_skip_audit_path(rel, patterns, observe_piiignore=observe_piiignore):
            continue
        all_findings.extend(_scan_file(path))
    return all_findings


def scan_staged() -> list[Finding]:
    """Scan staged added lines and blocked filenames (pre-commit)."""
    findings: list[Finding] = []
    for path in _staged_files():
        findings.extend(_blocked_filename_findings(path))
    for added in _staged_added_lines():
        if added.path == _SCANNER_TEST_FILE:
            continue
        findings.extend(scan_line(added.path, added.line_no, added.text))
    return findings


def _run_detect_secrets(paths: list[Path]) -> list[Finding]:
    """Optional second layer: Yelp detect-secrets (pip install detect-secrets)."""
    try:
        from detect_secrets.core.secrets_collection import SecretsCollection
        from detect_secrets.settings import default_settings
    except ImportError:
        return []

    findings: list[Finding] = []
    with default_settings():
        secrets = SecretsCollection()
        for path in paths:
            if not path.is_file():
                continue
            try:
                secrets.scan_file(str(path))
            except OSError:
                continue
        for secret in secrets:
            rel = _rel(Path(secret.filename))
            findings.append(
                Finding(
                    path=rel,
                    line_no=secret.line_number,
                    kind="secret",
                    detail=f"detect-secrets: {secret.type}",
                    snippet="",
                )
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan files for secrets and sensitive PII/PHI.")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Scan git-staged added lines only (pre-commit default).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan entire tracked tree (audit).",
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="Scan modified and untracked paths in the working tree.",
    )
    parser.add_argument(
        "--with-detect-secrets",
        action="store_true",
        help="Also run detect-secrets if installed (pip install detect-secrets).",
    )
    parser.add_argument(
        "--observe-piiignore",
        action="store_true",
        help="opt-in: honor .piiignore exemptions (default: scan commit content fully)",
    )
    parser.add_argument("paths", nargs="*", help="Explicit file paths to scan (full file).")
    args = parser.parse_args(argv)

    patterns = load_patterns(REPO)
    paths: list[Path] = []
    if args.staged:
        paths = _staged_files()
        _alarm_forbidden_paths(paths)
        findings = scan_staged()
        if not _staged_files() and not _staged_added_lines():
            return 0
    elif args.all:
        paths = _tracked_files()
        _alarm_forbidden_paths(paths)
        msg = format_local_warnings(
            local_sensitive_warnings(REPO, patterns, observe_piiignore=args.observe_piiignore)
        )
        if msg:
            print(msg, file=sys.stderr)
        findings = scan_paths(paths, observe_piiignore=args.observe_piiignore)
    elif args.worktree:
        paths = _worktree_files()
        _alarm_forbidden_paths(paths)
        findings = scan_paths(paths, observe_piiignore=args.observe_piiignore)
    else:
        paths = [Path(p) for p in args.paths]
        if not paths:
            parser.print_help()
            return 0
        findings = scan_paths(paths, observe_piiignore=args.observe_piiignore)

    if args.with_detect_secrets and paths:
        ds = _run_detect_secrets(paths)
        seen = {(f.path, f.line_no, f.detail) for f in findings}
        for f in ds:
            key = (f.path, f.line_no, f.detail)
            if key not in seen:
                findings.append(f)
                seen.add(key)

    if not findings:
        return 0

    print("ERROR: commit blocked — possible secrets or sensitive PII/PHI detected:\n", file=sys.stderr)
    for f in findings:
        loc = f"{f.path}:{f.line_no}" if f.line_no else f.path
        print(f"  [{f.kind}] {loc} — {f.detail}", file=sys.stderr)
        if f.snippet:
            print(f"         {f.snippet}", file=sys.stderr)
    print(
        "\nRemove or redact sensitive data before committing."
        " Emergency bypass: git commit --no-verify (avoid for normal work).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
