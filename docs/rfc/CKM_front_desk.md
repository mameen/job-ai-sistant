# RFC: Career Knowledge Manager as Career front desk

**Status:** Accepted (implementation in progress)  
**Product:** Project Career Zazu  
**Date:** 2026-07-08

## What is an RFC?

**RFC** = *Request for Comments*. A short design doc that proposes how something
should work **before** (or while) code lands. It is not user documentation — it
records decisions, boundaries, and trade-offs so future you (and agents) do not
re-litigate them. This RFC replaces the earlier idea of a separate Career
Concierge profile.

---

## Summary

Expand **`zazu_knowledge_manager` (CKM)** to be the **single human-facing entry
point** for Career Zazu: route user intent, trigger pipelines, report status,
steward the KB, and maintain an **auditable learning trail**. CKM orchestrates
and explains — it does **not** research jobs, evaluate fit, or write application
deliverables.

No fourth “Concierge-only” profile. AI Digest keeps **`ai_news_concierge`**;
Career Zazu uses **CKM**. Same pattern, different names, **no shared dispatch
namespace**.

---

## Problem

Today the user must run `manage.py search`, `apply`, and `kb-scan` manually.
Interests live in static KB markdown. Learning from rejections and outcomes is
not traced. A separate Concierge (as in AI Digest) would duplicate CKM’s
natural “career state” role and create **two Concierge agents** across products.

---

## Decision

| Topic | Decision |
|---|---|
| Front desk | **CKM** (`zazu_knowledge_manager`) — not a new profile |
| Workers | `zazu_researcher` (discover/evaluate), `zazu_coach` (apply package) |
| Digest “GO” | **Not used** in Career — use intent names below |
| Kanban | **One physical board** (`~/.hermes/kanban/`); **logical isolation** by assignee + title prefix |
| Learning | Automatic where safe; KB mutations **proposed** until user approves |
| Traceability | `opportunity_id`, `proposal_run`, `search_run_id`, `learning_event_id` |
| Email intake | **Required later** — same `EVALUATE` intent, `recruiter_message` adapter |

---

## CKM boundaries (non-negotiable)

### CKM does

| Mode | Examples |
|---|---|
| **Route** | Map chat → `DISCOVER`, `EVALUATE`, `APPLY`, `ANALYZE`, `STEWARD`, `STATUS` |
| **Trigger** | Invoke `manage.py` / (optional) kanban tasks for workers |
| **Report** | `career status`, registry stats, learning ledger — **from tools, not guesses** |
| **Steward** | KB scan review, merge proposals after user approval |
| **Explain** | Defend automatic learning with `learning_event_id` + `explanation` |

### CKM does not

- Perform job research or produce Recommendation Reports  
- Write resume, cover, or brief patches  
- Merge KB changes without user approval  
- Judge worker prose quality (deterministic gates do that)  
- Dispatch or interpret **AI Digest** tasks  

---

## User intent map (no “GO” jargon)

| You say | Intent | Pipeline? | Worker / tool | Output |
|---|---|---|---|---|
| “Run a search” / weekly discovery | **DISCOVER** | Yes | `zazu_researcher` via `manage.py search` | `search_latest.md` + summary |
| “Check this job” (link, paste, file) | **EVALUATE** | Yes | `zazu_researcher` (chat `EVALUATE_OPPORTUNITY`) | Recommendation per role |
| “Package / apply to X” | **APPLY** | Yes | `apply` + optional `zazu_coach` | `proposals/<run>/` |
| “I was rejected” / outcome | **RECORD_OUTCOME** | No | `applications record-outcome` + learning event | Registry + trace |
| “Response rate for MCP?” / gaps | **ANALYZE** | No | Registry + RAG + KB (deterministic queries) | Answer, no worker run |
| “Scan KB” / health | **STEWARD** | Optional | `kb-scan` / CKM `SCAN_KB` | Catalog / proposals |
| “What’s running?” | **STATUS** | No | `manage.py career status` | Board + artifacts |

**DISCOVER ≠ APPLY.** Search ends at a candidate list; apply requires explicit user choice.

### Cadence (when stable)

- **Daily:** `DISCOVER` from `career_goals.md` + prefs (cron/launchd → `manage.py search`)  
- **Anytime:** `EVALUATE` one job interrupts or runs beside discovery  
- **On demand:** `APPLY` after approval  

---

## Trace IDs (how learning propagates)

| ID | Example | Links |
|---|---|---|
| `opportunity_id` | `opp:a1b2c3d4e5f67890` | Registry row; dedupe key hash |
| `proposal_run` | `20260708153546` | Coach DOCX folder under `proposals/` |
| `search_run_id` | `search_20260708` or mtime of `search_latest.md` | Discovery batch |
| `learning_event_id` | `le:20260708:abc12345` | Ledger row with explanation |

Every automatic learning row includes:

- `source_type` — e.g. `user_rejection`, `topic_tag`, `search_signal`  
- `source_ref` — parent `opportunity_id` and/or `proposal_run`  
- `target` — e.g. `topic:mcp`, `career_goals#industry`  
- `action` — `proposed` \| `auto_applied` \| `approved` \| `rejected`  
- `explanation` — human-readable **why**  

KB file changes stay `proposed` until you approve. Registry tags and stats may `auto_applied`.

---

## Kanban: one board, two products — no contention

Hermes uses a **single kanban store** at `~/.hermes/kanban/`. You do **not**
need two physical kanbans. Contention is avoided by **self-aware filtering**:

| Product | Task filter | Assignees | Title convention |
|---|---|---|---|
| **AI Digest** | `digest_board_rows()` | `ai_news_*` | `Research:…`, `Librarian:…`, `Synthesize digest` |
| **Career Zazu** | `career_board_rows()` | `zazu_*` | `Career:…` prefix |

Rules:

1. **CKM** only creates/shows `Career:` tasks assigned to `zazu_*`.  
2. **`ai_news_concierge`** only uses `digest_*` admin tools — never Career tasks.  
3. **STATUS** in each product calls **its own** status tool (`digest_board_status` vs `career status`).  
4. Workers (`kanban_worker`) complete only tasks assigned to **their** profile name.  

Repo-local `.runtime/board/` in each project holds **metadata**; Hermes kanban is shared but **logically partitioned**.

---

## Coexistence with AI Digest (self-awareness)

Both products may run on the same machine and share Ollama + Hermes kanban.

| Agent | Knows it is | Must never |
|---|---|---|
| `zazu_knowledge_manager` | Career Zazu front desk | Call `digest_go`, `digest_board_status`, or assign `ai_news_*` |
| `ai_news_concierge` | AI Digest front desk | Call `manage.py search/apply` or assign `zazu_*` |

Cross-reference docs:

- Career: this RFC + [Career_Intelligence_System.md](../Career_Intelligence_System.md)  
- Digest: `ai_news_concierge` SOUL + `tools/orchestration.py`  

---

## Email intake (strong requirement — later)

Phase 1 remains chat paste. Phase 2+ adds **`recruiter_message`** intake:

- User forwards email/DM → CKM routes **EVALUATE**  
- Same `opportunity_artifact/v1` contract (`working_agreements.md`)  
- Provenance: `message_body` + optional fetch  

CKM routes; Researcher executes. No separate email agent.

---

## Implementation checklist

- [x] RFC (this document)  
- [x] CKM SOUL + profile doc update  
- [x] `learning_events` + `application_topics` in SQLite  
- [x] `lib/career/orchestration.py` — `career_board_rows`, `career_status`  
- [x] `manage.py career status|topics|learning`  
- [ ] Hermes plugin tools (`career_status`, …) — optional follow-up  
- [ ] Daily `DISCOVER` launchd plist — after stable search  
- [ ] Email / mailbox adapter — future  

---

## Open questions

1. **Topic vocabulary** — controlled list vs researcher-assigned free tags (v1: free tags, normalized slugs).  
2. **Formal `recommended/`** — per-row reports vs `search_latest.md` summary (v1: latter).  

---

## References

- [zazu_knowledge_manager profile](../profiles/zazu_knowledge_manager.md)  
- [working_agreements.md](../../agentic/hermes/working_agreements.md)  
- [application_registry_v1.yaml](../../agentic/hermes/schemas/application_registry_v1.yaml)  
- [learning_events_v1.yaml](../../agentic/hermes/schemas/learning_events_v1.yaml)  
