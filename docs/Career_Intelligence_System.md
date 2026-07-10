# Career Intelligence System

> **Mission:** Build a truthful, explainable AI platform that helps
> professionals make better career decisions while maintaining a
> curated, evidence-based career knowledge base.

**Product:** Career Intelligence · **Codename:** Project Career Zazu

------------------------------------------------------------------------

# Architecture

``` mermaid
flowchart LR

    USER((User))

    WEB[(Internet)]

    KB[(Career Knowledge Base)]

    KBM[Career Knowledge Manager]
    JR[Job Researcher]
    AC[Application Coach]

    RR[Recommendation Report]

    RES[Customized Resume]
    CL[Customized Cover Letter]
    AB[Application Brief]

    PROP[KB Update Proposal]

    WEB --> JR
    WEB --> AC

    KB --> JR
    KB --> AC
    KB --> KBM

    JR --> RR
    RR --> USER

    USER -->|Approve Application| AC

    AC --> RES
    AC --> CL
    AC --> AB

    AC --> PROP

    USER -->|Review & Approve| KBM
    PROP --> KBM
    KBM --> KB
```

------------------------------------------------------------------------

# Three profiles (not two)

The platform uses **Profiles** — specialized AI roles, not a single general
assistant. Every profile reads the Career Knowledge Base; only the Career
Knowledge Manager may write to it, and only after explicit user approval.

| # | Profile | Role |
|---|---|---|
| 1 | **Career Knowledge Manager** | **Career front desk** + KB steward — routes intents, explained learning, merges approved KB updates |
| 2 | **Job Researcher** | Opportunity scout & evaluator — discovers jobs, scores fit, produces Recommendation Reports |
| 3 | **Application Coach** | Application prep for user-approved roles — resume, cover letter, Application Brief |

| Phase | Profile | Question it answers |
|---|---|---|
| Front desk | Career Knowledge Manager | *What should run next? Why did preferences change?* |
| Stewardship | Career Knowledge Manager | *Is our career knowledge accurate, complete, and consistent?* |
| Discovery | Job Researcher | *Should I pursue this opportunity?* |
| Execution | Application Coach | *How do I maximize my chances for this approved role?* |

**No separate Concierge profile.** CKM absorbs front-desk routing; AI Digest keeps
`ai_news_concierge`. Design: [rfc/CKM_front_desk.md](rfc/CKM_front_desk.md).

------------------------------------------------------------------------

# Profiles

## 1. Career Knowledge Manager

### Mission

Maintain the integrity, quality, and long-term evolution of the Career
Knowledge Base.

Unlike the other profiles, this profile is **not application-centric**.
It is the steward of your professional history.

### Responsibilities

-   Curate the master resume
-   Maintain the career knowledge graph
-   Maintain the STAR story library
-   Organize projects and accomplishments
-   **Scan and index** the KB vault (PDF, DOCX, images, markdown) on demand or on a schedule
-   **Classify** documents and propose folder moves when files land in the wrong place
-   Detect duplicates and inconsistencies
-   Validate proposed KB updates
-   Merge approved changes
-   Produce periodic Career Knowledge Health Reports

### KB vault vs derived index

| Layer | Path | Notes |
|---|---|---|
| Vault | `.kb/inbox/`, `.kb/public/`, `.kb/private/` | Any file type — drop without sorting |
| Index | `.kb/_index/catalog.json` | Scan-built; extracted text under `_index/extracted/` |

```bash
python agentic/hermes/admin/manage.py kb-scan
python agentic/hermes/admin/manage.py kb-scan --agent   # zazu_knowledge_manager review
```

Relocation proposals live in `.kb/_index/relocation_proposals.json`. The KB Manager
**never moves files without user approval**.

Detail: `agentic/hermes/working_agreements_kb.md`

### Reads

-   Career Knowledge Base (vault + derived index)

### Internet Access

Limited to validation only:

-   Certification verification
-   Publication metadata
-   Conference information
-   Patent information
-   Company renames or acquisitions
-   Public profile validation

### Writes

Only after explicit user approval.

------------------------------------------------------------------------

## 2. Job Researcher

### Mission

Discover opportunities worth pursuing.

### Reads

-   Career Knowledge Base (read-only)

### Internet Access

Primary internet-facing profile.

Researches:

-   LinkedIn
-   Greenhouse
-   Lever
-   Company career sites
-   Recruiters
-   Glassdoor
-   Blind
-   Crunchbase
-   Company news
-   Financial information
-   Engineering blogs
-   Press releases

### Produces

## Recommendation Report

Sections:

1.  Executive Summary
2.  Recommendation (Apply / Consider / Skip)
3.  Job Summary
4.  Company Snapshot
5.  Authenticity Validation
6.  Why This Fits
7.  Why This Doesn't
8.  Top 3 Matching Skills
9.  Top Missing Skills
10. Career Growth Potential
11. Red Flags
12. Yellow Flags
13. Compensation Estimate
14. Recommended Next Steps

The Job Researcher **never modifies** the Career Knowledge Base.

------------------------------------------------------------------------

# Opportunity intake (diverse sources)

The Job Researcher does **not** use a different workflow per job board. Every
source — LinkedIn, Indeed, ZipRecruiter, company ATS pages, chat paste, email,
or recruiter DM — becomes the same canonical **Opportunity**, then the same
**Recommendation Report** pipeline.

## Pattern (borrowed from AI Digest)

In [AI Digest](https://github.com/mameen/AI_Digest), the Researcher works the
same way:

| AI Digest | Career Intelligence |
|---|---|
| One `researcher` **profile** | One `zazu_researcher` **profile** |
| Task body names the **target** (topic / feed) | Task body names the **opportunity** or search criteria |
| Ingest tools vary by source (RSS, crawl, JSON API) | **Intake adapters** vary by `source_kind` |
| Uniform output: `researcher_artifact/v1` | Uniform output: `opportunity_artifact/v1` → Recommendation Report |
| Concierge routes `GO` / topic intents | **CKM** routes `DISCOVER` / `EVALUATE` (user chat; email later) |
| Librarian merges many researchers | *(none)* — one opportunity → one report |

**Rule:** change the **task description** and **adapter**, not the profile.

## Source kinds

| `source_kind` | Examples | Intake |
|---|---|---|
| `user_direct` | Chat: URL + pasted JD | User text is evidence; fetch URL when allowed |
| `recruiter_message` | Email, LinkedIn DM, SMS forward | Parse subject/body; extract links; keep raw message |
| `aggregator` | Indeed, ZipRecruiter, Glassdoor | Listing page → resolve apply URL when possible |
| `social` | LinkedIn job post | Often login-walled — fall back to user paste |
| `ats` | Greenhouse, Lever, Ashby | Structured job pages |
| `company_site` | `careers.*` | Direct employer posting |
| `discovery` | Researcher-initiated search | Criteria from Career KB (role, location, comp) |

Registered boards (LinkedIn, Indeed, ZipRecruiter, …) are **hosts** mapped to a
`source_kind` — not separate agents.

## Two intake modes

### 1. User-directed (highest priority for v1)

You send the Researcher a message — Hermes chat, email forward, or DM paste:

```text
EVALUATE_OPPORTUNITY
url: https://www.ziprecruiter.com/...
description: |
  <pasted job description>
message: |
  <optional recruiter email or DM text>
```

The adapter merges: fetched page + pasted JD + message body. **Provenance**
records what was user-supplied vs fetched.

### 2. Proactive discovery

Standing criteria from the Career KB drive search across enabled sources.
Results dedupe by company + title + apply URL. Each hit becomes an Opportunity
and gets its own Recommendation Report.

## Canonical Opportunity (before fit analysis)

See `agentic/hermes/schemas/opportunity_v1.yaml` in the repo. Every adapter
emits this shape:

| Field | Purpose |
|---|---|
| `opportunity_id` | Stable id (hash of apply URL or submission) |
| `source_kind` | From table above |
| `source_url` | Where you found it |
| `apply_url` | Where you would apply |
| `title`, `company`, `location` | Structured basics |
| `job_description` | Full text for fit analysis |
| `provenance` | `fetched` / `user_pasted` / `message_body` / hybrid |
| `recruiter_message` | Optional raw email or DM (for `recruiter_message`) |

Fit analysis, authenticity checks, and Recommendation Report sections are
**identical** regardless of `source_kind`.

## Email and direct messages

Treat email and recruiter DMs as **`recruiter_message`** (a variant of user-directed intake):

1. User forwards or pastes the message into chat (or future mailbox integration).
2. Adapter extracts: sender, subject, body, embedded URLs, attachments (JD PDF later).
3. If a URL is present, fetch when accessible; **message body remains evidence**.
4. Flag authenticity: unknown sender, vague role, “apply on WhatsApp” red flags.
5. Emit Opportunity → standard Recommendation Report.

No separate “email agent” — same `zazu_researcher`, same contract.

## Phased implementation

| Phase | Scope |
|---|---|
| **1** | `user_direct` + `recruiter_message` via chat; ATS + company pages |
| **2** | Aggregators (Indeed, ZipRecruiter) where fetch works; paste fallback |
| **3** | Discovery search; harder sources (LinkedIn) with paste-first policy |

------------------------------------------------------------------------

## 3. Application Coach

### Mission

Maximize the probability of success for approved opportunities.

### Reads

-   Career Knowledge Base
-   Recommendation Report

### Internet Access

Targeted deep research:

-   Engineering blogs
-   Annual reports
-   Investor reports
-   Executive interviews
-   Hiring manager profiles
-   Interview experiences
-   Technical talks
-   Product launches
-   Earnings calls

### Responsibilities

-   Tailor resume
-   Tailor cover letter
-   Perform deep company research
-   Prepare interview strategy
-   Select relevant STAR stories
-   Analyze historical application patterns
-   Propose KB improvements

------------------------------------------------------------------------

# Produced Artifacts

## Customized Resume

-   Tailored summary
-   Selected accomplishments
-   Relevant leadership examples
-   Optimized ATS keywords
-   Truthful metrics and outcomes
-   Technologies aligned to the role

------------------------------------------------------------------------

## Customized Cover Letter

-   Personalized introduction
-   Why this company
-   Why this role
-   Relevant experiences
-   Leadership narrative
-   Closing

------------------------------------------------------------------------

## Application Brief

### Opportunity Intelligence

-   Job overview
-   Organization
-   Team
-   Hiring manager (if available)

### Company Intelligence

-   Mission
-   Products
-   Strategy
-   Financial health
-   Culture
-   Competitors
-   Recent news

### Interview Intelligence

-   Hiring process
-   Expected interview stages
-   Technical focus
-   Behavioral themes
-   Leadership principles

### Candidate Strategy

-   Strongest matching experiences
-   Potential weaknesses
-   Recommended STAR stories
-   Talking points
-   Questions for recruiter
-   Questions for hiring manager

### Compensation

-   Estimated range
-   Equity considerations
-   Negotiation notes

### Preparation Checklist

-   Resume review
-   Cover letter review
-   STAR practice
-   Technical preparation
-   Company research

------------------------------------------------------------------------

# Career Knowledge Base Lifecycle

``` mermaid
sequenceDiagram

    participant User
    participant Researcher
    participant Coach
    participant KBManager
    participant KB

    KB->>Researcher: Read
    Researcher->>User: Recommendation Report

    User->>Coach: Approve Application

    KB->>Coach: Read Knowledge

    Coach->>User: Resume
    Coach->>User: Cover Letter
    Coach->>User: Application Brief

    Coach->>KBManager: Proposed Updates

    User->>KBManager: Approve

    KBManager->>KB: Merge Changes
```

------------------------------------------------------------------------

# Core Design Principles

1.  The Career Knowledge Base is the single source of truth.
2.  Every profile can read the KB.
3.  Only the Career Knowledge Manager can modify the KB.
4.  Every KB modification requires explicit user approval.
5.  Recommendations must always be explainable.
6.  Resume customization must remain truthful.
7.  Observations must be evidence-backed.
8.  AI assists; the user always decides.
