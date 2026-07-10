# Agent Code Guide — Project Career Zazu

Working notes for agents (and humans) on **Career Intelligence**. Keep changes
conservative and aligned with human-in-the-loop principles.

> **Single entry point.** This file lives at `.agents/AGENTS.md`; repo-root `AGENTS.md`
> is a symlink. **Product narrative:** [`README.md`](../README.md) — if anything
> conflicts, README wins.

## Principles

1. **Human in control.** KB writes and applications require explicit user approval.
2. **Truthful by design.** No fabricated employers, titles, or metrics in outputs.
3. **Evidence-backed.** Recommendations cite KB or fetched sources; mark uncertainty.
4. **Disciplined workflow.** Describe → test → commit on a branch. Never push without
   explicit maintainer permission.
5. **Vault privacy.** Career documents live in gitignored `.kb/` — treat as sensitive PII.

Full product spec: [`docs/Career_Intelligence_System.md`](../docs/Career_Intelligence_System.md).

## Onboarding docs

| I want to… | Read |
|---|---|
| Hermes profile: repo, env, PII, imports | `.agents/onboarding/hermes-and-repo.md` |
| Profiles, tools, artifacts | [`docs/profiles/README.md`](../docs/profiles/README.md) |
| KB layout and extraction | [`agentic/hermes/kb/README.md`](../agentic/hermes/kb/README.md) |
| Machine setup | [`SETUP.md`](../SETUP.md) |
| Configuration / Ollama | [`docs/configuration.md`](../docs/configuration.md) |

## Hermes profiles & agent repo rules

**All `zazu_*` profiles** (`zazu_knowledge_manager`, `zazu_researcher`, `zazu_coach`) must
follow [`.agents/onboarding/hermes-and-repo.md`](onboarding/hermes-and-repo.md). Each SOUL
references it; `manage.py setup` copies it to
`~/.hermes/profiles/<role>/REPO_ONBOARDING.md`. On import, env, git, or PII questions,
**`read_file` that doc before guessing.**

| Topic | Rule |
|---|---|
| **Python layout** | Pipeline code under `agentic/hermes/lib/`; `manage.py` adds repo root to `sys.path`. No `digest-tools` overlay (unlike AI Digest). |
| **Redeploy** | After SOUL or `manage.py` changes: `python agentic/hermes/admin/manage.py setup` → `hermes gateway restart`. |
| **Career vault** | `agentic/hermes/.kb/` — **gitignored**, real PII. Never commit, stage, or paste vault content into chat artifacts. |
| **Generated outputs** | `agentic/hermes/.generated/` — gitignored working drafts. |
| **Secrets** | `.env` (never commit), `private/secrets/` templates only in git; real creds in vault paths. |
| **PII / hooks** | Pre-commit: `scripts/check_secrets.py`, `audit_pii.py`, `audit_secrets.py`. Exemptions: `.piiignore`. Install: `./.githooks/install.sh`. |
| **Git (agents)** | No git CLI tools in profiles. Maintainers commit; agents do not push or invent branch workflows. |
| **Scope** | Career Zazu only — not AI Digest / ORIO digest GO. |

## Testing

```bash
python run_tests.py
```

Prefer real fixtures under `tests/`; avoid mocking our own code unless unavoidable.

## Commit / push

- Commit locally with a descriptive message. **Do not push** unless explicitly asked.
- **Never** add `Co-authored-by` automation trailers or third-party co-author lines.
- Never commit `.env`, `.kb/`, `.generated/`, OAuth JSON, or IMAP credentials.
- **Pre-commit** blocks secrets and sensitive PII in staged lines (see `.githooks/README.md`).

## Sister project

**AI Digest** ([`AI_Digest`](https://github.com/mameen/AI_Digest)) shares the same `.agents/`
pattern and Hermes bootstrap style — reference only, not a dependency. Do not dispatch
digest GO or confuse ORIO roles with Zazu profiles.
