# Configuration templates

Project Career Zazu uses a **template + local override** pattern:

| Checked in (safe) | Local (gitignored) | Purpose |
|---|---|---|
| [`.env.example`](../.env.example) | `.env` | Ollama URLs, optional vault passphrase |
| [`hermes_roles.local.yaml.example`](../agentic/hermes/admin/config/hermes_roles.local.yaml.example) | `hermes_roles.local.yaml` | Machine-specific Hermes / Ollama overrides |
| [`kb/scaffold/private/secrets/*.example.json`](../agentic/hermes/kb/scaffold/private/secrets/) | `.kb/private/secrets/vault.json` | Encrypted email/OAuth credentials |
| [`hermes_roles.yaml`](../agentic/hermes/admin/config/hermes_roles.yaml) | — | Shared defaults (committed) |

**Rule:** Never commit filled-in `.env`, `*.local.yaml`, `vault.json`, or `*.json` credential files without the `.example` suffix.

---

## First-time setup

```bash
cp .env.example .env
# edit .env

cp agentic/hermes/admin/config/hermes_roles.local.yaml.example \
   agentic/hermes/admin/config/hermes_roles.local.yaml
# edit only if you need overrides beyond .env

python agentic/hermes/admin/manage.py bootstrap
python agentic/hermes/admin/manage.py setup
```

---

## Environment (`.env`)

`.env` is loaded by `manage.py` before commands run. Variables already set in the shell are **not** overwritten.

| Variable | Required | Notes |
|---|---|---|
| `OLLAMA_TARGET` | No | `local` or `remote` |
| `OLLAMA_BASE_URL` | No | Overrides yaml `base_url` |
| `OLLAMA_MODEL` | No | Chat model name |
| `OLLAMA_EMBED_*` | No | RAG embeddings host/model |
| `CAREER_VAULT_PASSPHRASE` | For `secrets` / `email poll` | Optional in `.env`; can prompt instead |

---

## Hermes roles local override

`hermes_roles.local.yaml` is **deep-merged** over `hermes_roles.yaml` when present. Use it for host-specific Ollama URLs you do not want in `.env`, or rare toolset tweaks.

---

## Secrets vault (email / OAuth)

Templates (placeholders only):

- `oauth_gmail.example.json`
- `oauth_outlook.example.json`
- `imap_yahoo.example.json`

**Do not** copy templates to `*.json` in the scaffold tree and commit them. Either:

1. Edit a template locally and pass to `secrets set --from-json` (file can live outside the repo), or
2. Let bootstrap copy examples into gitignored `.kb/private/secrets/` and edit there.

```bash
export CAREER_VAULT_PASSPHRASE='…'   # or add to .env
python agentic/hermes/admin/manage.py secrets set gmail_oauth \
  --type oauth_gmail \
  --from-json /path/to/your-oauth-bundle.json
```

See [RFC: secrets and email intake](rfc/secrets_and_email_intake.md).

---

## What stays gitignored

Entire local trees (never commit):

- `agentic/hermes/.kb/` — career vault + encrypted secrets
- `agentic/hermes/.generated/` — search reports, DOCX, email intake
- `agentic/hermes/.runtime/` — session / poll state

---

## Security scan allowlists

Pre-commit runs three layers: `check_secrets.py`, Presidio (`audit_pii.py`), and
Betterleaks or detect-secrets (`audit_secrets.py`).

| File | Standard? | Purpose |
|---|---|---|
| [`.piiignore`](../.piiignore) | Project convention (gitignore syntax) | Exempt paths from PII audits |
| [`.ignorepii`](../.ignorepii) | Optional alias | Merged with `.piiignore` |
| [`.gitleaksignore`](../.gitleaksignore) | **Yes** (Gitleaks/Betterleaks) | Secret-scan allowlist |
| [`.secrets.baseline`](../.secrets.baseline) | detect-secrets | Known legacy secret fingerprints |

**Rule:** every `.piiignore` path must also appear in `.gitignore` (except safe
`*.example` templates). `.kb/` is exempt from audits but **blocked** if staged.

```bash
pip install -r requirements-dev.txt
python -m spacy download en_core_web_sm
# optional: brew install betterleaks
./.githooks/install.sh
```

---

## Gitignore reference

Patterns live in [`.gitignore`](../.gitignore). Templates use:

- `*.example` — env and yaml
- `*.example.json` — credential shape samples
