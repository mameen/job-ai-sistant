# Agent configuration — Project Career Zazu

> **Canonical narrative:** [`README.md`](../README.md) at the repo root. If anything
> here conflicts with README, **README wins**.

This directory is the **source of truth** for contributor and Hermes-agent onboarding
on **Career Intelligence** (Project Career Zazu). Committed to Git; read by humans and
automation.

## Layout

```
.agents/
├── README.md                       # This file
├── AGENTS.md                       # Day-to-day agent rulebook
└── onboarding/
    └── hermes-and-repo.md          # Hermes profiles: repo, env, PII, git boundaries
```

## Repo-root symlink

| Link | Target |
|---|---|
| `AGENTS.md` | `.agents/AGENTS.md` |

Edit files under `.agents/`; the root symlink follows automatically.

## Reading order

1. [`README.md`](../README.md) — product story and getting started
2. [`SETUP.md`](../SETUP.md) — machine checklist
3. `AGENTS.md` — rules before coding or dispatching agents
4. `onboarding/hermes-and-repo.md` — **required for `zazu_*` Hermes profiles**

## Maintenance

- Update onboarding when Hermes wiring, hooks, KB paths, or role boundaries change.
- No secrets, credentials, or career vault content in these docs.
- `.kb/` and `.generated/` are gitignored — never paste real PII from them into committed files.
