#!/bin/sh
# Point this clone at .githooks (run once per clone).
set -e
cd "$(dirname "$0")/.."
chmod +x .githooks/prepare-commit-msg .githooks/commit-msg .githooks/pre-commit .githooks/scan-secrets-pii.sh .githooks/install.sh
chmod +x scripts/audit_pii.py scripts/audit_secrets.py
git config core.hooksPath .githooks
echo "✓ core.hooksPath → .githooks"
echo "  Pre-commit: check_secrets + Presidio + secrets (see .piiignore / .gitleaksignore)"
