# Project Career Zazu — application DOCX templates

Tracked scaffold copies of the Zazu templates. Runtime vault copies live at
`agentic/hermes/.kb/templates/` (gitignored).

## Rebuild from vault originals

When `pm-resume.docx` or `cover.docx` change under
`.kb/private/originals/resume-repo/`, regenerate templates:

```bash
python agentic/hermes/scripts/build_zazu_templates.py
```

## Files

| File | Purpose |
|------|---------|
| `manifest.yaml` | Section contract for coach patches and pipeline merge |
| `resume/pm-resume.docx` | Master resume layout |
| `cover/cover.docx` | Cover letter layout |
| `brief/application-brief.docx` | Application Brief (Heading 1/2/3 + Normal) |

## Coach workflow

The `zazu_coach` profile writes `*_patch.md` files with `## SECTION_ID` blocks.
`manage.py apply --coach` merges patches into templates locally.
