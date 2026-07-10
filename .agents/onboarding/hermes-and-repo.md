# Hermes profiles & repo onboarding (Project Career Zazu)

> **Audience:** `zazu_knowledge_manager`, `zazu_researcher`, `zazu_coach`.
> **Maintainers:** update when import wiring, hooks, env, or role boundaries change.
> **Human rulebook:** [`.agents/AGENTS.md`](../AGENTS.md) · **Bootstrap:** [`agentic/hermes/README.md`](../../agentic/hermes/README.md)

Every Zazu profile should **`read_file` this document** when asked about imports,
environment, git, commits, PII, or “how the repo works” — do not guess from generic
Python packaging rules.

**Paths:** repo root `.agents/onboarding/hermes-and-repo.md` · after `manage.py setup`, a
copy lives at `~/.hermes/profiles/<zazu_*>/REPO_ONBOARDING.md`.

---

## Repo layout (what matters to agents)

| Path | Purpose |
|---|---|
| `agentic/hermes/lib/` | Career pipeline (KB, search, apply, email, generated DOCX) |
| `agentic/hermes/admin/manage.py` | Bootstrap, setup, search, apply, kb-extract |
| `agentic/hermes/.kb/` | Career vault — **gitignored**, real PII |
| `agentic/hermes/.generated/` | Draft research, proposals — **gitignored** |
| `agentic/hermes/.runtime/` | Runtime state — **gitignored** |
| `.agents/` | Agent onboarding (this file) |
| `docs/profiles/` | Role specs per Zazu profile |

Repo root is the `job-ai-sistant` clone (where `SETUP.md` and `.env.example` live).

---

## Imports & Hermes (read before diagnosing errors)

**Unlike AI Digest**, this repo does **not** use a `digest-tools` plugin or `tools.*`
overlay. CLI code lives under `agentic/hermes/lib/` and is imported when
`manage.py` runs with the repo on `sys.path`.

**Common mistake:** “missing `__init__.py` / need PYTHONPATH / setup pip-installs lib.”

**Actual mechanism:** run commands via `python agentic/hermes/admin/manage.py …` from
the repo root (or venv with deps installed via `bootstrap`). Hermes chat profiles use
Hermes toolsets (`file`, `web`, `kanban_worker`, …) — not a separate pip package for `lib/`.

**After changing** SOULs or `hermes_roles.yaml`:

```bash
python agentic/hermes/admin/manage.py setup
hermes gateway restart
```

Re-open the dashboard tab if it was already open.

---

## Environment & requirements

| Step | Command | When |
|---|---|---|
| Venv + deps | `python agentic/hermes/admin/manage.py bootstrap [--extract-kb]` | Once per clone |
| Hermes profiles | `python agentic/hermes/admin/manage.py setup` | After SOUL/config changes |
| Gateway | `hermes gateway start` · `hermes gateway restart` | Before chat / after setup |
| Chat UI | `python agentic/hermes/admin/manage.py hermes dashboard` | Interactive use |
| Ollama | From `.env` + `hermes_roles.yaml` | All LLM roles |
| KB index | `python agentic/hermes/admin/manage.py kb-extract` | After vault changes |

See [`SETUP.md`](../../SETUP.md) and [`.env.example`](../../.env.example).

---

## PII, secrets, and commit policy (strict)

This product handles **real career PII**. Pre-commit hooks (`.githooks/`) on staged files:

1. `scripts/check_secrets.py --staged`
2. `scripts/audit_pii.py --staged` (Presidio)
3. `scripts/audit_secrets.py --staged`

| File | Purpose |
|---|---|
| `.piiignore` / `.ignorepii` | Opt-in audit exemptions — pass `--observe-piiignore` to honor |
| `.gitleaksignore` | Secret allowlist |
| `.secrets.baseline` | detect-secrets baseline |

**Default:** commit/staged content is scanned fully; `.piiignore` is **not** applied.
**`--all`:** also **warns** if local `.kb/`, `.venv/`, etc. exist on disk (even when gitignored).
**`--observe-piiignore`:** opt-in to skip paths listed in `.piiignore` during audits.

**Always alarm (never skippable):** anything in a commit (staged or tracked) matching
``.gitignore``-sensitive paths — ``.kb/``, ``.venv/``, ``.env``, credentials, ``vault.json``,
``*.local.yaml``, etc. ``--observe-piiignore`` does **not** exempt these.

**Never commit:** `.env`, OAuth tokens, IMAP passwords, `.kb/` content, `.generated/`
drafts with personal data, absolute home paths in source.

**Agent rule:** do not copy resume text, compensation, or identifiers from the vault into
kanban comments, git-tracked files, or public chat logs. Use role names and artifact paths.

Manual audit: `python scripts/check_secrets.py --all` · `python scripts/audit_pii.py --all`

Install hooks: [`./.githooks/install.sh`](../../.githooks/install.sh) (see [`.githooks/README.md`](../../.githooks/README.md)).

---

## Git — what profiles may assume

| Role | Git access |
|---|---|
| **Zazu profiles** | **No** git CLI. Write artifacts under `.generated/` or kanban workspace only. |
| **Maintainers** | Full git; branch workflow; push only when intended. |

Profiles **do not know** the current branch. “Sync the fix” means: maintainer checks out
the right branch, runs `setup`, restarts gateway.

---

## Role boundaries (quick)

| Profile | Does | Does not |
|---|---|---|
| `zazu_knowledge_manager` | Route intents, KB stewardship, dispatch workers | Job research prose, application DOCX |
| `zazu_researcher` | Discover/evaluate roles, recommendation reports | KB writes, apply packages |
| `zazu_coach` | Resume/cover/brief after user approval | Unapproved applications, KB writes |

Deterministic validation (registry, patch quality) runs in Python — not LLM judgment.

---

## Further reading

| Topic | Doc |
|---|---|
| Day-to-day rules | [`.agents/AGENTS.md`](../AGENTS.md) |
| Product README | [`README.md`](../../README.md) |
| Profile index | [`docs/profiles/README.md`](../../docs/profiles/README.md) |
| Working agreements | [`agentic/hermes/working_agreements.md`](../../agentic/hermes/working_agreements.md) |

When this doc conflicts with **product story**, root `README.md` wins. When it conflicts
with **agent workflow**, `AGENTS.md` wins.
