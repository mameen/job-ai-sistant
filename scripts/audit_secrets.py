#!/usr/bin/env python3
"""Secret scan: Betterleaks / Gitleaks (preferred) or detect-secrets (pip fallback).

Policy:
- ``--staged``: scan every staged file; alarm on forbidden paths (``.kb/``, ``.venv/``).
- ``--all``: scan all git-tracked files; warn about local gitignored sensitive trees.
- ``.piiignore`` applies only with ``--observe-piiignore`` (opt-in).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
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
    should_skip_audit_path,
)

BASELINE = REPO / ".secrets.baseline"

_SKIP_SECRET_SCAN = frozenset(
    {
        "scripts/check_secrets.py",
        "scripts/audit_secrets.py",
        "scripts/audit_pii.py",
        "scripts/scan_ignore.py",
        ".secrets.baseline",
    }
)


def _fail(msg: str) -> None:
    print(f"✗ secrets audit: {msg}", file=sys.stderr)
    sys.exit(1)


def _staged_paths() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def _tracked_paths() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def _alarm_forbidden(paths: list[str]) -> None:
    alarm_commit_paths(paths)


def _filter_scannable(paths: list[str], *, observe_piiignore: bool) -> list[str]:
    patterns = load_patterns(REPO)
    return [
        p
        for p in paths
        if p not in _SKIP_SECRET_SCAN
        and not should_skip_audit_path(p, patterns, observe_piiignore=observe_piiignore)
    ]


def _existing_files(paths: list[str]) -> list[str]:
    return [p for p in paths if (REPO / p).is_file()]


def _scannable_tracked_paths(*, observe_piiignore: bool) -> list[str]:
    tracked = _tracked_paths()
    _alarm_forbidden(tracked)
    return _existing_files(_filter_scannable(tracked, observe_piiignore=observe_piiignore))


def _staged_scannable_paths(*, observe_piiignore: bool) -> list[str]:
    staged = _staged_paths()
    _alarm_forbidden(staged)
    return _existing_files(_filter_scannable(staged, observe_piiignore=observe_piiignore))


def _print_local_warnings(*, observe_piiignore: bool) -> None:
    patterns = load_patterns(REPO)
    msg = format_local_warnings(
        local_sensitive_warnings(REPO, patterns, observe_piiignore=observe_piiignore)
    )
    if msg:
        print(msg, file=sys.stderr)


def _run_cli_protect(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)
    return proc.returncode


def _gitleaks_cmd(binary: str) -> list[str]:
    cmd = [binary, "protect", "--verbose", "--redact"]
    gignore = REPO / ".gitleaksignore"
    if gignore.is_file():
        cmd.extend(["--gitleaks-ignore-path", str(gignore)])
    config = REPO / ".gitleaks.toml"
    if config.is_file():
        cmd.extend(["--config", str(config)])
    return cmd


def _scan_with_gitleaks_family(
    binary: str,
    *,
    staged_only: bool,
    observe_piiignore: bool,
) -> int:
    if staged_only:
        cmd = _gitleaks_cmd(binary)
        cmd.append("--staged")
        rc = _run_cli_protect(cmd)
        if rc != 0:
            print("ERROR: secret scan failed.", file=sys.stderr)
        return rc

    _print_local_warnings(observe_piiignore=observe_piiignore)
    paths = _scannable_tracked_paths(observe_piiignore=observe_piiignore)
    if not paths:
        return 0
    rc = 0
    for rel in paths:
        source = REPO / rel
        cmd = _gitleaks_cmd(binary)
        cmd.extend(["--source", str(source)])
        if _run_cli_protect(cmd) != 0:
            rc = 1
    if rc != 0:
        print("ERROR: secret scan failed.", file=sys.stderr)
    return rc


def _ensure_detect_secrets() -> None:
    try:
        import detect_secrets  # noqa: F401
    except ImportError:
        _fail(
            "install a secret scanner:\n"
            "  brew install betterleaks   # or gitleaks\n"
            "  pip install -r requirements-dev.txt"
        )


def _write_initial_baseline(paths: list[str]) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "detect_secrets", "scan", *paths],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        _fail(proc.stderr or proc.stdout or "detect-secrets scan failed")
    BASELINE.write_text(proc.stdout, encoding="utf-8")


def _ensure_baseline(*, observe_piiignore: bool) -> None:
    if BASELINE.is_file():
        return
    paths = _scannable_tracked_paths(observe_piiignore=observe_piiignore)
    if not paths:
        _fail("no tracked files to seed .secrets.baseline")
    _write_initial_baseline(paths)


def _scan_with_detect_secrets(*, staged_only: bool, observe_piiignore: bool) -> int:
    _ensure_detect_secrets()
    _ensure_baseline(observe_piiignore=observe_piiignore)

    if staged_only:
        paths = _staged_scannable_paths(observe_piiignore=observe_piiignore)
        if not paths:
            return 0
        hook = shutil.which("detect-secrets-hook")
        if hook:
            return subprocess.run([hook, "--baseline", str(BASELINE), *paths], cwd=REPO).returncode
        proc = subprocess.run(
            [sys.executable, "-m", "detect_secrets", "scan", "--baseline", str(BASELINE), *paths],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout or proc.stderr, file=sys.stderr)
        return proc.returncode

    _print_local_warnings(observe_piiignore=observe_piiignore)
    paths = _scannable_tracked_paths(observe_piiignore=observe_piiignore)
    if not paths:
        return 0
    proc = subprocess.run(
        [sys.executable, "-m", "detect_secrets", "scan", "--baseline", str(BASELINE), *paths],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout or proc.stderr, file=sys.stderr)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Secret audit (Betterleaks / detect-secrets).")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--observe-piiignore",
        action="store_true",
        help="opt-in: honor .piiignore exemptions (default: scan commit content fully)",
    )
    args = parser.parse_args(argv)
    staged_only = args.staged or not args.all

    for binary in ("betterleaks", "gitleaks"):
        if shutil.which(binary):
            return _scan_with_gitleaks_family(
                binary,
                staged_only=staged_only,
                observe_piiignore=args.observe_piiignore,
            )

    return _scan_with_detect_secrets(
        staged_only=staged_only,
        observe_piiignore=args.observe_piiignore,
    )


if __name__ == "__main__":
    raise SystemExit(main())
