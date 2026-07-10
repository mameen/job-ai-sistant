"""Gitignore-style path exemptions for PII/secret audit scanners.

Reads ``.piiignore`` and ``.ignorepii`` (alias) from the repo root.
Syntax matches ``.gitignore`` (``#`` comments, ``/`` prefix, ``**``, ``*``).

Policy (default — no ``--observe-piiignore``):
- **Anything in a commit** (staged or tracked): full content scan; never skip via ``.piiignore``.
- **Forbidden paths** (``.kb/``, ``.env``, credentials, …): always **alarm** — never skippable,
  including with ``--observe-piiignore``.
- **``--all`` local trees:** warn if gitignored vault/venv dirs exist on disk (not in commit).
- ``.piiignore`` applies only when ``--observe-piiignore`` is passed (opt-in), and only for
  non-forbidden paths.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

IGNORE_FILENAMES = (".piiignore", ".ignorepii")

# Directory prefixes — if any path in a commit matches, alarm (never skippable).
FORBIDDEN_COMMIT_PREFIXES: tuple[str, ...] = (
    "agentic/hermes/.kb/",
    "agentic/hermes/.generated/",
    "agentic/hermes/.runtime/",
    ".kb/",
    "career_kb/",
    ".cache/",
    ".venv/",
    "venv/",
)

FORBIDDEN_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "credentials.json",
        "secrets.json",
        "vault.json",
        "id_rsa",
        "id_ed25519",
        ".API_KEY",
    }
)

FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".kdbx",
    ".credentials.json",
    "_credentials.json",
)

# Gitignored dirs that ``--all`` warns about when present on disk (not in the commit).
LOCAL_SENSITIVE_DIRS: tuple[str, ...] = (
    "agentic/hermes/.kb",
    "agentic/hermes/.generated",
    "agentic/hermes/.runtime",
    ".kb",
    "career_kb",
    ".cache",
    ".venv",
    "venv",
)


def load_patterns(repo: Path) -> tuple[str, ...]:
    patterns: list[str] = []
    for name in IGNORE_FILENAMES:
        path = repo / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return tuple(patterns)


def _normalize_rel(rel: str) -> str:
    """Normalize repo-relative paths without stripping leading dots from ``.venv`` etc."""
    rel = rel.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _match_pattern(rel: str, pattern: str) -> bool:
    rel = _normalize_rel(rel)
    pat = _normalize_rel(pattern)

    if pat.endswith("/"):
        prefix = pat.rstrip("/")
        return rel == prefix or rel.startswith(prefix + "/")

    if "/" in pat:
        return fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pat.lstrip("/"))

    if fnmatch.fnmatch(rel, pat):
        return True
    parts = rel.split("/")
    return any(fnmatch.fnmatch(part, pat) for part in parts)


def is_ignored(rel: str, patterns: tuple[str, ...] | None = None, *, repo: Path | None = None) -> bool:
    if patterns is None:
        if repo is None:
            raise ValueError("repo required when patterns is None")
        patterns = load_patterns(repo)
    rel = _normalize_rel(rel)
    return any(_match_pattern(rel, p) for p in patterns)


def forbidden_commit_reason(rel: str) -> str | None:
    """Return alarm reason when a path must not be in a commit (aligned with ``.gitignore``)."""
    rel = _normalize_rel(rel)
    name = Path(rel).name

    for prefix in FORBIDDEN_COMMIT_PREFIXES:
        bare = prefix.rstrip("/")
        if rel == bare or rel.startswith(prefix):
            return f"forbidden local-only path must not be committed ({prefix})"

    if name in FORBIDDEN_BASENAMES:
        return f"forbidden sensitive file must not be committed ({name})"

    lower = name.lower()
    for suffix in FORBIDDEN_SUFFIXES:
        if lower.endswith(suffix):
            return f"forbidden sensitive file must not be committed (*{suffix})"

    if fnmatch.fnmatch(name, ".env.*.local"):
        return "forbidden local environment file (.env.*.local)"

    if rel.endswith(".local.yaml") and not rel.endswith(".local.yaml.example"):
        return "forbidden local config override (*.local.yaml)"

    if "/private/secrets/" in rel and rel.endswith(".json") and not rel.endswith(".example.json"):
        return "forbidden secrets JSON (use *.example.json templates only)"

    return None


def is_forbidden_in_commit(rel: str) -> bool:
    return forbidden_commit_reason(rel) is not None


def collect_forbidden_paths(rels: list[str]) -> list[tuple[str, str]]:
    return [(p, r) for p in rels if (r := forbidden_commit_reason(p))]


def alarm_commit_paths(rels: list[str]) -> None:
    """Fail fast if any path that would land in a commit is forbidden."""
    blocked = collect_forbidden_paths(rels)
    if not blocked:
        return
    print(
        "ERROR: forbidden paths must not be committed "
        "(vault, venv, .env, credentials — remove from index; keep in .gitignore):\n",
        file=sys.stderr,
    )
    for path, reason in blocked:
        print(f"  {path}: {reason}", file=sys.stderr)
    sys.exit(1)


def should_skip_audit_path(
    rel: str,
    patterns: tuple[str, ...],
    *,
    observe_piiignore: bool,
) -> bool:
    """Skip content scan only when ``--observe-piiignore`` and path matches ``.piiignore``.

    Forbidden commit paths are never skipped — they must alarm via ``alarm_commit_paths``.
    """
    if is_forbidden_in_commit(rel):
        return False
    if not observe_piiignore:
        return False
    return is_ignored(rel, patterns)


def local_sensitive_warnings(
    repo: Path,
    patterns: tuple[str, ...],
    *,
    observe_piiignore: bool,
) -> list[str]:
    """Warn about gitignored local trees on disk (``--all`` only, not commit content)."""
    warnings: list[str] = []
    for rel_dir in LOCAL_SENSITIVE_DIRS:
        full = repo / rel_dir
        if not full.exists():
            continue
        if observe_piiignore and (
            is_ignored(rel_dir, patterns) or is_ignored(f"{rel_dir}/", patterns)
        ):
            continue
        if full.is_dir():
            try:
                n_files = sum(1 for p in full.rglob("*") if p.is_file())
            except OSError:
                n_files = -1
            warnings.append(
                f"{rel_dir}/ exists on disk ({n_files} files) — gitignored, must not be committed"
            )
        else:
            warnings.append(f"{rel_dir} exists on disk — gitignored, must not be committed")
    return warnings


def format_local_warnings(warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = [
        "WARNING: local-only sensitive trees present (not part of the commit):",
        *(f"  {w}" for w in warnings),
        "",
        "Do not stage these paths. To silence: add to .piiignore and pass --observe-piiignore.",
    ]
    return "\n".join(lines)
