# Agentic Hermes — Project Career Zazu bootstrap

Python bootstrap for [Hermes Agent](https://hermes-agent.nousresearch.com/) role
profiles. Pattern inspired by
[AI Digest `agentic/hermes/`](https://github.com/mameen/AI_Digest/tree/main/agentic/hermes).

**New machine?** Start with [SETUP.md](../../SETUP.md) (venv, pip deps, Ollama, KB extract).

## Quick start

```bash
cp .env.example .env          # set OLLAMA_TARGET=remote for LAN GPU host
python agentic/hermes/admin/manage.py bootstrap [--extract-kb]
python agentic/hermes/admin/manage.py setup
python agentic/hermes/admin/manage.py status
python agentic/hermes/admin/manage.py hermes dashboard
```

### Python dependencies

| File | When |
|---|---|
| `requirements.txt` | Always — YAML, pypdf, python-docx, chromadb, docxtpl |
| `requirements-kb-extract.txt` | Images / scanned PDFs — unstructured + pytesseract |
| `requirements-dev.txt` | Dev/CI — full stack |

```bash
python agentic/hermes/admin/manage.py install-deps [--kb-extract]
```

### Ollama: laptop vs remote 4090

Same as AI Digest — point Hermes at the LAN host:

| | Laptop | Remote (faster dev) |
|---|---|---|
| **`.env`** | `OLLAMA_TARGET=local` | `OLLAMA_TARGET=remote` |
| **Or edit yaml** | `localhost:11434` | `192.168.0.100:11434` |
| **Then** | `python agentic/hermes/admin/manage.py setup` | same |

`.env` is gitignored. See [`.env.example`](../../.env.example) and
[`admin/config/hermes_roles.yaml`](admin/config/hermes_roles.yaml).

Select **`zazu_researcher`** and send:

```text
EVALUATE_OPPORTUNITY
url: https://jobs.lever.co/example/...
description: |
  <paste job description>
message: |
  <optional recruiter email or DM>
```

## Concepts

| Term | What it is |
|---|---|
| **Profile** | `zazu_knowledge_manager`, `zazu_researcher`, `zazu_coach` — each with SOUL.md + toolsets |
| **Opportunity** | Normalized job intake (`schemas/opportunity_v1.yaml`) — same shape for every source |
| **source_kind** | `user_direct`, `recruiter_message`, `aggregator`, `ats`, … — picks intake adapter |

## Admin commands

```bash
python agentic/hermes/admin/manage.py bootstrap [--extract-kb] [--skip-setup] [--remote]
python agentic/hermes/admin/manage.py install-deps [--kb-extract]
python agentic/hermes/admin/manage.py setup [--dry-run] [--remote]
python agentic/hermes/admin/manage.py kb-extract [--force-organize]
# Job search — recency window (default 10 days), not hit count:
python agentic/hermes/admin/manage.py search -q "Software Engineering Manager"
python agentic/hermes/admin/manage.py search -q "Software Engineering Manager" --posted-within-days 14
python agentic/hermes/admin/manage.py search -q "Software Engineering Manager" --posted-within-days 7
python agentic/hermes/admin/manage.py status
python agentic/hermes/admin/manage.py nuke --yes
python agentic/hermes/admin/manage.py hermes profile list
```

## Docs

| Doc | Purpose |
|---|---|
| [working_agreements.md](working_agreements.md) | Intake modes, AI Digest comparison, chat intents |
| [schemas/opportunity_v1.yaml](schemas/opportunity_v1.yaml) | Opportunity contract |
| [admin/config/hermes_roles.yaml](admin/config/hermes_roles.yaml) | Profiles + Ollama |
| [../docs/Career_Intelligence_System.md](../docs/Career_Intelligence_System.md) | Full architecture |

## AI Digest Researcher (reference)

AI Digest uses **one researcher profile** per run; only the **task target**
changes. Ingest tools (RSS, crawl, structured JSON) vary by source; output is
always `researcher_artifact/v1`. Career Intelligence maps that to **one
zazu_researcher** and **`opportunity_artifact/v1`** — including chat paste,
email, and ZipRecruiter — with no Librarian merge step.
