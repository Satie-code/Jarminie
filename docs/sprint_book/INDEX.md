# JARMINEI Master Sprint Book — Index

The single roadmap for Version 1. Generated per [docs/05_Claude_Development_Guide.md](../05_Claude_Development_Guide.md)'s Sprint Book instruction, from the architecture in [02_System_Architecture.md](../02_System_Architecture.md) and the phase roadmap in [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md).

## Numbering Convention

**Sprint ID = `<Level>.<SequentialIndex>`**, where the index restarts at 1 for each Level and increments once per sprint regardless of which Part-4 Phase it belongs to (a Phase may span several sprints — see the "Sprint Size" rule in the Development Guide: one subsystem/feature/integration milestone per sprint). This supersedes the earlier version-numbered guess (`sprint_0_1`) used before this instruction existed — see [../backlog/technical_debt.md](../backlog/technical_debt.md) item 4.

Each sprint file lives at `docs/sprint_book/sprint_<level>_<index>.md`.

## Detail Status

Per an explicit scoping decision (2026-07-11): **Level 1 sprints are fully specified now** (all 16+ template sections). **Levels 2–6 are indexed here at roadmap granularity only** — full per-sprint detail will be written when each level becomes current, so technical design (classes/interfaces) reflects what Level 1–N actually taught us rather than upfront speculation. Expand any sprint early on request.

---

## LEVEL 1 — Foundation → Release v0.1 — ✔ RELEASED (2026-07-11)

| Sprint | Name                            | Phase | Depends On    | Complexity | Detail                                        |
| ------ | ------------------------------- | ----- | ------------- | ---------- | --------------------------------------------- |
| 1.1    | Repository Bootstrap            | 1.1   | —             | Low        | [sprint_1_1.md](sprint_1_1.md) — **Complete** |
| 1.2    | Configuration Manager           | 1.2   | 1.1           | Low–Medium | [sprint_1_2.md](sprint_1_2.md) — **Complete** |
| 1.3    | Logging System                  | 1.2   | 1.2           | Low        | [sprint_1_3.md](sprint_1_3.md) — **Complete** |
| 1.4    | Health Monitor (resource probe) | 1.2   | 1.2           | Low–Medium | [sprint_1_4.md](sprint_1_4.md) — **Complete** |
| 1.5    | Core Manager                    | 1.2   | 1.2, 1.3, 1.4 | Medium     | [sprint_1_5.md](sprint_1_5.md) — **Complete** |
| 1.6    | Desktop Shell & Main Window     | 1.3   | 1.5           | Medium     | [sprint_1_6.md](sprint_1_6.md) — **Complete** |
| 1.7    | Status Panel                    | 1.3   | 1.6, 1.4      | Low        | [sprint_1_7.md](sprint_1_7.md) — **Complete** |
| 1.8    | Settings Window                 | 1.3   | 1.6, 1.2      | Low–Medium | [sprint_1_8.md](sprint_1_8.md) — **Complete** |
| 1.9    | Debug Console                   | 1.3   | 1.6, 1.3      | Low        | [sprint_1_9.md](sprint_1_9.md) — **Complete** |

See the Level 1 Acceptance Pass in [sprint_1_9.md](sprint_1_9.md) and [changelog/0.1.0.md](../changelog/0.1.0.md).

## LEVEL 2 — Communication → Release v0.2

| Sprint | Name                                      | Phase | Depends On                          | Complexity  |
| ------ | ----------------------------------------- | ----- | ----------------------------------- | ----------- |
| 2.1    | Wake Word Detector                        | 2.1   | 1.5, 1.2                            | Medium      |
| 2.2    | Microphone Manager                        | 2.1   | 2.1                                 | Medium      |
| 2.3    | Speech-to-Text Engine (Whisper)           | 2.1   | 2.2                                 | Medium–High |
| 2.4    | Text-to-Speech Engine (Coqui, dual voice) | 2.1   | 1.2                                 | Medium–High |
| 2.5    | Voice Session Manager & Timeout           | 2.1   | 2.3, 2.4                            | Medium      |
| 2.6    | Quiet Mode Controller                     | 2.1   | 2.1, 2.5                            | Medium      |
| 2.7    | Conversation Session Store                | 2.2   | 2.5, database (3.1) stub            | Medium      |
| 2.8    | Context Manager                           | 2.2   | 2.7                                 | Medium      |
| 2.9    | Persona Base & Jarvis Persona             | 2.3   | 2.4                                 | Medium      |
| 2.10   | Minie Persona                             | 2.3   | 2.9                                 | Low–Medium  |
| 2.11   | Persona Switching & Explicit Selection    | 2.3   | 2.9, 2.10, authority (3.10) partial | Medium–High |

## LEVEL 3 — Intelligence → Release v0.3

| Sprint | Name                                               | Phase | Depends On          | Complexity  |
| ------ | -------------------------------------------------- | ----- | ------------------- | ----------- |
| 3.1    | Memory Store Foundation (SQLite + ChromaDB)        | 3.1   | 1.2, 1.5            | Medium–High |
| 3.2    | Shared Memory & Persona Memory                     | 3.1   | 3.1                 | Medium      |
| 3.3    | Event Memory                                       | 3.1   | 3.1                 | Low–Medium  |
| 3.4    | Short-Term Memory                                  | 3.1   | 3.1                 | Low–Medium  |
| 3.5    | Confidence Scoring Engine                          | 3.2   | 3.2, 3.3, 3.4       | Medium–High |
| 3.6    | Memory Lifecycle Manager (cleanup/review/override) | 3.2   | 3.5                 | Medium      |
| 3.7    | Intent Detection                                   | 3.3   | 2.8, Ollama runtime | High        |
| 3.8    | Context Analysis                                   | 3.3   | 3.7, 2.8, 3.5       | Medium–High |
| 3.9    | Priority Queue                                     | 3.3   | 1.5                 | Medium      |
| 3.10   | Authority Evaluation & Engine Selection            | 3.3   | 3.7, 3.8, 3.9       | High        |

## LEVEL 4 — Productivity → Release v0.4

| Sprint | Name                                           | Phase | Depends On         | Complexity  |
| ------ | ---------------------------------------------- | ----- | ------------------ | ----------- |
| 4.1    | Application Control                            | 4.1   | 1.5, security stub | Medium      |
| 4.2    | File & Folder Operations                       | 4.1   | 4.1                | Medium      |
| 4.3    | Window Management                              | 4.1   | 4.1                | Low–Medium  |
| 4.4    | System Monitoring & Resource Protection (full) | 4.1   | 1.4                | Medium      |
| 4.5    | Workflow Builder                               | 4.2   | 3.10               | Medium      |
| 4.6    | Workflow Executor                              | 4.2   | 4.5, 4.1–4.3       | Medium–High |
| 4.7    | Large-Workflow Confirmation Gate               | 4.2   | 4.6                | Low–Medium  |
| 4.8    | Calendar & Deadlines Store                     | 4.3   | 3.1                | Medium      |
| 4.9    | Reminder Engine (delay/reschedule/postpone)    | 4.3   | 4.8, 3.9           | Medium–High |
| 4.10   | Search & Research                              | 4.4   | 3.10               | Medium      |
| 4.11   | Summarization & Source Validation              | 4.4   | 4.10               | Medium–High |

## LEVEL 5 — Companion → Release v0.5

| Sprint | Name                                      | Phase | Depends On | Complexity  |
| ------ | ----------------------------------------- | ----- | ---------- | ----------- |
| 5.1    | Emotion Signal Collection                 | 5.1   | 2.3, 2.8   | Medium      |
| 5.2    | Emotion Inference & Contextual Adaptation | 5.1   | 5.1        | Medium–High |
| 5.3    | Wellness Triggers                         | 5.2   | 4.9, 5.2   | Medium      |
| 5.4    | Wellness Escalation & Hard Limit          | 5.2   | 5.3        | Medium      |
| 5.5    | Adaptive Wellness                         | 5.2   | 5.4, 5.8   | Medium–High |
| 5.6    | Usage & Habit Tracking                    | 5.3   | 4.4, 4.1   | Medium      |
| 5.7    | Analytics Dashboard Data                  | 5.3   | 5.6        | Low–Medium  |
| 5.8    | Pattern Recognition                       | 5.4   | 3.2, 5.6   | High        |
| 5.9    | Preference Learning & Recommendations     | 5.4   | 5.8        | Medium–High |

## LEVEL 6 — Stabilization → Release v1.0

| Sprint | Name                                               | Phase | Depends On | Complexity  |
| ------ | -------------------------------------------------- | ----- | ---------- | ----------- |
| 6.1    | Startup & Caching Optimization                     | 6.1   | all prior  | Medium      |
| 6.2    | Async Background Task Audit                        | 6.1   | all prior  | Medium      |
| 6.3    | Stress & Recovery Testing                          | 6.2   | all prior  | Medium–High |
| 6.4    | Resource Protection & Fail-Gracefully Verification | 6.2   | 1.4, 4.4   | Medium      |
| 6.5    | Permission & Encryption Audit                      | 6.3   | all prior  | Medium–High |
| 6.6    | Privacy Verification                               | 6.3   | all prior  | Medium      |
| 6.7    | Full Documentation Pass                            | 6.4   | all prior  | Low–Medium  |
| 6.8    | Full Test Suite Pass (unit/integration/system/UAT) | 6.5   | all prior  | High        |

---

## Milestones

| Version | After Sprint | Theme                                                 |
| ------- | ------------ | ----------------------------------------------------- |
| 0.1     | 1.9          | Stable project foundation — ✔ **Released 2026-07-11** |
| 0.2     | 2.11         | Voice interaction operational                         |
| 0.3     | 3.10         | Intelligent memory and decision system                |
| 0.4     | 4.11         | Complete productivity assistant                       |
| 0.5     | 5.9          | Complete personal AI companion                        |
| 1.0     | 6.8          | Official JARMINEI Release                             |

## Recommendations (not part of the official roadmap — flagged separately per the Development Guide's constraints)

- Consider a thin `security/` stub (permission-check pass-through, no real enforcement) as early as Sprint 4.1, rather than deferring all Security Layer work to Level 6 — Device Control's "permission-sensitive operations always require user approval" (Part 2) needs _something_ to call even before Phase 6.3 builds it out fully. Flag for discussion before Sprint 4.1, not a change to the roadmap itself.
- `database/` (SQLite layer) is first exercised in Sprint 3.1 but `config/` (Sprint 1.2) and `scheduler` (Sprint 4.8) also need persistent storage — worth deciding at Sprint 3.1 whether the SQLite access layer is generic enough to serve all three, to avoid three separate ad hoc DB-access implementations.
