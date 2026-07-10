# Career KB — inbox (drop zone)

**Local only — never commit.** Lives at `.kb/inbox/`.

Drop **any** file here — PDF, DOCX, images, exports, screenshots, recruiter
attachments. You do not need to sort first.

```bash
python agentic/hermes/admin/manage.py kb-scan          # index + classify
python agentic/hermes/admin/manage.py kb-scan --agent  # + zazu_knowledge_manager review
```

The scan builds `.kb/_index/catalog.json` (derived database) and
`relocation_proposals.json` when files belong elsewhere. The **Career Knowledge
Manager** proposes moves; nothing is relocated without your approval.

Canonical curated markdown still lives under `public/` and `private/`; originals
often land in `public/originals/` or `private/originals/` after classification.
