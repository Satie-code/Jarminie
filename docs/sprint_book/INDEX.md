# JARMINEI Master Sprint Book — Index

The single roadmap for Version 1. Generated per [docs/05_Claude_Development_Guide.md](../05_Claude_Development_Guide.md)'s Sprint Book instruction, from the architecture in [02_System_Architecture.md](../02_System_Architecture.md) and the phase roadmap in [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md).

## Numbering Convention

**Sprint ID = `<Level>.<SequentialIndex>`**, where the index restarts at 1 for each Level and increments once per sprint regardless of which Part-4 Phase it belongs to (a Phase may span several sprints — see the "Sprint Size" rule in the Development Guide: one subsystem/feature/integration milestone per sprint). This supersedes the earlier version-numbered guess (`sprint_0_1`) used before this instruction existed — see [../backlog/technical_debt.md](../backlog/technical_debt.md) item 4.

Each sprint file lives at `docs/sprint_book/sprint_<level>_<index>.md`.

## Detail Status

Per an explicit scoping decision (2026-07-11): **Level 1 sprints are fully specified** (all 16+ template sections). **Level 2 was expanded to full detail on 2026-07-16**, per an explicit request now that Level 1 is complete and released — see `sprint_2_1.md`–`sprint_2_14.md`. **Level 3 was expanded to full detail on 2026-07-18**, per an explicit request now that Level 2 is complete (pending only its outstanding manual real-hardware verification) — see `sprint_3_1.md`–`sprint_3_14.md` and the breakdown note below. **Levels 4–6 remain at roadmap granularity only** — full per-sprint detail will be written when each level becomes current, so technical design (classes/interfaces) reflects what came before rather than upfront speculation. Expand any sprint early on request.

### Level 3 breakdown changes (2026-07-18)

This roadmap originally listed Level 3 as 10 sprints (3.1–3.10). Expanding to full detail surfaced one real gap against [02_System_Architecture.md](../02_System_Architecture.md)'s own Decision Engine pipeline diagram — *"Intent Detection → Context Analysis → Memory Retrieval → Priority Evaluation → Authority Evaluation → Engine Selection"* — which names **Memory Retrieval** as its own pipeline stage with no corresponding sprint in the original 10. Three deliberate deviations from that original list, each explained in full in the affected sprint files, not just here:

1. **A new sprint, Memory Retrieval Engine, inserted as 3.9** (between Context Analysis and Priority Queue, matching the pipeline diagram's own ordering exactly) — the cross-memory-type, confidence-weighted query composition layer the diagram's "Memory Retrieval" stage implies, distinct from the per-type retrieval primitives Sprints 3.1–3.4 already ship. This shifts the original 3.7–3.10 (Intent Detection, Context Analysis, Priority Queue, Authority Evaluation) to 3.7, 3.8, 3.10, 3.11 respectively. See [sprint_3_9.md](sprint_3_9.md)'s Engineering Rationale.
2. **Explainability was not given its own sprint** — Phase 3.3's own acceptance criterion ("Explainability preserved") ties it directly to Authority Evaluation, so it is built as a first-class deliverable of [sprint_3_11.md](sprint_3_11.md) (`DecisionTrace`, `AuthorityEvaluator.explain()`) rather than a separate sprint, matching how the Engineering Specification itself frames the two together.
3. **Three sprints added (3.12–3.14)**: Decision Engine Integration, Error Handling & Recovery Hardening, and Integration Testing & Level Freeze — mirroring the exact precedent Level 2 already set for itself (see the Level 2 breakdown-changes note below) when it went from roadmap-granularity to full detail. Level 3's integration surface (SQLite + ChromaDB + Ollama + a six-stage pipeline) is at least as large as Level 2's real-time voice/hardware surface, so it earns the same dedicated wiring/hardening/freeze treatment rather than folding into the last component sprint.

Every other component identity, name, and dependency below is unchanged from the original roadmap-granularity plan — Sprints 3.1–3.6 (Memory Store Foundation through Memory Lifecycle Manager) are renumbered not at all.

### Level 2 breakdown changes (2026-07-16)

Two deliberate deviations from the roadmap recorded below prior to this date — both explained in full in the affected sprint files, not just here:

1. **2.1 and 2.2 swapped** — Microphone Manager now precedes Wake Word Detector (previously the reverse), so Wake Word Detector receives a `MicrophoneManager` via Dependency Injection instead of building its own throwaway audio stream. See [sprint_2_1.md](sprint_2_1.md)'s Engineering Rationale.
2. **Three sprints added (2.12–2.14)**: Communication Pipeline Integration, Error Handling & Recovery Hardening, and Integration Testing & Level Freeze. Level 2's real-time, hardware-and-ML-dependent integration surface is much larger than Level 1's, so wiring, resilience hardening, and level-closing acceptance are each given their own planned sprint rather than folded into the last component sprint the way Level 1 did retroactively in `sprint_1_9.md`. See each sprint file's Engineering Rationale.

Every other component identity, name, and dependency below is unchanged from the original roadmap-granularity plan.

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

## LEVEL 2 — Communication → Release v0.2 — ✔ RELEASED (2026-07-17)

| Sprint | Name                                       | Phase       | Depends On                | Complexity  | Detail                             |
| ------ | ------------------------------------------ | ----------- | ------------------------- | ----------- | ---------------------------------- |
| 2.1    | Microphone Manager                         | 2.1         | 1.5, 1.2                  | Medium      | [sprint_2_1.md](sprint_2_1.md) — **Complete** |
| 2.2    | Wake Word Detector                         | 2.1         | 2.1                       | Medium      | [sprint_2_2.md](sprint_2_2.md) — **Complete** |
| 2.3    | Speech-to-Text Engine (Whisper)            | 2.1         | 2.1                       | Medium–High | [sprint_2_3.md](sprint_2_3.md) — **Complete** |
| 2.4    | Text-to-Speech Engine (Coqui, dual voice)  | 2.1         | 1.2                       | Medium–High | [sprint_2_4.md](sprint_2_4.md) — **Complete** |
| 2.5    | Voice Session Manager & Timeout            | 2.1         | 2.3, 2.4, 2.1             | Medium      | [sprint_2_5.md](sprint_2_5.md) — **Complete** |
| 2.6    | Quiet Mode Controller                      | 2.1         | 2.2, 2.5                  | Medium      | [sprint_2_6.md](sprint_2_6.md) — **Complete** |
| 2.7    | Conversation Session Store                 | 2.2         | 2.5, database (3.1) stub  | Medium      | [sprint_2_7.md](sprint_2_7.md) — **Complete** |
| 2.8    | Context Manager                            | 2.2         | 2.7                       | Low–Medium  | [sprint_2_8.md](sprint_2_8.md) — **Complete** |
| 2.9    | Persona Base & Jarvis Persona              | 2.3         | 2.4                       | Low–Medium  | [sprint_2_9.md](sprint_2_9.md) — **Complete** |
| 2.10   | Minie Persona                              | 2.3         | 2.9                       | Low         | [sprint_2_10.md](sprint_2_10.md) — **Complete** |
| 2.11   | Persona Switching & Explicit Selection     | 2.3         | 2.9, 2.10                 | Medium–High | [sprint_2_11.md](sprint_2_11.md) — **Complete** |
| 2.12   | Communication Pipeline Integration         | integration | 2.1–2.11                  | Medium–High | [sprint_2_12.md](sprint_2_12.md) — **Complete** |
| 2.13   | Error Handling & Recovery Hardening        | reliability | 2.12                      | Medium      | [sprint_2_13.md](sprint_2_13.md) — **Complete** |
| 2.14   | Integration Testing & Level Freeze         | level gate  | 2.13                      | Medium–High | [sprint_2_14.md](sprint_2_14.md) — **Complete** |

See the Level 2 Acceptance Pass in [sprint_2_14.md](sprint_2_14.md) and [changelog/0.2.0.md](../changelog/0.2.0.md). One criterion (a live, human-voice wake-to-reply round trip) remains manual-only, not yet performed — the `v0.2.0` tag is deferred until it is, per `sprint_2_14.md`'s own Acceptance Criteria ordering.

Note: `2.11`'s dependency on Level 3's Authority System (originally noted here as "authority (3.10) partial") is now handled differently — see [sprint_2_11.md](sprint_2_11.md)'s Engineering Rationale: the `CRITICAL_EMERGENCY` priority slot is reserved in the `SwitchReason` enum but deliberately left unwired until the Authority Evaluation sprint exists, rather than treating it as a partial dependency of this Level. That sprint is now numbered **3.11**, not 3.10 — see the "Level 3 breakdown changes (2026-07-18)" note below for why.

## LEVEL 3 — Intelligence → Release v0.3

See the "Level 3 breakdown changes (2026-07-18)" note above for how this table differs from the original 10-sprint roadmap-granularity plan.

| Sprint | Name                                                | Phase       | Depends On          | Complexity  | Detail                           |
| ------ | ---------------------------------------------------- | ----------- | -------------------- | ----------- | --------------------------------- |
| 3.1    | Memory Store Foundation (SQLite + ChromaDB)          | 3.1         | 1.2, 1.5, 2.7        | Medium–High | [sprint_3_1.md](sprint_3_1.md) — **Complete**   |
| 3.2    | Shared Memory & Persona Memory                       | 3.1         | 3.1                  | Medium      | [sprint_3_2.md](sprint_3_2.md) — **Complete**   |
| 3.3    | Event Memory                                         | 3.1         | 3.1                  | Low–Medium  | [sprint_3_3.md](sprint_3_3.md) — **Complete**   |
| 3.4    | Short-Term Memory                                    | 3.1         | 3.1, 2.7             | Low–Medium  | [sprint_3_4.md](sprint_3_4.md) — **Complete**   |
| 3.5    | Confidence Scoring Engine                            | 3.2         | 3.2, 3.3, 3.4        | Medium–High | [sprint_3_5.md](sprint_3_5.md) — **Complete**   |
| 3.6    | Memory Lifecycle Manager (cleanup/review/override)   | 3.2         | 3.5                  | Medium      | [sprint_3_6.md](sprint_3_6.md) — **Complete**   |
| 3.7    | Intent Detection                                     | 3.3         | 2.8, Ollama runtime  | High        | [sprint_3_7.md](sprint_3_7.md) — **Complete**   |
| 3.8    | Context Analysis                                     | 3.3         | 3.7, 2.8             | Medium–High | [sprint_3_8.md](sprint_3_8.md) — **Complete**   |
| 3.9    | Memory Retrieval Engine                              | 3.3         | 3.1–3.6              | Medium–High | [sprint_3_9.md](sprint_3_9.md) — **Complete**   |
| 3.10   | Priority Queue                                       | 3.3         | 1.5, 3.9             | Medium      | [sprint_3_10.md](sprint_3_10.md) — **Complete** |
| 3.11   | Authority Evaluation & Engine Selection              | 3.3         | 3.7, 3.8, 3.9, 3.10  | High        | [sprint_3_11.md](sprint_3_11.md) — **Complete** |
| 3.12   | Decision Engine Integration                          | integration | 3.1–3.11, 2.12       | Medium–High | [sprint_3_12.md](sprint_3_12.md) — **Complete** |
| 3.13   | Error Handling & Recovery Hardening                  | reliability | 3.12                 | Medium      | [sprint_3_13.md](sprint_3_13.md) — **Complete** |
| 3.14   | Integration Testing & Level Freeze                   | level gate  | 3.13                 | Medium–High | [sprint_3_14.md](sprint_3_14.md) — **Complete** |

## LEVEL 4 — Productivity → Release v0.4

| Sprint | Name                                           | Phase | Depends On         | Complexity  |
| ------ | ---------------------------------------------- | ----- | ------------------ | ----------- |
| 4.1    | Application Control                            | 4.1   | 1.5, security stub | Medium      |
| 4.2    | File & Folder Operations                       | 4.1   | 4.1                | Medium      |
| 4.3    | Window Management                              | 4.1   | 4.1                | Low–Medium  |
| 4.4    | System Monitoring & Resource Protection (full) | 4.1   | 1.4                | Medium      |
| 4.5    | Workflow Builder                               | 4.2   | 3.11               | Medium      |
| 4.6    | Workflow Executor                              | 4.2   | 4.5, 4.1–4.3       | Medium–High |
| 4.7    | Large-Workflow Confirmation Gate               | 4.2   | 4.6                | Low–Medium  |
| 4.8    | Calendar & Deadlines Store                     | 4.3   | 3.1                | Medium      |
| 4.9    | Reminder Engine (delay/reschedule/postpone)    | 4.3   | 4.8, 3.10          | Medium–High |
| 4.10   | Search & Research                              | 4.4   | 3.11               | Medium      |
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
| 0.2     | 2.14         | Voice interaction operational — ✔ **Released 2026-07-17** |
| 0.3     | 3.14         | Intelligent memory and decision system — ✔ **Released 2026-07-20** |
| 0.4     | 4.11         | Complete productivity assistant                       |
| 0.5     | 5.9          | Complete personal AI companion                        |
| 1.0     | 6.8          | Official JARMINEI Release                             |

## Recommendations (not part of the official roadmap — flagged separately per the Development Guide's constraints)

- Consider a thin `security/` stub (permission-check pass-through, no real enforcement) as early as Sprint 4.1, rather than deferring all Security Layer work to Level 6 — Device Control's "permission-sensitive operations always require user approval" (Part 2) needs _something_ to call even before Phase 6.3 builds it out fully. Flag for discussion before Sprint 4.1, not a change to the roadmap itself.
- ~~`database/` (SQLite layer) is first exercised in Sprint 3.1 but `config/` (Sprint 1.2) and `scheduler` (Sprint 4.8) also need persistent storage — worth deciding at Sprint 3.1 whether the SQLite access layer is generic enough to serve all three, to avoid three separate ad hoc DB-access implementations.~~ **Resolved by [sprint_3_1.md](sprint_3_1.md)'s Engineering Rationale (2026-07-18)**: `database/sqlite_client.py`'s `SqliteClient` (built in Sprint 2.7) is confirmed generic enough and reused as-is — Sprint 3.1 adds a new `memory_records` table to the same `sqlite_path` file via the same caller-owns-its-own-DDL pattern `ConversationSessionStore` already established, rather than building a second database-access layer. `scheduler` (Sprint 4.8) should follow the identical pattern when it arrives.
- Level 3's `AuthorityEvaluator` (Sprint 3.11) ships with a structurally empty `approved_emergency_procedures` whitelist — by design, since no pre-approved emergency procedure exists until Device Control does. **Sprint 4.1 (Application Control) should treat populating this whitelist as a deliberate, reviewed act**, not an incidental side effect of building Device Control — see [sprint_3_11.md](sprint_3_11.md)'s Future Considerations. Flag for discussion before Sprint 4.1, not a change to the Level 3 roadmap itself.
