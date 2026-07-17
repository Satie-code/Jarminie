# JARMINEI Build Status

Tracks progress against the roadmap in [04_Master_Implementation_Plan.md](04_Master_Implementation_Plan.md). Each module's status is one of: `Planned`, `Designing`, `Developing`, `Testing`, `Complete`, `Needs Refactoring`. Per-sprint detail (spec + completion report) lives in [sprint_book/](sprint_book/); this file is the high-level dashboard.

## Level 1 — Foundation (target: v0.1) — ✔ RELEASED

| Phase | Status | Notes |
|---|---|---|
| 1.1 Repository Bootstrap | Complete | See [sprint_book/INDEX.md](sprint_book/INDEX.md) for the full Master Sprint Book, or [sprint_book/sprint_1_1.md](sprint_book/sprint_1_1.md) directly. Full dependency install deferred — see [backlog/technical_debt.md](backlog/technical_debt.md). |
| 1.2 Core Framework | Complete | All four sprints done (1.2 Configuration Manager, 1.3 Logging System, 1.4 Health Monitor, 1.5 Core Manager) — see [sprint_book/INDEX.md](sprint_book/INDEX.md). `main.py` runs end-to-end: config loads, logging initializes, JARMINEI starts up and shuts down cleanly. |
| 1.3 Desktop Interface | Complete | All four sprints done (Desktop Shell, Status Panel, Settings Window, Debug Console). Settings persist across a restart and logs stream live in-app, both verified end-to-end. |

**Level 1 acceptance pass + post-release review recorded in [sprint_book/sprint_1_9.md](sprint_book/sprint_1_9.md). Released as [0.1.0](changelog/0.1.0.md).** 95/95 tests passing, `ruff check .` clean.

## Level 2 — Communication (target: v0.2)

| Phase | Status |
|---|---|
| 2.1 Voice Pipeline | Complete — all six sprints done (2.1 Microphone Manager, 2.2 Wake Word Detector, 2.3 Speech-to-Text, 2.4 Text-to-Speech, 2.5 Voice Session Manager & Timeout, 2.6 Quiet Mode Controller); see [sprint_book/INDEX.md](sprint_book/INDEX.md). Wake phrase, speech recognition, and voice responses all function (verified against fakes for the Quiet Mode state machine; real-hardware/model verification done per-sprint in 2.1–2.5). Wiring these modules together in `main.py` is deferred to Sprint 2.12 (Communication Pipeline Integration) by design. |
| 2.2 Conversation Engine | Complete — both sprints done (2.7 Conversation Session Store, 2.8 Context Manager); see [sprint_book/INDEX.md](sprint_book/INDEX.md). `database/sqlite_client.py`, `voice/conversation_store.py`, and `voice/context_manager.py` assemble a queryable working-context object (recent turns, active persona, session timing) from persisted turns — no inference/scoring anywhere in this phase, by design (that's Level 3's Decision Engine). |
| 2.3 Persona Engine | Complete — all three sprints done (2.9 Persona Base & Jarvis Persona, 2.10 Minie Persona, 2.11 Persona Switching & Explicit Selection); see [sprint_book/INDEX.md](sprint_book/INDEX.md). `PersonaManager` enforces exactly-one-active-persona with Part 2's full priority-ordered switching mechanism — only Explicit Selection and a heuristic Context Detection are wired in Level 2; Critical Emergency (Sprint 3.10) and Daily Routine (Sprint 4.8+) are named but reserved. `compose_reply()` remains a deliberate Level 2 placeholder (templated acknowledgement, no real reasoning) until Sprint 3.7's Decision Engine. **This closes all of Level 2's individual-component sprints (2.1–2.11).** |

## Level 3 — Intelligence (target: v0.3)

| Phase | Status |
|---|---|
| 3.1 Memory Engine | Planned |
| 3.2 Dynamic Memory | Planned |
| 3.3 Decision Engine | Planned |

## Level 4 — Productivity (target: v0.4)

| Phase | Status |
|---|---|
| 4.1 Device Control | Planned |
| 4.2 Workflow Engine | Planned |
| 4.3 Scheduler | Planned |
| 4.4 Internet Agent | Planned |

## Level 5 — Companion (target: v0.5)

| Phase | Status |
|---|---|
| 5.1 Emotion Engine | Planned |
| 5.2 Wellness Engine | Planned |
| 5.3 Analytics | Planned |
| 5.4 Learning Engine | Planned |

## Level 6 — Stabilization (target: v1.0)

| Phase | Status |
|---|---|
| 6.1 Performance | Planned |
| 6.2 Reliability | Planned |
| 6.3 Security | Planned |
| 6.4 Documentation | Planned |
| 6.5 Final Testing | Planned |

## Technical Debt

Tracked in [backlog/technical_debt.md](backlog/technical_debt.md), per the spec's Technical Debt Policy.
