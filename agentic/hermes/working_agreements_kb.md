# KB ingestion — working agreement

How the **Career Knowledge Manager** maintains the Career KB when sources are
messy: PDFs, DOCX, images, exports, and markdown in the wrong folder.

Architecture: [Career_Intelligence_System.md](../../docs/Career_Intelligence_System.md)

---

## Two layers

| Layer | Path | Role |
|---|---|---|
| **Source vault** | `.kb/` tree | Your files — any type, any folder (inbox, public, private) |
| **Derived index** | `.kb/_index/` | Scan-built catalog + extracted text — internal DB for agents |

The index is **gitignored** with `.kb/`. Rebuild anytime with `kb-scan`.

---

## AI Digest pattern (reference)

| Concept | AI Digest | Career KB |
|---|---|---|
| Profile | `researcher` + `librarian` | `zazu_knowledge_manager` only writer |
| Adapters | RSS, crawl, JSON per source kind | extractors per file type (md, pdf, docx, …) |
| Contract | `researcher_artifact/v1` | `kb_catalog/v1` + relocation proposals |
| User gate | CKM routes; user approves KB writes | **User approval** before moves or merges |

---

## Intents (zazu_knowledge_manager — front desk + steward)

| Intent | Action |
|---|---|
| `DISCOVER` | Trigger job search (`manage.py search`) |
| `EVALUATE` | Route single opportunity to researcher |
| `APPLY` | Trigger application package after user approval |
| `RECORD_OUTCOME` | Update registry + learning trace |
| `ANALYZE` | Topic response rates, gaps (`career topics`) |
| `STATUS` | `manage.py career status` |
| `CONFIGURE` | Propose KB preference updates (user approves) |
| `SCAN_KB` | On-demand scan review — classify ambiguous docs, refine proposals |
| `KB_HEALTH` | Career Knowledge Health Report from catalog + KB |
| `MERGE_PROPOSAL` | Apply user-approved KB update (from Coach or scan) |

CLI today:

```bash
python agentic/hermes/admin/manage.py kb-scan
python agentic/hermes/admin/manage.py kb-scan --agent
```

Periodic scan: run `kb-scan` on a schedule (cron / launchd) or after dropping files in `inbox/`.

---

## Scan pipeline

1. Walk `.kb/` (skip `_index/`, `index_db/`)
2. Hash each file — detect new / changed / removed
3. Extract text: basic → **unstructured** → **tesseract OCR** (`lib/kb/rich_extract.py`)
4. Classify against `kb/taxonomy.yaml`
5. Write `.kb/_index/catalog.json` + `chunks.jsonl`
6. Embed chunks with **Ollama** → **ChromaDB** at `.kb/index_db/` (vector leg)
7. **BM25** keyword search over the same `chunks.jsonl` (no extra index file)
8. **`query_rag_hybrid()`** — reciprocal rank fusion of BM25 + vector (search preflight)
9. Sync **SQLite** application registry from `application_history/` folders
10. Organize canonical `public/*.md` from best resume extraction

```bash
python agentic/hermes/admin/manage.py bootstrap --extract-kb
python agentic/hermes/admin/manage.py kb-extract [--force-organize] [--skip-rag]
```

Deep-extract deps: `pip install -r requirements-kb-extract.txt` (+ `brew install tesseract` for OCR).

RAG query API: `lib.kb.query_rag()` (vector) · `lib.kb.query_rag_hybrid()` (BM25 + vector).
Search preflight: `lib.kb.build_search_preflight()` — injected into `manage.py search`.

### Application registry (SQLite)

Path: `agentic/hermes/.kb/_index/applications.db` (gitignored with `.kb/`).

Tracks roles applied to, proposal paths, and outcomes — **not** Hermes session memory.
Schema: `schemas/application_registry_v1.yaml`.

```bash
python agentic/hermes/admin/manage.py applications import-vault   # backfill from application_history/
python agentic/hermes/admin/manage.py applications list
python agentic/hermes/admin/manage.py applications record-outcome --company AcmeCorp --status rejected --notes "no response"
```

`manage.py apply` writes a row; `search` injects the registry into the researcher prompt for dedupe.

### Learning ledger + topics

Schema: `schemas/learning_events_v1.yaml` · RFC: `docs/rfc/CKM_front_desk.md`

```bash
python agentic/hermes/admin/manage.py career status
python agentic/hermes/admin/manage.py career topics
python agentic/hermes/admin/manage.py career learning
python agentic/hermes/admin/manage.py applications record-outcome --company X --status rejected --topics mcp --notes "no response"
```

Topic tags power **ANALYZE** intents (“response rate for MCP”). Learning events
record **why** preferences changed, linked to `opportunity_id` / `proposal_run`.

**No automatic moves.** Proposals stay `pending` until you approve; `zazu_knowledge_manager`
executes approved relocations and updates canonical markdown when needed.

---

## File types

| Type | Extract | Classify |
|---|---|---|
| `.md`, `.txt`, … | direct read | keywords + path |
| `.pdf` | `pypdf` (optional dep) | text + filename |
| `.docx` | `python-docx` (optional dep) | text + filename |
| images | metadata only | filename + zazu_knowledge_manager vision/OCR on `SCAN_KB --agent` |
| unknown | skipped | fallback `original_public` / `original_private` |

Install optional extractors:

```bash
pip install pypdf python-docx
```

---

## Schemas

| Schema | Path |
|---|---|
| Catalog | [schemas/kb_catalog_v1.yaml](schemas/kb_catalog_v1.yaml) |
| Taxonomy | [kb/taxonomy.yaml](kb/taxonomy.yaml) |

---

## Other profiles

| Profile | KB access |
|---|---|
| `zazu_researcher` | Read catalog + curated markdown (read-only) |
| `zazu_coach` | Read catalog + curated markdown; proposes updates to `zazu_knowledge_manager` |
| `zazu_knowledge_manager` | Read/write after approval; runs scan review |
