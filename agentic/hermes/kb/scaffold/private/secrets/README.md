# Secrets vault (local only)

This directory holds **encrypted credentials** for email intake and optional
aggregator proxies. It is **never** scanned by `kb-scan`, `kb-extract`, or RAG.

## Setup

```bash
export CAREER_VAULT_PASSPHRASE='your-strong-passphrase'   # or enter at prompt

python agentic/hermes/admin/manage.py secrets unlock
python agentic/hermes/admin/manage.py secrets set gmail_oauth \
  --type oauth_gmail \
  --from-json /path/to/oauth-bundle.json
python agentic/hermes/admin/manage.py secrets list
```

`vault.json` is created on first `secrets set`. Do not edit it by hand.

**Templates** (`*.example.json` in this scaffold folder) are safe to commit.
Copy values via `secrets set --from-json` using a file **outside the repo**, or edit
copies under gitignored `agentic/hermes/.kb/private/secrets/`. Never commit real
`*.json` credential files (only `*.example.json`).

## What to store

| Entry type | Example key | Notes |
|---|---|---|
| `oauth_gmail` | `gmail_oauth` | Gmail API — preferred over password |
| `oauth_outlook` | `outlook_oauth` | Microsoft Graph |
| `imap_app_password` | `yahoo_imap` | Yahoo / generic IMAP |
| `linkedin_session` | `linkedin_session` | Cookies only — optional, high maintenance |
| `proxy_list` | `jobspy_proxies` | Optional JobSpy proxies |

**Email poll** (after storing credentials):

```bash
pip install -r requirements-email.txt
python agentic/hermes/admin/manage.py email poll --vault-key gmail_oauth
```


Design: [docs/rfc/secrets_and_email_intake.md](../../../../docs/rfc/secrets_and_email_intake.md)
