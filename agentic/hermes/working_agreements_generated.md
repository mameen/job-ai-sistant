# Generated artifacts — working agreement

Where agents write **outputs** (distinct from the Career KB vault and Hermes
session memory).

| Store | Path | Git |
|---|---|---|
| Career KB vault | `agentic/hermes/.kb/` | ignored |
| Generated artifacts | `agentic/hermes/.generated/` | ignored |
| Hermes runtime | `agentic/hermes/.runtime/` | ignored |

User prompts and guardrails live in `agentic/hermes/.kb/private/prompts/`.

---

## Layout

```
agentic/hermes/.generated/
├── researched/          # Job Researcher — discovery & raw evaluation
├── recommended/         # Job Researcher — final Recommendation Reports
└── proposals/
    └── <YYYYMMDDHHmmss>/    # Application Coach — one folder per application run
        ├── <company>_<title>_<job_id>_<date>_resume.docx
        ├── <company>_<title>_<job_id>_<date>_cover.docx
        └── <company>_<title>_<job_id>_<date>_brief.docx
```

### `researched/`

| Artifact | Writer | Example |
|---|---|---|
| Search summary | `zazu_researcher` | `researched/20260707_search_Software_Engineering_Manager.md` |
| Opportunity evaluation draft | `zazu_researcher` | `researched/Tailscale_Engineering_Manager_4700031005_20260707_evaluation.md` |
| Authenticity check | `zazu_researcher` | Uses `private/prompts/fake_job.md` protocol |

### `recommended/`

Final **Recommendation Reports** (Apply / Consider / Skip) — one file per opportunity:

```
<company>_<job_title>_<job_id>_<job_date>_recommendation.md
```

Only roles that pass red/yellow screening should land here.

### `proposals/<run>/`

**Application Coach** output after user approves a role. Exactly three DOCX files
per application (see `private/prompts/job_fitness.md`):

| kind | File |
|---|---|
| `resume` | Tailored 2-page resume |
| `cover` | One-page cover letter |
| `brief` | Application Brief (strategy, STAR picks, talking points) |

**Naming (required):**

```
<company>_<job_title>_<job_id>_<job_date>_<kind>.docx
```

Implemented in `lib/generated/naming.py` — agents must use this convention.

---

## Agent read order

| Profile | Read first | Write to |
|---|---|---|
| `zazu_knowledge_manager` | `.kb/`, `.kb/_index/` | `.kb/` (after approval) |
| `zazu_researcher` | `.kb/`, `private/prompts/`, prior `recommended/` | `researched/`, `recommended/` |
| `zazu_coach` | `.kb/`, `recommended/<report>.md`, `job_fitness.md` | `proposals/<run>/` |

---

## DOCX generation (Application Coach)

Free libraries (in `requirements.txt`):

| Library | License | Use |
|---|---|---|
| [python-docx](https://python-docx.readthedocs.io/) | MIT | Create DOCX; edit paragraphs/styles; clone template + fill body |
| [docxtpl](https://docxtpl.readthedocs.io/) | LGPL-2.1 | Jinja2 merge into `pm-resume.docx` / `cover.docx` (preserves layout) |

Code: `agentic/hermes/lib/generated/docx_io.py`

Templates (Career KB vault):

```
.kb/private/originals/resume-repo/pm-resume.docx
.kb/private/originals/resume-repo/cover.docx
```

`write_application_triplet()` writes all three files into `proposals/<run>/` using
`artifact_filename()` naming.

---

## Lifecycle

1. **Discovery** → `researched/search_*.md`
2. **Evaluate** → `researched/*_evaluation.md` → `recommended/*_recommendation.md`
3. **User approves** → Application Coach → `proposals/<datetime>/` (3 DOCX)
4. **Optional:** copy finished DOCX to OneDrive Applications mirror (manual or script)

`.generated/` is safe to prune older runs; the Career KB vault is never deleted by cleanup.
