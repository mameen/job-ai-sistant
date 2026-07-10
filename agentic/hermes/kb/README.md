# Career KB scaffold

Templates under `scaffold/public/` and `scaffold/private/` are **checked into git**
and copied to **`agentic/hermes/.kb/public/`** and **`agentic/hermes/.kb/private/`**
on bootstrap.

The **`.kb/`** tree is **gitignored** and must never be committed.

```bash
python agentic/hermes/admin/manage.py bootstrap
python agentic/hermes/admin/manage.py kb-scan
```

| Layer | Path | Contents |
|---|---|---|
| Inbox | `agentic/hermes/.kb/inbox/` | Drop zone — any file type |
| Public | `agentic/hermes/.kb/public/` | Resume, skills, projects, STAR stories |
| Private | `agentic/hermes/.kb/private/` | Goals, comp, flags, prompts, history |
| Secrets | `agentic/hermes/.kb/private/secrets/` | Encrypted vault — **never** kb-scanned or RAG-indexed |
| Index | `agentic/hermes/.kb/_index/` | Derived catalog + extracted text |

Agent prompts live at `private/prompts/` (`fake_job.md`, `job_fitness.md`).

Generated outputs (search reports, DOCX) go to **`agentic/hermes/.generated/`** —
see [working_agreements_generated.md](../working_agreements_generated.md).

Legacy repo-root `.kb/` is migrated to `agentic/hermes/.kb/` on bootstrap.
