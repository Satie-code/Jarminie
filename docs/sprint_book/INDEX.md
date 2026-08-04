# JARMINEI Master Sprint Book — Index

The single roadmap for Version 1. Generated per [docs/05_Claude_Development_Guide.md](../05_Claude_Development_Guide.md)'s Sprint Book instruction, from the architecture in [02_System_Architecture.md](../02_System_Architecture.md) and the phase roadmap in [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md).

## Numbering Convention

**Sprint ID = `<Level>.<SequentialIndex>`**, where the index restarts at 1 for each Level and increments once per sprint regardless of which Part-4 Phase it belongs to (a Phase may span several sprints — see the "Sprint Size" rule in the Development Guide: one subsystem/feature/integration milestone per sprint). This supersedes the earlier version-numbered guess (`sprint_0_1`) used before this instruction existed — see [../backlog/technical_debt.md](../backlog/technical_debt.md) item 4.

Each sprint file lives at `docs/sprint_book/sprint_<level>_<index>.md`.

## Detail Status

Per an explicit scoping decision (2026-07-11): **Level 1 sprints are fully specified** (all 16+ template sections). **Level 2 was expanded to full detail on 2026-07-16**, per an explicit request now that Level 1 is complete and released — see `sprint_2_1.md`–`sprint_2_14.md`. **Level 3 was expanded to full detail on 2026-07-18**, per an explicit request now that Level 2 is complete (pending only its outstanding manual real-hardware verification) — see `sprint_3_1.md`–`sprint_3_14.md` and the breakdown note below. **Level 4 Part A (Device Control & Workflow Automation) was expanded to full detail on 2026-07-20**, per an explicit request now that Level 3 is complete and released — see `sprint_4_1.md`–`sprint_4_13.md` and the "Level 4 breakdown changes" note below. **Level 4 Part B (Scheduler & Internet Agent) was expanded to full detail on 2026-07-31**, per an explicit request now that Part A is frozen — see `sprint_4_14.md`–`sprint_4_20.md` and the "Level 4 Part B breakdown changes" note below. **Level 5 Part A (Emotional Intelligence & Presentation Layer) was expanded to full detail on 2026-08-02**, per an explicit request now that Level 4 is complete — see `sprint_5_1.md`–`sprint_5_16.md` and the "Level 5 breakdown changes" note below. **Level 5 Part B (Companion Intelligence) was expanded to full detail on 2026-08-04**, per an explicit request now that Part A is frozen — see `sprint_5_17.md`–`sprint_5_26.md` and the "Level 5 Part B breakdown changes" note below. **Level 6 remains at roadmap granularity only** — full per-sprint detail will be written once it becomes current, so technical design (classes/interfaces) reflects what came before rather than upfront speculation. Expand any sprint early on request.

### Level 5 breakdown changes (2026-08-02)

Level 5 is delivered as **two Sprint Books**, mirroring the exact precedent Level 4 already set for itself (see the "Level 4 breakdown changes" note below) — a deliberate scoping decision made explicitly, via `AskUserQuestion`, before any Level 5 sprint file was written:

- **Part A — Emotional Intelligence & Presentation Layer** (this expansion, sprints 5.1–5.16): the behavioral Emotion Engine Part 4's Phase 5.1 already named ("Stress detection. Fatigue detection. Frustration detection... Behavior adapts appropriately. Never performs medical diagnosis.") — plus an entirely new Presentation Layer (Jarvis's holographic-sphere/segmented-ring dashboard; Minie's avatar; gesture, persona-transition, voice-personality, adaptive-workspace, and companion-experience behavior) that neither Part 4's roadmap nor Part 3's technology stack anticipated. Commissioned as new scope in the same conversation that produced this Sprint Book.
- **Part B — Companion Intelligence** (Wellness Engine, Analytics, Learning Engine — Part 4's Phases 5.2/5.3/5.4): expanded to full detail on 2026-08-04, now that Part A is frozen — sprints 5.17–5.26 (see the "Level 5 Part B breakdown changes" note below for the real renumbering/build-order this expansion required, and the three integration/hardening/freeze sprints it added beyond the original roadmap-granularity table's own seven).

**`v0.5` ("Complete personal AI companion," per [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md)) is not redefined by this split and is not tagged until both parts freeze** — identical discipline to `v0.4`'s own two-part gating (see the Milestones table below).

Two further decisions were made explicitly via `AskUserQuestion` before writing any Part A sprint file, not assumed:

1. **The renderer's own architecture.** Part 3's locked tech stack names PySide6 as JARMINEI's only desktop UI technology, with no 3D/animation/avatar SDK named anywhere. Resolved not by picking one rendering technology outright, but by mandating a **renderer abstraction**: `Persona Controller -> Presentation State -> Renderer Interface -> {Jarvis Renderer, Minie Renderer}`, explicitly ruling out committing the whole project to QML or to any single avatar SDK. Jarvis's renderer (sprint 5.7) stays on native PySide6 (`QPainter`/`QGraphicsView`; OpenGL only if profiling later proves necessary — no QML). Minie's renderer (sprint 5.8) is built behind a generic `AvatarRenderer` interface whose first concrete implementation drives a locally-running VTube Studio instance through its own documented WebSocket Plugin API — JARMINEI never embeds or redistributes Live2D's own SDK, and nothing outside `presentation/vtube_studio_renderer.py` imports anything VTube-Studio-specific, so a future Live2D Cubism SDK embed, Unreal, or Unity backend needs only one new class plus one registry entry (mirrors `internet/search_provider_registry.py`'s already-established provider-swap precedent exactly — see that file's own docstring).
2. **Naming**: the Presentation Layer's own coordinator is named `PresentationController` (sprint 5.6), not `PersonaController` — the codebase already has a `PersonaManager` (`personas/persona_manager.py`, Sprint 2.11) owning *which* persona is active and *why*; a second, presentation-side class named similarly would be a real, avoidable ambiguity. `PresentationController` owns *how* the currently-active persona gets rendered, composing `PersonaManager`'s own active-persona read with Presentation State (sprint 5.5) — it never duplicates or second-guesses switching logic.

Also recorded here, per this project's own "log a real structural deviation rather than let it pass silently" discipline (the same treatment `emotion/`'s own folder addition got at Sprint 1.1 — `backlog/technical_debt.md` item 2): **a new top-level `presentation/` package is added**, not present in Part 3's original repository-structure list, for the identical one-engine-one-folder reason. Sprint 5.6 is where this folder is actually created; recorded here as the point of decision. **A concrete WebSocket client dependency for VTube Studio's API is deliberately left as an explicit stop-and-ask gate at Sprint 5.8**, not decided in this Sprint Book — mirroring Sprint 4.16's own precedent for the search-provider choice — since Part 3 names no WebSocket library at all and more than one reasonable option exists (a plain `websockets` client hand-rolled against VTube Studio's own documented JSON protocol, or a community wrapper such as `pyvts`).

### Level 5 Part B breakdown changes (2026-08-04)

Expanded to full detail now that Part A (Sprints 5.1–5.16) is frozen, per an explicit request ("continue with sprint 5 Part B"). **Unlike Level 4 Part B (whose seven sprints were unchanged in name, number, and scope from the original roadmap-granularity plan), Level 5 Part B's real build order required real renumbering**, discovered directly while diffing this Sprint Book's own roadmap-granularity table against itself (per `feedback_jarminei_workflow.md`'s own "diff repo vs docs before each phase" discipline) rather than assumed safe to expand in-place:

1. **A real forward dependency in the original roadmap-granularity table**: `Adaptive Wellness` (originally `5.19`) named `5.22` (`Pattern Recognition`, a later-numbered sprint) as one of its own two dependencies — the exact "a sprint depends on a later-numbered sprint" problem `docs/sprint_book/INDEX.md`'s own Level 3/Level 4 breakdown notes already required correcting when it appeared during their own expansions. Resolved the same way those were: full renumbering into real dependency order, not merely correcting the one broken reference in place.
2. **The renumbered order, old → new**: `5.20 Usage & Habit Tracking` → **5.17**; `5.17 Wellness Triggers` → **5.18**; `5.18 Wellness Escalation & Hard Limit` → **5.19**; `5.21 Analytics Dashboard Data` → **5.20**; `5.22 Pattern Recognition` → **5.21**; `5.19 Adaptive Wellness` → **5.22**; `5.23 Preference Learning & Recommendations` → **5.23** (unchanged). No sprint's own name or scope changed, only its number and its position in the build sequence — see the renumbered table below. This interleaves Phase 5.2 (Wellness)/5.3 (Analytics)/5.4 (Learning) sprints rather than keeping each phase's own sprints contiguous, a real, disclosed departure from every prior Level/Part's own phase-contiguous numbering (Level 5 Part A's own 5.1–5.13 table, for contrast, never needed this) — an honest consequence of Companion Intelligence's own cross-phase dependency shape, not a numbering inconsistency.
3. **Three sprints added (5.24–5.26): Companion Intelligence Integration, Error Handling & Recovery Hardening (Part B), and Integration Testing & Level Freeze (Part B)** — mirroring the exact precedent Level 2, Level 3, and Level 4 Part A each already set for themselves when moving from a component-only roadmap-granularity list to full detail (see the "Level 4 breakdown changes" note below, point 6, for the closest direct precedent). Unlike Level 4 Part B (whose original roadmap-granularity plan already accounted for its own integration/hardening/freeze trio within its seven sprints), Level 5 Part B's own roadmap-granularity table named only the seven component sprints — this expansion adds the trio every Level/Part boundary in this project's history has needed, rather than skipping it because the original planning document happened not to name it explicitly.

Two further real design decisions, made explicitly during expansion, not assumed:

1. **No new external dependency, and no stop-and-ask gate was needed** — unlike Level 4 Part B's Search & Research provider choice or Level 5 Part A's VTube Studio WebSocket client choice, `03_Engineering_Standards.md` already locks both libraries this Part's own screen-time/application-usage tracking needs (`pywin32`, already backing `device_control/`'s own foreground-window calls; `psutil`, already backing `core/resource_monitor.py`) — see `sprint_5_17.md`'s own Engineering Rationale.
2. **`voice/pipeline.py`'s `_check_and_announce_due_reminder()` (Sprint 4.18) is generalized into `_check_and_announce_priority_item()`, not duplicated** — that method's own docstring already anticipated exactly this moment ("a future, still-unhandled `PriorityItem` type... is never silently consumed... without understanding it"), directly satisfying the Development Guide's own Step 1 ("extend or improve... instead of recreating it"). `decision/priority_queue.py`'s `PriorityLevel.WELLNESS`/`GENERAL_SUGGESTION` and `decision/authority.py`'s `EngineSelection.WELLNESS` — reserved since Level 3/Level 5 Part A — get their first real producers/consumers at Sprint 5.24, closing two of `backlog/technical_debt.md` item 17's four sources (`IMPORTANT_ALERT` remains the one still-open source, disclosed explicitly rather than overstated, the same correction this exact item has already required at Sprint 3.14 and Sprint 4.18). See `sprint_5_24.md`'s own Engineering Rationale for the full reasoning, including why Wellness (and only Wellness, per Part 2's own "Owned exclusively by Minie" language) force-switches the active persona for its own announcement while Scheduled Reminders and General Suggestions do not.

Also recorded here, per this project's own "log a real structural deviation rather than let it pass silently" discipline: **no new top-level package was needed** — `wellness/`, `analytics/`, and `learning/` are all three already named in Part 3's own repository-structure list (unlike `emotion/`/`presentation/` at Level 5 Part A, both real additions requiring their own `backlog/technical_debt.md` entries), so no equivalent new-folder entry is warranted for this expansion.

This Sprint Book's own `sprint_book/README.md` had a stale note ("Levels 5-6 exist at roadmap/index granularity") predating even Level 5 Part A's own 2026-08-02 expansion — corrected as part of this same documentation pass, not left for a later sprint to notice.

### Level 4 Part B breakdown changes (2026-07-31)

Unlike Level 4 Part A's own expansion (which inserted, renamed, and renumbered several sprints against the original roadmap-granularity plan — see the note below), **Part B's seven sprints (4.14–4.20) are unchanged in name, number, and scope from the original roadmap-granularity plan** — no insertion or renumbering was needed. Two real design decisions, made explicitly during expansion rather than left implicit, worth recording here:

1. **A shared `TaskScheduler` class (introduced within Sprint 4.14/4.15's own detail, not a separate roadmap entry) owns the one real `APScheduler` `BackgroundScheduler` instance**, exposing a generic `add_job()`/`remove_job()` primitive rather than letting `ReminderEngine` own a private scheduler only it can register jobs against. This directly answers the open question this file's own Recommendations section had already raised when `backlog/technical_debt.md` items 11/15 were first logged ("worth deciding... whether one generic periodic-task mechanism can serve both `MemoryLifecycleManager`'s passes and `ConversationSessionStore.purge_older_than()`/`ActionAuditLog.purge_older_than()`, rather than three separate ad hoc timers") — Sprint 4.18 registers all three of those alongside `ReminderEngine`'s own poll and a new proactive-announcement check on the same shared instance, finally closing items 11/15's recurring-cadence gap for real. See [sprint_4_15.md](sprint_4_15.md)'s Engineering Rationale.
2. **Sprint 4.16 (Search & Research)'s own concrete search-provider choice is deliberately left as an explicit stop-and-ask gate**, not decided in this Sprint Book — Part 3's technology stack names no search provider or HTTP library at all (every other external dependency in this project is explicitly named), and this is the first sprint in JARMINEI's history whose whole purpose is making outbound requests to the public internet on the user's behalf, a real privacy/reliability boundary worth a deliberate decision rather than a default guess. See [sprint_4_16.md](sprint_4_16.md)'s Engineering Rationale.

Sprint 4.18 (Scheduler & Internet Agent Integration) is also where this project's first genuinely *proactive* (not turn-triggered) behavior is built — a due reminder interrupting an idle JARMINEI on its own initiative, via `QuietModeController`'s own `ActivationReason.SCHEDULED_ALERT` (reserved since Sprint 2.6, unused by any real caller until this sprint). See [sprint_4_18.md](sprint_4_18.md)'s Engineering Rationale.

### Level 4 breakdown changes (2026-07-20)

Level 4 is delivered as **two Sprint Books**, a deliberate scoping decision made explicitly before any Level 4 sprint file was written (not discovered mid-implementation, unlike the Level 2/3 breakdown changes below):

- **Part A — Device Control & Workflow Automation** (this expansion, sprints 4.1–4.13): application/file/window/command control, the shared Action Engine, permission/confirmation, audit/recovery, and workflow definition/execution/integration/hardening/freeze. Corresponds to Part 4's Phase 4.1 (Device Control) and Phase 4.2 (Workflow Engine).
- **Part B — Scheduler & Internet Agent** (sprints 4.14–4.20 below, fully specified 2026-07-31 — see the "Level 4 Part B breakdown changes" note above): calendar/deadlines, reminders, search/research, summarization/validation, plus their own integration/hardening/freeze sprints. Corresponds to Part 4's Phase 4.3 (Scheduler) and Phase 4.4 (Internet Agent). Not yet implemented.

**`v0.4` ("Complete productivity assistant," per [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md)) is not redefined by this split and is not tagged until both parts freeze** — see `sprint_4_13.md`'s own Purpose section. This mirrors, at the Level-splitting scale, the same "ship a real, verified increment without silently redefining what the release means" discipline `v0.2.0`'s deferred tag (Sprint 2.14) already established at the single-criterion scale.

Within Part A, six deviations from the original roadmap-granularity plan below, each explained in full in the affected sprint files, not just here:

1. **A new sprint, Action Engine Foundation, inserted as 4.1** — the shared `ActionRequest`/`ActionResult`/`ActionExecutor`/`ActionRegistry` contract every executor is built against, plus a real (if deliberately thin) Security Layer stub, acting directly on this file's own prior Recommendation ("Consider a thin `security/` stub... as early as Sprint 4.1"). This shifts the original `4.1 Application Control` to `4.2`, renamed `Application Manager`. See [sprint_4_1.md](sprint_4_1.md)'s Engineering Rationale.
2. **A new sprint, Command Execution Engine, inserted as 4.5** — approved system command/subprocess execution, named explicitly by this Sprint Book's own commissioning instructions ("Executing approved system commands") but absent from the original roadmap-granularity plan entirely. See [sprint_4_5.md](sprint_4_5.md)'s Engineering Rationale.
3. **The original `4.4 System Monitoring & Resource Protection (full)` is narrowed and renamed `System Monitoring & Resource Protection (Action-Aware)` (now 4.6)** — scoped specifically to gating Action Engine dispatch under critical resource pressure, not the larger, cross-cutting "throttle every subsystem's background work" concern the original "(full)" parenthetical implied, which reaches outside this Sprint Book's own mandate. See [sprint_4_6.md](sprint_4_6.md)'s Engineering Rationale.
4. **The original `4.7 Large-Workflow Confirmation Gate` is absorbed into a new, broader sprint, Permission & Confirmation System (now 4.7)** — a single general risk-classification/confirmation engine covering every executor's individual actions AND whole-workflow gating, rather than a workflow-only gate built separately from (and before) a general one would ever be needed. See [sprint_4_7.md](sprint_4_7.md)'s Engineering Rationale.
5. **A new sprint, Action Logging & Recovery, inserted as 4.8** — persistent audit trail and reversal/retry for executed actions, named explicitly by this Sprint Book's own commissioning instructions ("Logging executed actions... Recovering gracefully from failed actions") but absent from the original roadmap-granularity plan entirely. See [sprint_4_8.md](sprint_4_8.md)'s Engineering Rationale.
6. **Three sprints added (4.11–4.13): Workflow & Device Control Integration, Error Handling & Recovery Hardening, and Integration Testing & Level Freeze (Part A)** — mirroring the exact precedent both Level 2 and Level 3 already set for themselves when each went from roadmap-granularity to full detail. Level 4 Part A's integration surface is the first in this project with real, occasionally destructive effects on the machine running it, so it earns the same dedicated wiring/hardening/freeze treatment, with additional real-machine-safety discipline named explicitly in [sprint_4_11.md](sprint_4_11.md) and [sprint_4_13.md](sprint_4_13.md).

The original roadmap's `4.2 File & Folder Operations` (now 4.3), `4.3 Window Management` (now 4.4), `4.5 Workflow Builder` (now 4.9), and `4.6 Workflow Executor` (now 4.10) are unchanged in name and scope, renumbered only by the insertions above.

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

See the "Level 4 breakdown changes (2026-07-20)" note above for why this table is split into two Sprint Books, and the "Level 4 Part B breakdown changes (2026-07-31)" note for Part B's own expansion — both parts are now fully specified; neither is implemented.

### Part A — Device Control & Workflow Automation (fully specified 2026-07-20)

| Sprint | Name                                                    | Phase       | Depends On              | Complexity  | Detail                              |
| ------ | -------------------------------------------------------- | ----------- | ------------------------ | ----------- | ------------------------------------ |
| 4.1    | Action Engine Foundation                                  | 4.1         | 1.2, 1.5, 3.10, 3.11      | Medium      | [sprint_4_1.md](sprint_4_1.md) — **Complete** |
| 4.2    | Application Manager                                       | 4.1         | 4.1                       | Medium      | [sprint_4_2.md](sprint_4_2.md) — **Complete** |
| 4.3    | File & Folder Operations                                  | 4.1         | 4.1                       | Medium      | [sprint_4_3.md](sprint_4_3.md) — **Complete** |
| 4.4    | Window Management                                         | 4.1         | 4.1 (soft: 4.2)           | Low–Medium  | [sprint_4_4.md](sprint_4_4.md) — **Complete** |
| 4.5    | Command Execution Engine                                  | 4.1         | 4.1                       | Medium      | [sprint_4_5.md](sprint_4_5.md) — **Complete** |
| 4.6    | System Monitoring & Resource Protection (Action-Aware)    | 4.1         | 4.1, 1.4, 3.10            | Medium      | [sprint_4_6.md](sprint_4_6.md) — **Complete** |
| 4.7    | Permission & Confirmation System                          | 4.1/4.2     | 4.1–4.6, 3.11             | High        | [sprint_4_7.md](sprint_4_7.md) — **Complete** |
| 4.8    | Action Logging & Recovery                                  | 4.1/4.2     | 4.1, 4.2, 4.3, 4.6, 4.7   | Medium      | [sprint_4_8.md](sprint_4_8.md) — **Complete** |
| 4.9    | Workflow Builder                                           | 4.2         | 4.1, 3.11                 | Medium      | [sprint_4_9.md](sprint_4_9.md) — **Complete** |
| 4.10   | Workflow Executor                                          | 4.2         | 4.1, 4.7, 4.8, 4.9        | Medium–High | [sprint_4_10.md](sprint_4_10.md) — **Complete** |
| 4.11   | Workflow & Device Control Integration                      | integration | 4.1–4.10, 2.12, 3.12      | High        | [sprint_4_11.md](sprint_4_11.md) — **Complete** |
| 4.12   | Error Handling & Recovery Hardening                        | reliability | 4.11                      | Medium      | [sprint_4_12.md](sprint_4_12.md) — **Complete** |
| 4.13   | Integration Testing & Level Freeze (Part A)                | level gate  | 4.12                      | Medium–High | [sprint_4_13.md](sprint_4_13.md) — **Complete** |

### Part B — Scheduler & Internet Agent (fully specified 2026-07-31)

Renumbered continuation of the original roadmap's `4.8`–`4.11` entries, plus three new integration/hardening/freeze sprints, following Part A's own precedent — the same "one dedicated wiring/hardening/freeze sprint set" practice every Level's own expansion has now used. See the "Level 4 Part B breakdown changes (2026-07-31)" note above for the two real design decisions made while expanding this table to full detail — no sprint here was renamed, renumbered, or inserted against the original roadmap-granularity plan.

| Sprint | Name                                            | Phase       | Depends On       | Complexity  | Detail                              |
| ------ | ------------------------------------------------ | ----------- | ----------------- | ----------- | ------------------------------------ |
| 4.14   | Calendar & Deadlines Store                        | 4.3         | 3.1                | Medium      | [sprint_4_14.md](sprint_4_14.md) — **Complete** |
| 4.15   | Reminder Engine (delay/reschedule/postpone)      | 4.3         | 4.14, 3.10         | Medium–High | [sprint_4_15.md](sprint_4_15.md) — **Complete** |
| 4.16   | Search & Research                                 | 4.4         | 3.11               | Medium      | [sprint_4_16.md](sprint_4_16.md) — **Complete** |
| 4.17   | Summarization & Source Validation                 | 4.4         | 4.16               | Medium–High | [sprint_4_17.md](sprint_4_17.md) — **Complete** |
| 4.18   | Scheduler & Internet Agent Integration            | integration | 4.14–4.17, 4.11    | High        | [sprint_4_18.md](sprint_4_18.md) — **Complete** |
| 4.19   | Error Handling & Recovery Hardening (Part B)      | reliability | 4.18               | Medium      | [sprint_4_19.md](sprint_4_19.md) — **Complete** |
| 4.20   | Integration Testing & Level Freeze (Part B)       | level gate  | 4.19               | Medium–High | [sprint_4_20.md](sprint_4_20.md) — **Complete** |

## LEVEL 5 — Companion → Release v0.5

See the "Level 5 breakdown changes (2026-08-02)" note above for why this table is split into two Sprint Books, mirroring Level 4's own split — both Part A and Part B (below) are now fully specified, Part B as of 2026-08-04 (renumbered 5.17–5.26, continuing this Level's own sequence rather than restarting, the same convention Level 4 Part B's 4.14–4.20 already established, plus three added integration/hardening/freeze sprints — see the "Level 5 Part B breakdown changes" note above for the full reasoning and the old→new renumbering table).

### Part A — Emotional Intelligence & Presentation Layer (fully specified 2026-08-02)

| Sprint | Name                                                | Phase       | Depends On            | Complexity  | Detail                              |
| ------ | ---------------------------------------------------- | ----------- | ---------------------- | ----------- | ------------------------------------ |
| 5.1    | Emotion Detection Engine                             | 5.1         | 2.3, 2.8, 3.8           | Medium      | [sprint_5_1.md](sprint_5/sprint_5_1.md) — **Complete** |
| 5.2    | Emotional State Manager                              | 5.1         | 5.1                     | Medium      | [sprint_5_2.md](sprint_5/sprint_5_2.md) — **Complete** |
| 5.3    | Emotional Memory                                     | 5.1         | 5.2, 3.1–3.6            | Medium–High | [sprint_5_3.md](sprint_5/sprint_5_3.md) — **Complete** |
| 5.4    | Persona Behavioral Adaptation                        | 5.1         | 5.2, 2.9, 2.10, 3.11    | Medium      | [sprint_5_4.md](sprint_5/sprint_5_4.md) — **Complete** |
| 5.5    | Presentation State Engine                            | 5.5         | 5.2, 5.4                | Medium      | [sprint_5_5.md](sprint_5/sprint_5_5.md) — **Complete** |
| 5.6    | Presentation Layer Foundation & Renderer Interface   | 5.5         | 5.5, 2.11               | Medium–High | [sprint_5_6.md](sprint_5/sprint_5_6.md) — **Complete** |
| 5.7    | Jarvis Renderer                                      | 5.5         | 5.6, 1.6, 1.7           | High        | [sprint_5_7.md](sprint_5/sprint_5_7.md) — **Complete** |
| 5.8    | Minie Renderer & Avatar Renderer Interface           | 5.5         | 5.6                     | High        | [sprint_5_8.md](sprint_5/sprint_5_8.md) — **Complete** |
| 5.9    | Gesture Engine                                       | 5.5         | 5.6, 5.2                | Medium      | [sprint_5_9.md](sprint_5/sprint_5_9.md) — **Complete** |
| 5.10   | Persona Transition Engine                            | 5.5         | 5.7, 5.8, 2.11          | Medium–High | [sprint_5_10.md](sprint_5/sprint_5_10.md) — **Complete** |
| 5.11   | Voice Personality                                    | 5.5         | 5.5, 2.4, 2.9, 2.10     | Low–Medium  | [sprint_5_11.md](sprint_5/sprint_5_11.md) — **Complete** |
| 5.12   | Adaptive Workspace                                   | 5.5         | 5.7, 3.8                | Medium      | [sprint_5_12.md](sprint_5/sprint_5_12.md) — **Complete** |
| 5.13   | Companion Experience                                 | 5.5         | 5.3, 5.9, 3.1–3.4       | Medium      | [sprint_5_13.md](sprint_5/sprint_5_13.md) — **Complete** |
| 5.14   | Presentation Layer Integration                       | integration | 5.1–5.13, 4.11, 4.18    | High        | [sprint_5_14.md](sprint_5/sprint_5_14.md) — **Complete** |
| 5.15   | Error Handling & Recovery Hardening                  | reliability | 5.14                    | Medium      | [sprint_5_15.md](sprint_5/sprint_5_15.md) — **Complete** |
| 5.16   | Integration Testing & Level Freeze (Part A)          | level gate  | 5.15                    | Medium–High | [sprint_5_16.md](sprint_5/sprint_5_16.md) — **Complete** |

### Part B — Companion Intelligence (fully specified 2026-08-04; renumbered — see "Level 5 Part B breakdown changes" note above)

| Sprint | Name | Phase | Depends On | Complexity | Detail |
| --- | --- | --- | --- | --- | --- |
| 5.17 | Usage & Habit Tracking | 5.3 | 4.6, 4.2 | Medium | [sprint_5_17.md](sprint_5/sprint_5_17.md) |
| 5.18 | Wellness Triggers | 5.2 | 4.15, 5.2 | Medium | [sprint_5_18.md](sprint_5/sprint_5_18.md) |
| 5.19 | Wellness Escalation & Hard Limit | 5.2 | 5.18 | Medium | [sprint_5_19.md](sprint_5/sprint_5_19.md) |
| 5.20 | Analytics Dashboard Data | 5.3 | 5.17 | Low–Medium | [sprint_5_20.md](sprint_5/sprint_5_20.md) |
| 5.21 | Pattern Recognition | 5.4 | 3.2, 5.17, 5.20 | High | [sprint_5_21.md](sprint_5/sprint_5_21.md) |
| 5.22 | Adaptive Wellness | 5.2 | 5.19, 5.21 | Medium–High | [sprint_5_22.md](sprint_5/sprint_5_22.md) |
| 5.23 | Preference Learning & Recommendations | 5.4 | 5.21, 3.1 | Medium–High | [sprint_5_23.md](sprint_5/sprint_5_23.md) |
| 5.24 | Companion Intelligence Integration | integration | 5.17–5.23, 4.15, 4.18, 5.14 | High | [sprint_5_24.md](sprint_5/sprint_5_24.md) |
| 5.25 | Error Handling & Recovery Hardening, Part B (Companion Intelligence) | reliability | 5.24 | Medium | [sprint_5_25.md](sprint_5/sprint_5_25.md) |
| 5.26 | Integration Testing & Level Freeze (Part B) | level gate | 5.25 | Medium–High | [sprint_5_26.md](sprint_5/sprint_5_26.md) |

## LEVEL 6 — Stabilization → Release v1.0

| Sprint | Name                                               | Phase | Depends On | Complexity  |
| ------ | -------------------------------------------------- | ----- | ---------- | ----------- |
| 6.1    | Startup & Caching Optimization                     | 6.1   | all prior  | Medium      |
| 6.2    | Async Background Task Audit                        | 6.1   | all prior  | Medium      |
| 6.3    | Stress & Recovery Testing                          | 6.2   | all prior  | Medium–High |
| 6.4    | Resource Protection & Fail-Gracefully Verification | 6.2   | 1.4, 4.6   | Medium      |
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
| —       | 4.13         | Level 4 Part A complete (Device Control & Workflow Automation) — not a semver tag; see `sprint_4_13.md`'s Purpose and the "Level 4 breakdown changes" note above |
| 0.4     | 4.20         | Complete productivity assistant (gated on BOTH Part A/4.13 AND Part B/4.20 — corrected from the original `4.11`, which predates the Part A/B split) |
| —       | 5.16         | Level 5 Part A complete (Emotional Intelligence & Presentation Layer) — not a semver tag; see `sprint_5_16.md`'s Purpose and the "Level 5 breakdown changes" note above |
| 0.5     | 5.26         | Complete personal AI companion (gated on BOTH Part A/5.16 AND Part B/5.26 — corrected from the original `5.9`, which predates the Part A/B split, then from `5.23`, which predated Part B's own 2026-08-04 renumbering/expansion) |
| 1.0     | 6.8          | Official JARMINEI Release                             |

## Recommendations (not part of the official roadmap — flagged separately per the Development Guide's constraints)

- ~~Consider a thin `security/` stub (permission-check pass-through, no real enforcement) as early as Sprint 4.1, rather than deferring all Security Layer work to Level 6 — Device Control's "permission-sensitive operations always require user approval" (Part 2) needs _something_ to call even before Phase 6.3 builds it out fully.~~ **Resolved by [sprint_4_1.md](sprint_4_1.md)'s Engineering Rationale (2026-07-20)**: `security/permission_gate.py`'s `PermissionGate` ships in Sprint 4.1 as a real, callable, honestly-thin pass-through; [sprint_4_7.md](sprint_4_7.md) (Permission & Confirmation System) is what turns it into a full policy engine.
- ~~`database/` (SQLite layer) is first exercised in Sprint 3.1 but `config/` (Sprint 1.2) and `scheduler` (Sprint 4.8) also need persistent storage — worth deciding at Sprint 3.1 whether the SQLite access layer is generic enough to serve all three, to avoid three separate ad hoc DB-access implementations.~~ **Resolved by [sprint_3_1.md](sprint_3_1.md)'s Engineering Rationale (2026-07-18)**: `database/sqlite_client.py`'s `SqliteClient` (built in Sprint 2.7) is confirmed generic enough and reused as-is — Sprint 3.1 adds a new `memory_records` table to the same `sqlite_path` file via the same caller-owns-its-own-DDL pattern `ConversationSessionStore` already established. Sprints 4.9 (`workflows`/`workflow_steps` tables) and 4.8 (`action_audit_log` table) both followed the identical pattern (2026-07-20); Scheduler (now Part B, Sprint 4.14) should do the same when it arrives.
- ~~Level 3's `AuthorityEvaluator` (Sprint 3.11) ships with a structurally empty `approved_emergency_procedures` whitelist — by design, since no pre-approved emergency procedure exists until Device Control does. Sprint 4.1 should treat populating this whitelist as a deliberate, reviewed act, not an incidental side effect of building Device Control.~~ **Resolved by [sprint_4_7.md](sprint_4_7.md)'s Engineering Rationale/Architecture Notes (2026-07-20)**: whitelist population is this sprint's own explicit, reviewed responsibility, not folded into Application Manager (4.2) as originally anticipated — see that sprint's own reasoning for why it moved to 4.7 instead.
- **New (2026-07-20): `device_control/` hosts the shared Action Engine contract (`ActionRequest`/`ActionResult`/`ActionExecutor`/`ActionRegistry`, Sprint 4.1) even though `workflow/` also depends on it.** Part 3's fixed top-level folder list has no neutral "actions" home; Device Control is the more architecturally foundational of the two per Part 2's own Workflow Engine example (a workflow is a sequence of device-control-shaped steps), so `workflow/` depending on `device_control/`, never the reverse, is the natural fit. See [sprint_4_1.md](sprint_4_1.md)'s Engineering Rationale. Not a roadmap change, an architecture note worth surfacing for the next person who wonders why a "shared" contract lives in a named subsystem folder.
- **New (2026-07-20): the `authority/` top-level folder (Part 3's repository structure) has been an empty stub (`__init__.py` only) since Sprint 1.1, while the real Authority System (`AuthorityLevel`, `AuthorityEvaluator`, `DecisionTrace`) was actually built in `decision/authority.py` by Sprint 3.11.** This is real, silent drift from Part 3's own folder list, not something any Level 3 or Level 4 sprint file caught or explained — flagged here now rather than fixed unilaterally, since removing or repurposing an approved-architecture folder is exactly the kind of change this task's own instructions say to surface as a recommendation, not act on directly. Worth a real decision (retire the empty `authority/` folder, or move `decision/authority.py`'s contents into it) at a natural pause point — Level 4 Part A's freeze (Sprint 4.13) or Level 6's Documentation Pass (6.7) are both reasonable candidates, not urgent before either.
- **New (2026-07-20): `requirements.txt` needs `Send2Trash` added for Sprint 4.3's recycle-bin-based delete** — not previously named in Part 3's technology stack list (which predates Level 4's own detailed design). Same "corrected package/dependency naming, documented not hidden" treatment as `backlog/technical_debt.md` item 3's `coqui-tts` correction. See [sprint_4_3.md](sprint_4_3.md)'s Files to Modify.
- **New (2026-07-20): Sprint 4.6 (System Monitoring & Resource Protection, Action-Aware) deliberately narrowed the original roadmap's "(full)" scope to Action Engine dispatch-gating only** — the larger, cross-cutting "throttle every subsystem's background work" half of Part 2's Resource Protection Rule remains unbuilt. **Level 6's Sprint 6.4 (Resource Protection & Fail-Gracefully Verification) should treat closing that specific gap as part of its own scope**, not assume Sprint 4.6 already delivered it in full — see [sprint_4_6.md](sprint_4_6.md)'s Engineering Rationale for the exact boundary drawn. Flag for discussion before Sprint 6.4, not a change to the Level 6 roadmap itself.
