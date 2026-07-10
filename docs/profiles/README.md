# Agent profiles

Three Hermes profiles — specialized roles, not one generic assistant.

| # | Profile | Hermes name | Doc |
|---|---|---|---|
| 1 | **Career Knowledge Manager** | `zazu_knowledge_manager` | [zazu_knowledge_manager.md](zazu_knowledge_manager.md) |
| 2 | **Job Researcher** | `zazu_researcher` | [zazu_researcher.md](zazu_researcher.md) |
| 3 | **Application Coach** | `zazu_coach` | [zazu_coach.md](zazu_coach.md) |

Each profile page covers **role**, **interdependencies**, **outputs & artifacts**,
**tools**, and **internet requirements**.

------------------------------------------------------------------------

## How they connect

```
KB ──read──► Job Researcher ──► Recommendation Report ──► User
                    │
User approves ◄─────┘
      │
      ▼
KB ──read──► Application Coach ──► Resume / CL / Brief ──► User
      │                              │
      │                              └── KB proposals ──► KB Manager ──► User approves ──► KB
      │
KB Manager ◄── read/write (after approval) ──► KB
```

| Phase | Profile | Question |
|---|---|---|
| Front desk | Career Knowledge Manager | *What should run? What's my MCP response rate?* |
| Stewardship | Career Knowledge Manager | *Is our career knowledge accurate?* |
| Discovery | Job Researcher | *Should I pursue this?* |
| Execution | Application Coach | *How do I win this?* |

→ Full architecture: [Career_Intelligence_System.md](../Career_Intelligence_System.md)  
→ CKM front desk RFC: [rfc/CKM_front_desk.md](../rfc/CKM_front_desk.md)  
→ Opportunity intake: [working_agreements.md](../../agentic/hermes/working_agreements.md)
