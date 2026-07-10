# Opportunity intake — working agreement

How the Job Researcher handles diverse sources. Mirrors the AI Digest pattern:
**one profile, many adapters, one output contract.**

Architecture: [Career_Intelligence_System.md](../../docs/Career_Intelligence_System.md#opportunity-intake-diverse-sources)

---

## AI Digest Researcher (reference)

| Concept | AI Digest behavior |
|---|---|
| Profile | Single `researcher` — never fork per topic or feed |
| Dispatch | Concierge creates kanban tasks; task body = target + window |
| Sources | Tools pick ingest path: RSS, crawl markdown, structured JSON, web search |
| Output | `researcher_artifact/v1` — Librarian consumes uniform shape |
| User input | Concierge intents (`ADD_TOPIC`, `GO`) — not per-URL chat |

Career Intelligence **drops the Librarian fan-in** (one job → one report) but keeps
the same **adapter + contract** idea.

**Front desk:** Career Zazu does **not** add a separate Concierge profile. The
**Career Knowledge Manager** (`zazu_knowledge_manager`) routes intents and reports
status. AI Digest keeps `ai_news_concierge` — see [RFC: CKM front desk](../../docs/rfc/CKM_front_desk.md).

---

## Career Intelligence Job Researcher

| Concept | Behavior |
|---|---|
| Profile | Single `zazu_researcher` |
| Dispatch | Chat `EVALUATE_OPPORTUNITY`, forwarded email/DM, or discovery task |
| Sources | `source_kind` → intake adapter (see architecture doc); DISCOVER also runs **JobSpy** (`search_jobspy.json`) before researcher web_search |
| Output | `opportunity_artifact/v1` → Recommendation Report |
| KB | Read-only |

---

## Intents (chat — routed by zazu_knowledge_manager)

The **Career Knowledge Manager** is the human-facing entry point. Route these
intents to the correct worker or CLI command. There is **no "GO"** in Career Zazu
(that is AI Digest vocabulary).

| Intent | Action | Example | Pipeline? |
|---|---|---|---|
| `DISCOVER` | Search from KB criteria | “Senior staff eng, Seattle, $300k+” | Yes |
| `EVALUATE_OPPORTUNITY` | One Opportunity → one Recommendation Report | URL + pasted JD + optional recruiter message | Yes |
| `APPLY` | Application package for user-approved role | `manage.py apply [--coach]` | Yes |
| `RECORD_OUTCOME` | Registry + learning trace | `applications record-outcome` | No |
| `ANALYZE` | Topic stats, gaps | `career topics` + RAG | No |
| `STEWARD` | KB scan / health | `kb-scan` | Optional |
| `STATUS` | Board + artifacts | `career status` | No |
| `CONFIGURE` | Goals, topics, cadence | KB proposal → user approves | No |

For bootstrap, message **`zazu_knowledge_manager`** (front desk) or **`zazu_researcher`**
directly with `EVALUATE_OPPORTUNITY` blocks.

**Email intake (required later):** forward recruiter message → CKM routes `EVALUATE`
with `recruiter_message` adapter (same contract). Credentials live in the
[encrypted vault](docs/rfc/secrets_and_email_intake.md) (`manage.py secrets`).

---

## `recruiter_message` intake

Email and DMs are **not** a separate pipeline:

```yaml
source_kind: recruiter_message
source_url: null                    # or link extracted from body
recruiter_message:
  channel: email | linkedin_dm | sms | other
  from: "recruiter@example.com"
  subject: "Role at Acme"
  body: |
    Full message text...
  urls_found: ["https://jobs.lever.co/..."]
provenance:
  - kind: message_body
    at: "2026-07-07T18:00:00Z"
  - kind: fetched
    url: "https://jobs.lever.co/..."
    status: ok
```

Merge extracted JD with fetched page; **never discard** the original message.

---

## Output contract

Schema: [`schemas/opportunity_v1.yaml`](schemas/opportunity_v1.yaml)

Recommendation Report sections are defined in
[Career_Intelligence_System.md](../../docs/Career_Intelligence_System.md).

---

## Tools (planned)

| Tool | Purpose |
|---|---|
| `intake_opportunity` | Parse chat/email block → Opportunity |
| `fetch_job_page` | HTTP fetch + readability extract (allowlisted hosts) |
| `verify_url` | Link alive / redirect check |
| `web_search` | Company validation, news (gap repair) |

Pipeline invariants (provenance stamping, KB write guard) run outside the LLM.
