# JARMINEI Build Status

Tracks progress against the roadmap in [04_Master_Implementation_Plan.md](04_Master_Implementation_Plan.md). Each module's status is one of: `Planned`, `Designing`, `Developing`, `Testing`, `Complete`, `Needs Refactoring`. Per-sprint detail (spec + completion report) lives in [sprint_book/](sprint_book/); this file is the high-level dashboard.

## Level 1 — Foundation (target: v0.1) — ✔ RELEASED

| Phase | Status | Notes |
|---|---|---|
| 1.1 Repository Bootstrap | Complete | See [sprint_book/INDEX.md](sprint_book/INDEX.md) for the full Master Sprint Book, or [sprint_book/sprint_1_1.md](sprint_book/sprint_1_1.md) directly. Full dependency install deferred — see [backlog/technical_debt.md](backlog/technical_debt.md). |
| 1.2 Core Framework | Complete | All four sprints done (1.2 Configuration Manager, 1.3 Logging System, 1.4 Health Monitor, 1.5 Core Manager) — see [sprint_book/INDEX.md](sprint_book/INDEX.md). `main.py` runs end-to-end: config loads, logging initializes, JARMINEI starts up and shuts down cleanly. |
| 1.3 Desktop Interface | Complete | All four sprints done (Desktop Shell, Status Panel, Settings Window, Debug Console). Settings persist across a restart and logs stream live in-app, both verified end-to-end. |

**Level 1 acceptance pass + post-release review recorded in [sprint_book/sprint_1_9.md](sprint_book/sprint_1_9.md). Released as [0.1.0](changelog/0.1.0.md).** 95/95 tests passing, `ruff check .` clean.

## Level 2 — Communication (target: v0.2) — ✔ RELEASED

| Phase | Status |
|---|---|
| 2.1 Voice Pipeline | Complete — all six sprints done (2.1 Microphone Manager, 2.2 Wake Word Detector, 2.3 Speech-to-Text, 2.4 Text-to-Speech, 2.5 Voice Session Manager & Timeout, 2.6 Quiet Mode Controller); see [sprint_book/INDEX.md](sprint_book/INDEX.md). Wake phrase, speech recognition, and voice responses all function (verified against fakes for the Quiet Mode state machine; real-hardware/model verification done per-sprint in 2.1–2.5). Wiring these modules together in `main.py` is deferred to Sprint 2.12 (Communication Pipeline Integration) by design. |
| 2.2 Conversation Engine | Complete — both sprints done (2.7 Conversation Session Store, 2.8 Context Manager); see [sprint_book/INDEX.md](sprint_book/INDEX.md). `database/sqlite_client.py`, `voice/conversation_store.py`, and `voice/context_manager.py` assemble a queryable working-context object (recent turns, active persona, session timing) from persisted turns — no inference/scoring anywhere in this phase, by design (that's Level 3's Decision Engine). |
| 2.3 Persona Engine | Complete — all three sprints done (2.9 Persona Base & Jarvis Persona, 2.10 Minie Persona, 2.11 Persona Switching & Explicit Selection); see [sprint_book/INDEX.md](sprint_book/INDEX.md). `PersonaManager` enforces exactly-one-active-persona with Part 2's full priority-ordered switching mechanism — only Explicit Selection and a heuristic Context Detection are wired in Level 2; Critical Emergency (Sprint 3.11, renumbered from the original 3.10 placeholder when Level 3 was expanded to full detail — see [sprint_book/INDEX.md](sprint_book/INDEX.md)'s Level 3 breakdown note) and Daily Routine (Sprint 4.8+) are named but reserved. `compose_reply()` remains a deliberate Level 2 placeholder (templated acknowledgement, no real reasoning) until Sprint 3.7's Decision Engine. **This closes all of Level 2's individual-component sprints (2.1–2.11).** |

**Sprint 2.12 (Communication Pipeline Integration)** wired every Level 2 module into one real system via `voice/pipeline.py`'s `CommunicationPipeline`, with `main.py` constructing and registering the full 9-`ManagedModule` graph through `CoreManager` — the same composition-root pattern Level 1 established. **Sprint 2.13 (Error Handling & Recovery Hardening)** applied the Fail Gracefully Rule across six specific failure scenarios (microphone disconnect, Whisper failure, Coqui failure, wake-word thread death, persona reply failure, SQLite write failure), finding and fixing several real gaps beyond what was originally planned — see `sprint_2_13.md`'s own completion report.

**Sprint 2.14 (Integration Testing & Level Freeze) formally closes Level 2 — Communication and Release v0.2.** A full Level 2 Acceptance Pass confirmed every Phase 2.1 ("Wake phrase activates JARMINEI. Speech recognition functions. Voice responses function."), 2.2 ("Natural conversation maintained during session."), and 2.3 ("Correct persona selected. Correct voice selected. No simultaneous personas.") criterion together, via: a new `tests/system/test_level2_acceptance.py` driving one continuous scripted multi-turn conversation through a real `CoreManager.startup()`/`shutdown()` with the entire Level 2 graph registered; `tests/integration/test_voice_pipeline_integration.py` confirming all six of Sprint 2.13's hardened failure scenarios at the integration level (not just unit level); an adversarial re-read of every `voice/`/`personas/` source file that found and fixed two further real gaps (`QuietModeController.activate()` could get stuck ACTIVE-with-no-session if `begin_session()` failed; `ConversationSessionStore.purge_older_than()` had no failure handling at all) — see `sprint_2_6.md` and `sprint_2_7.md`'s own Post-Sprint Fix sections; and a real, non-mocked smoke run completing a full turn through real Whisper, real Coqui (with real audio played through actual speakers), and a real microphone. 289/289 tests passing, `ruff check .` clean. Full detail in `sprint_2_14.md`'s Sprint Completion Report and [changelog/0.2.0.md](changelog/0.2.0.md).

**One criterion remains outstanding, not satisfiable by any automated test**: a live, human-voice wake-word-to-spoken-reply round trip on the actual target laptop, performed by a person — this sprint's own Acceptance Criteria name it as "the one criterion that cannot be satisfied by any automated test in this Sprint Book." Everything upstream of that specific interactive step (real model loads, real hardware I/O, the full turn-processing chain) has been verified for real; only a human actually speaking the wake phrase and confirming the reply remains. **The `v0.2.0` git tag has not been created** — per this sprint's own Acceptance Criteria ordering ("performed... before tagging the release"), tagging is deferred until that manual verification happens.

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
