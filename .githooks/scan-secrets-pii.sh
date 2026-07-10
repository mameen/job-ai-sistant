#!/bin/sh
# Thin wrapper — prefer: python scripts/check_secrets.py …
set -eu
cd "$(dirname "$0")/.."
case "${1:-}" in
    --staged) exec python3 scripts/check_secrets.py --staged ;;
    --all) exec python3 scripts/check_secrets.py --all ;;
    --worktree) exec python3 scripts/check_secrets.py --worktree ;;
    "") exec python3 scripts/check_secrets.py --staged ;;
    *) exec python3 scripts/check_secrets.py "$@" ;;
esac
