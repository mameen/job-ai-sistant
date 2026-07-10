# Machine setup — Career Intelligence

Reproduce the dev environment on a new laptop or VM.

## Prerequisites (system)

| Tool | Purpose | Install |
|---|---|---|
| **Python 3.11+** | Pipeline + `manage.py` | `python3 --version` |
| **Hermes CLI** | Agent profiles | [hermes-agent](https://hermes-agent.nousresearch.com/) |
| **Ollama** | Local / remote LLM + embeddings | [ollama.com](https://ollama.com) |
| **Git** | Clone repo | system package |

Optional (KB deep extract — images / scanned PDFs):

| Tool | macOS | Linux |
|---|---|---|
| **Tesseract OCR** | `brew install tesseract` | `apt install tesseract-ocr` |

## 1. Clone and enter repo

```bash
git clone <your-remote> job-ai-sistant
cd job-ai-sistant
```

## 2. Python virtualenv + dependencies

**Standard** (KB scan, RAG, DOCX — enough for most workflows):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

**Full KB extract** (adds unstructured + OCR for images/scanned PDFs):

```bash
pip install -r requirements-kb-extract.txt
```

Or let bootstrap install deps:

```bash
python agentic/hermes/admin/manage.py bootstrap              # requirements.txt
python agentic/hermes/admin/manage.py bootstrap --extract-kb # + requirements-kb-extract.txt
python agentic/hermes/admin/manage.py install-deps --kb-extract  # venv already exists
```

## 3. Environment and local config

**Templates are committed; real files are gitignored.** See [docs/configuration.md](docs/configuration.md).

```bash
cp .env.example .env
cp agentic/hermes/admin/config/hermes_roles.local.yaml.example \
   agentic/hermes/admin/config/hermes_roles.local.yaml
# Edit .env (and local yaml only if you need overrides beyond .env)
```

Typical split: **chat** on remote GPU, **embeddings** on laptop (`OLLAMA_EMBED_BASE_URL=http://localhost:11434/v1`).

```bash
ollama pull nomic-embed-text    # for KB RAG index
ollama pull qwen3.6:35b         # or your chat model
```

## 4. Bootstrap Hermes + Career KB

```bash
python agentic/hermes/admin/manage.py bootstrap
python agentic/hermes/admin/manage.py setup
python agentic/hermes/admin/manage.py status
```

Copy personal documents into `agentic/hermes/.kb/` (gitignored), then:

```bash
python agentic/hermes/admin/manage.py kb-extract --force-organize
```

## 5. Verify

```bash
python run_tests.py
```

**Job search** (recency window, not hit count — default last 10 days):

```bash
# default: last 10 days; JobSpy pre-fetch (linkedin, indeed, google) runs before researcher
python agentic/hermes/admin/manage.py search -q "Software Engineering Manager AI ML"

# LinkedIn only via JobSpy
python agentic/hermes/admin/manage.py search -q "Software Engineering Manager" --jobspy-sites linkedin --location "United States"

# wider window
python agentic/hermes/admin/manage.py search -q "Software Engineering Manager" --posted-within-days 14

# tighter (e.g. only this week)
python agentic/hermes/admin/manage.py search -q "Software Engineering Manager" --posted-within-days 7
```

## Dependency files

| File | Contents |
|---|---|
| `requirements.txt` | Core — always install |
| `requirements-kb-extract.txt` | Includes base + unstructured + OCR |
| `requirements-dev.txt` | Full stack for dev/CI |

## What stays local (never commit)

- `.env` — Ollama URLs
- `agentic/hermes/.kb/` — Career vault + `index_db/`
- `agentic/hermes/.generated/` — reports and DOCX
- `agentic/hermes/.runtime/` — Hermes session state

## Git hooks — maintainer-only commits

Cursor and Claude Code append `Co-authored-by` trailers that pollute GitHub’s
contributor graph. After clone, run once:

```bash
./.githooks/install.sh
```

See `.githooks/README.md` for details.

## Secrets vault (email / OAuth — optional)

Encrypted credentials live under `agentic/hermes/.kb/private/secrets/` (never kb-scanned).

```bash
export CAREER_VAULT_PASSPHRASE='your-strong-passphrase'
python agentic/hermes/admin/manage.py secrets unlock
python agentic/hermes/admin/manage.py secrets list
```

Design: [docs/rfc/secrets_and_email_intake.md](docs/rfc/secrets_and_email_intake.md)

## Email poll (recruiter intake)

```bash
pip install -r requirements-email.txt   # or: manage.py install-deps --email

python agentic/hermes/admin/manage.py email poll --vault-key gmail_oauth
python agentic/hermes/admin/manage.py email poll --vault-key yahoo_imap --job-filter
```

Output: `agentic/hermes/.generated/intake/email_poll_latest.json`
