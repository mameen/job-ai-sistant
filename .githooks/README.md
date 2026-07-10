# Git hooks — maintainer-only commit attribution + security scans

## Install (once per clone)

```bash
pip install -r requirements-dev.txt
python -m spacy download en_core_web_sm
# optional: brew install betterleaks
./.githooks/install.sh
```

## Pre-commit (three layers)

1. **`check_secrets.py --staged`** — fast blocked paths (`.env`, `.kb/`, `vault.json`), tokens, home paths
2. **`audit_pii.py --staged`** — Microsoft Presidio PII/PHI on staged text
3. **`audit_secrets.py --staged`** — Betterleaks/Gitleaks, or detect-secrets fallback

## Ignore files (standard names)

| File | Used by | Purpose |
|---|---|---|
| **`.piiignore`** | Presidio, detect-secrets paths, full-tree audits | PII audit exemptions (gitignore syntax) |
| **`.ignorepii`** | Same (optional alias) | Merged with `.piiignore` if present |
| **`.gitleaksignore`** | Betterleaks / Gitleaks | Secret-scan exemptions (**industry standard**) |
| **`.secrets.baseline`** | detect-secrets | Known legacy findings (brownfield) |

**Rule:** every `.piiignore` path must also be in `.gitignore` (or be a safe `*.example` template).
`.kb/` is exempt from **audits** but still **blocked** if staged for commit.

## Manual audit

```bash
python scripts/check_secrets.py --all
python scripts/audit_pii.py --all
python scripts/audit_secrets.py --all
```
