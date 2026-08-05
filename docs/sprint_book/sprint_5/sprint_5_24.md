# Sprint 5.24 — Companion Intelligence Integration

## Sprint ID

5.24

## Sprint Name

Companion Intelligence Integration

## Purpose

Wire the entire Level 5 Part B graph (Sprints 5.17–5.23) into one real, running system — the same "one dedicated integration sprint per Level/Part" discipline this project has applied without exception since Level 2 (`sprint_2_12.md`, `sprint_3_12.md`, `sprint_4_11.md`/`sprint_4_18.md`, `sprint_5_14.md`). Gives `decision/priority_queue.py`'s `PriorityLevel.WELLNESS`/`GENERAL_SUGGESTION` and `decision/authority.py`'s `EngineSelection.WELLNESS` their first real producers/consumers, closing the last two open halves of `backlog/technical_debt.md` item 17.

## Engineering Rationale

New sprint, not present in the original roadmap-granularity plan (which allocated only the seven component sprints, 5.17–5.23 in this Sprint Book's own renumbering) — added for the identical reason `sprint_4_11.md`/`sprint_4_18.md`/`sprint_5_14.md` were each added at their own Level/Part boundary: real, live wiring earns its own dedicated sprint rather than being folded into whichever component sprint happens to finish last. See `docs/sprint_book/INDEX.md`'s "Level 5 Part B breakdown changes" note for why this Sprint Book adds three sprints (this one, 5.25, 5.26) beyond the original roadmap-granularity table's own seven.

**`voice/pipeline.py`'s `_check_and_announce_due_reminder()` is generalized, not duplicated** — that method's own docstring (Sprint 4.18) already named this exact moment: "a future, still-unhandled `PriorityItem` type... is never silently consumed by this method without understanding it." This sprint renames it `_check_and_announce_priority_item()` and widens its own `peeked.priority is not PriorityLevel.SCHEDULED_REMINDER` guard into a small dispatch table keyed by `PriorityLevel`, one branch per known payload shape (`ScheduledItem` unchanged; the two new ones below) — directly satisfying the Development Guide's own Step 1 ("If functionality already exists, extend or improve it instead of recreating it") rather than adding a second, parallel polling job that would itself violate `QuietModeController`'s own single-owner assumptions about when it is safe to interrupt.

**Wellness's own force-switch-to-Minie is a new, disclosed behavioral difference from every other proactive announcement this codebase has ever made**: Sprint 4.18's `SCHEDULED_REMINDER` announcements, and this sprint's own new `GENERAL_SUGGESTION` announcements, both speak through whichever persona is already active, unchanged. Wellness is different because Part 2's own text is explicit and singular here — "Owned exclusively by Minie" — stronger language than anything said about reminders or suggestions. `personas/persona_manager.py`'s `SwitchReason` enum (four members since Sprint 2.11: `CRITICAL_EMERGENCY`, `EXPLICIT_SELECTION`, `CONTEXT_DETECTION`, `DAILY_ROUTINE`) gains a fifth, `WELLNESS` — deliberately not repurposing the already-reserved `DAILY_ROUTINE` (still reserved for genuine time-of-day/routine-based switching, an unrelated future concern) — and a wellness announcement calls `persona_manager.select("minie", SwitchReason.WELLNESS)` immediately before speaking, then `persona_manager.resume_previous()` (real since Sprint 2.11, unchanged) immediately after, so a user working with Jarvis active is briefly, audibly handed to Minie for exactly one wellness prompt and handed back — never left on Minie by surprise. `SwitchReason.WELLNESS`'s own priority rank (per `personas/persona_manager.py`'s own priority-ordered switching table) is placed directly below `DAILY_ROUTINE`, above `CONTEXT_DETECTION`/`EXPLICIT_SELECTION` — a wellness prompt should not be silently pre-empted by an ordinary context-detected topic switch mid-announcement, but still yields to a genuine emergency.

**`EngineSelection.WELLNESS` gets a real, narrow live-turn branch, not only the proactive path** — mirroring `EMOTION_SUPPORT`'s own Sprint 5.4 precedent of a small, disclosed, narrowly-gated addition to `_determine_engine()`: an `INFORMATIONAL` or `EMOTIONAL_SUPPORT` intent whose raw transcript names wellness-shaped self-check language (a literal `"how am I doing"`/`"should I take a break"`/`"my screen time"` keyword — see the new `_WELLNESS_KEYWORDS` tuple, the same small, literal, non-NLU discipline every prior keyword-routing addition in this file already established) routes to `WELLNESS` instead of the default `CONVERSATIONAL_RESPONSE`/`EMOTION_SUPPORT`. `CommunicationPipeline._handle_wellness_turn()` answers it directly from `WellnessTracker`'s own current counters plus `AnalyticsDashboardService.daily_summary()` (5.20) — a live, honest status report, never a repeat of whatever the last proactive prompt happened to be.

## Objectives

- `main.py` gains `_construct_level5_part_b_modules()`/`_register_level5_part_b_modules()`, constructing and registering `UsageStore`, `UsageTracker`, `WellnessTracker` (with `WellnessEscalationManager`/`AdaptiveWellnessAdjuster` composed alongside), `PatternStore`, `PatternRecognizer`, plus the stateless `AnalyticsDashboardService`/`PreferenceLearner`/`RecommendationEngine` helpers.
- `voice/pipeline.py`'s proactive-announcement job generalized to a real, three-source dispatcher (`SCHEDULED_REMINDER`, `WELLNESS`, `GENERAL_SUGGESTION`).
- A real, live-turn `_handle_wellness_turn()`.
- Real recurring `TaskScheduler` cadences for `PatternRecognizer.run_detection_pass()` and `RecommendationEngine.generate_recommendations()`.
- `personas/persona_manager.py`'s `SwitchReason.WELLNESS`.

## Dependencies

5.17, 5.18, 5.19, 5.20, 5.21, 5.22, 5.23 (every component sprint this Part built), 4.15/4.18 (`TaskScheduler`'s own established registration/job-management precedent this sprint directly extends), 5.14 (`main.py`'s `_construct_level5_modules()`/`_register_level5_modules()` naming and null-fallback-on-construction-failure precedent, mirrored here for Part B).

## Files to Modify

- `main.py` — new `_construct_level5_part_b_modules()`/`_register_level5_part_b_modules()`, mirroring `_construct_level5_modules()`/`_register_level5_modules()`'s own shape including Sprint 5.15's null-fallback-on-failure discipline (a `_Level5PartBModules` dataclass with its own `available: bool` flag; a construction failure falls back to an all-`None`/inert set rather than crashing startup, the same reasoning that sprint's own scenario (e) already established for the whole of Level 5).
- `voice/pipeline.py` — `_check_and_announce_due_reminder()` renamed `_check_and_announce_priority_item()`, dispatch widened to `SCHEDULED_REMINDER`/`WELLNESS`/`GENERAL_SUGGESTION`; new `_handle_wellness_turn(trace: DecisionTrace) -> str`; constructor DI grows to accept `wellness_tracker`, `wellness_escalation_manager`, `dashboard_service`, `usage_tracker`, `pattern_recognizer`, `recommendation_engine` (all `| None` for the same graceful-fallback reason `_construct_level5_part_b_modules()` above needs it).
- `decision/authority.py` — `_determine_engine()` gains the new `_WELLNESS_KEYWORDS`-gated `WELLNESS` branch; `_ENGINE_DISPLAY_NAMES`/module docstring updated to move `WELLNESS` from "reserved" to "wired."
- `personas/persona_manager.py` — `SwitchReason.WELLNESS` added, inserted into the existing priority-rank table directly below `DAILY_ROUTINE`.
- `config/schema.py` — `SchedulerConfig` (or a new field on `LearningConfig`/`WellnessConfig`, resolved directly during implementation per whichever existing config section already owns the closest-related cadence — a genuine, small implementation-time judgment call, the same class of decision `sprint_4_14.md`'s own completion report already made for `max_lookahead_days`'s real enforcement point) gains `pattern_detection_interval_seconds`/`recommendation_generation_interval_seconds` (both defaulting to a daily-scale cadence — far longer than `poll_interval_seconds`, since neither needs to run often).

## Expected Classes

- `_Level5PartBModules` (a `main.py`-local dataclass, mirroring `_Level5Modules`) — every constructed Part B object plus `available: bool`.

## Expected Interfaces

None new.

## Expected Functions

- `_construct_level5_part_b_modules(config: AppConfig, sqlite_client: SqliteClient, task_scheduler: TaskScheduler, emotional_state_manager: EmotionalStateManager | None, memory_store: MemoryStore) -> _Level5PartBModules`
- `_register_level5_part_b_modules(core_manager: CoreManager, modules: _Level5PartBModules) -> None`
- `voice/pipeline.py`'s `_check_and_announce_priority_item()` — same `peek_next()`-before-`pop_next()` discipline Sprint 4.18 already established (a due item found while a session is `ACTIVE` stays queued, re-checked next poll), now branching on `peeked.priority`: `SCHEDULED_REMINDER` unchanged; `WELLNESS` → force-switch to Minie (`SwitchReason.WELLNESS`) → `quiet_mode_controller.activate(SCHEDULED_ALERT, announce_first=(prompt.message, "minie"))` → `persona_manager.resume_previous()` immediately after the announcement completes; `GENERAL_SUGGESTION` → announced through whichever persona is already active, unchanged persona, same as `SCHEDULED_REMINDER`. An unrecognized `PriorityLevel` (there is none today, but the dispatch table is exhaustive-by-construction so a future fifth source cannot be silently mishandled) logs a warning and leaves the item queued rather than popping and discarding it.
- `CommunicationPipeline._handle_wellness_turn(trace: DecisionTrace) -> str` — composes `WellnessTracker`'s own current per-trigger elapsed time plus `AnalyticsDashboardService.daily_summary(date.today())` into one honest, spoken status sentence; degrades to a plain "I don't have enough information about today yet" when Level 5 Part B modules are unavailable (the null-fallback case) or when today's `UsageStore` has no data at all — never a fabricated number.
- `PatternRecognizer.run_detection_pass()`/`RecommendationEngine.generate_recommendations()` — unchanged signatures (5.21/5.23), now given real `TaskScheduler.add_job()` callers at `pattern_detection_interval_seconds`/`recommendation_generation_interval_seconds`.

## Data Flow

```
main.py: _construct_level5_part_b_modules() → _register_level5_part_b_modules()
      ↓
TaskScheduler jobs registered:
  - UsageTracker._on_tick()                (sample_interval_seconds)
  - WellnessTracker._on_tick()             (idle_check_interval_seconds)
  - PatternRecognizer.run_detection_pass() (pattern_detection_interval_seconds)
  - RecommendationEngine.generate_recommendations() (recommendation_generation_interval_seconds)
  - CommunicationPipeline._check_and_announce_priority_item() (existing, widened)
      ↓
WellnessTracker.evaluate_triggers(escalation_manager, interval_overrides)
      ↓ (a real WellnessPrompt)
PriorityQueueManager.enqueue(PriorityLevel.WELLNESS, prompt)
      ↓ (next poll, if DORMANT)
_check_and_announce_priority_item()  →  force-switch to Minie  →  spoken  →  resume_previous()
      ↓
WellnessEscalationManager.register_prompt_shown()/.register_postponed()  (per real user response)

--- live-turn path ---
transcript ("how am I doing today?")
      ↓
IntentDetector → ContextAnalyzer → AuthorityEvaluator._determine_engine()  →  EngineSelection.WELLNESS
      ↓
CommunicationPipeline._handle_wellness_turn(trace)
      ↓
WellnessTracker current state + AnalyticsDashboardService.daily_summary()
      ↓
spoken reply
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — the two new interval fields, landed in whichever existing config section the implementer determines fits best (see Files to Modify note).
2. `main.py` — `_Level5PartBModules`, `_construct_level5_part_b_modules()`, `_register_level5_part_b_modules()`, wired into `main()` alongside the existing Level 5 (Part A) construction/registration calls.
3. `personas/persona_manager.py` — `SwitchReason.WELLNESS`, priority-table update, and its own dedicated unit test confirming rank placement.
4. `decision/authority.py` — `_WELLNESS_KEYWORDS`, the new `_determine_engine()` branch, docstring/`_ENGINE_DISPLAY_NAMES` updates.
5. `voice/pipeline.py` — the rename/widen of `_check_and_announce_due_reminder()` → `_check_and_announce_priority_item()`, `_handle_wellness_turn()`, constructor DI growth, real `TaskScheduler.add_job()` registrations for `PatternRecognizer`/`RecommendationEngine`.
6. Integration tests: a real end-to-end wellness announcement (forced switch, spoken, resumed) via the real object graph; a real live-turn wellness query; `SCHEDULED_REMINDER` announcements re-confirmed unaffected by the rename/widen (regression); a `GENERAL_SUGGESTION` announcement through the already-active persona (no switch); Level 5 Part B construction failure exercised directly, confirming the same graceful all-`None` fallback Sprint 5.15 already established for Part A.

## Architecture Notes

The rename `_check_and_announce_due_reminder()` → `_check_and_announce_priority_item()` is itself a disclosed, deliberate documentation-accuracy fix — the old name was already slightly misleading once `WELLNESS`/`GENERAL_SUGGESTION` became real, live sources, the same "correct a name once its own scope has genuinely grown" precedent this project applied when Sprint 4.1's insertion renamed the original `4.1 Application Control` to `4.2 Application Manager`.

The force-switch-then-resume choreography for `WELLNESS` deliberately does **not** invoke Sprint 5.10's full seven-phase `TransitionEngine` — a wellness announcement is a brief, single-utterance interruption, not a genuine change of who the user is talking to for the rest of the session (Sprint 4.18's `SCHEDULED_ALERT` announcements never invoked it either, for the identical reason); using the lighter `select()`/`resume_previous()` pair, unchanged since Sprint 2.11, keeps this sprint's own real behavioral surface area small and consistent with the one other proactive-announcement precedent already in the codebase.

## Integration Considerations

- This is this Part's own dedicated integration sprint — no further "component before integration" deferral remains after it for any of 5.17–5.23's own real capabilities.
- `IMPORTANT_ALERT` (`backlog/technical_debt.md` item 17's one still-genuinely-open source) is **not** addressed by this sprint — nothing in this Sprint Book names a periodic `ResourceMonitor.critical_alerts()` producer, and inventing one here would be scope creep beyond this Part's own named purpose (Companion Intelligence, not Resource Protection). Recorded here explicitly as still open, the same "don't overstate a partial resolution" discipline `sprint_3_14.md`/`sprint_4_18.md` both already modeled for this exact item.

## Potential Risks

- **A wellness announcement arriving mid-way through an already-in-progress persona-switch choreography (Sprint 5.10's `TransitionEngine`) is a genuinely new interleaving this codebase has not had to reason about before** — `_check_and_announce_priority_item()` only fires while `QuietModeController.current_mode() is OperatingMode.DORMANT` (unchanged gating from Sprint 4.18), and a `TransitionEngine` choreography in progress implies an active, non-dormant interaction, so this should be structurally unreachable — verified directly by a dedicated test, not merely assumed safe by inspection, mirroring `sprint_5_14.md`'s own "verified directly, not assumed" discipline for its own real concurrency question.
- **`_handle_wellness_turn()`'s own honesty is bounded by how much real data exists** — a fresh install with an empty `UsageStore` will, correctly, report having nothing to say yet, which could itself read as an unhelpful/broken reply on first run; disclosed here as an acceptable, honest consequence rather than a defect to paper over with a fabricated placeholder statistic.
- **The null-fallback path (Level 5 Part B construction failure) means `_handle_wellness_turn()`/the whole proactive-wellness-announcement path can be silently inert on a broken machine**, the same disclosed trade-off Sprint 5.15's own scenario (e) already accepted for the whole of Level 5 — a real, named risk, not a new one this sprint introduces.

## Acceptance Criteria

- A real, scripted wellness trigger (an artificially-elapsed `WellnessTracker` state) produces a real spoken announcement through Minie's own voice, with whatever persona was active before correctly restored immediately after.
- A real live turn asking a wellness-shaped question is routed to `EngineSelection.WELLNESS` and answered honestly from real `WellnessTracker`/`AnalyticsDashboardService` state.
- `SCHEDULED_REMINDER` announcements continue to work exactly as before this sprint (regression-tested against Sprint 4.18's own existing test expectations).
- `PatternRecognizer`/`RecommendationEngine` each receive a real, periodic (not just startup-once) `TaskScheduler` cadence.
- A simulated Level 5 Part B construction failure degrades every dependent code path to an honest, inert no-op — never a crash, never a silent false success.

## Testing Checklist

- [x] Integration: real wellness announcement — forced Minie switch, spoken, `resume_previous()` restores the prior persona.
- [x] Integration: real live-turn wellness query, routed and answered correctly.
- [x] Regression: `SCHEDULED_REMINDER` announcement path unaffected by the rename/widen.
- [x] Integration: `GENERAL_SUGGESTION` announcement — no persona switch.
- [x] Integration: `TaskScheduler` jobs for `PatternRecognizer`/`RecommendationEngine` genuinely fire on their own configured cadence (a fast-interval test harness, mirroring `sprint_4_20.md`'s own `fast_scheduler_app_harness` precedent).
- [x] Integration: Level 5 Part B construction failure — full graceful degrade, confirmed against every new dependent code path.
- [x] Unit: `SwitchReason.WELLNESS`'s own priority-rank placement.
- [x] Unit: `_determine_engine()`'s new `WELLNESS` branch, keyword-gated, narrow.

## Documentation Checklist

- [x] `voice/pipeline.py`'s own module docstring updated with the new three-source dispatch diagram.
- [x] `decision/authority.py`'s own module docstring: `WELLNESS` moved from "reserved" to "wired," with the same level of detail its `SCHEDULER`/`INTERNET_AGENT`/`EMOTION_SUPPORT` routing sections already have.
- [x] `backlog/technical_debt.md` item 17 updated: `WELLNESS`/`GENERAL_SUGGESTION` marked resolved; `IMPORTANT_ALERT` explicitly reconfirmed as the one still-open source.
- [x] `docs/STATUS.md` — Level 5 Part B's own integration narrative added; Phases 5.2/5.3/5.4 all move to `Complete`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

High.

## Estimated Development Time

2.5–3 days.

## Risks

See Potential Risks above.

## Next Sprint

5.25 — Error Handling & Recovery Hardening, Part B (Companion Intelligence).

## Future Considerations

- A settings-UI surface for the whole of Companion Intelligence (Wellness thresholds, Analytics visibility/opt-out, Learning Engine pattern review/dismissal) — no sprint anywhere in this Sprint Book builds one; a genuine, disclosed gap for Level 6 or a later dedicated sprint.
- `IMPORTANT_ALERT`'s own still-open periodic-producer gap — explicitly out of this sprint's own scope, named rather than silently left implicit.
- Real postponement-detection from a user's own spoken response to a wellness announcement (`WellnessEscalationManager.register_postponed()` remains implemented, tested in isolation since Sprint 5.19, but still has no live caller) — this sprint wires `register_prompt_shown()` for real (the announcement genuinely happened), but nothing in this Sprint Book's own scope analyzes the user's NEXT utterance for a "not now"/"later" postponement signal; disclosed here rather than guessed at with an unreliable heuristic.
- Recommendation deduplication/dismissal tracking beyond this sprint's own in-memory `_enqueued_recommendation_pattern_ids` set (Sprint 5.23's own Future Consideration) — a process restart currently re-surfaces every already-shown recommendation once, the same "in-memory-only, no persistence" simplification `ReminderEngine._enqueued_item_ids` already established as this project's own precedent for this exact class of dedup state.

## Sprint Completion Report (2026-08-05)

Implemented directly ("continue with the implementation of sprint 5.24"), in a new session continuing from where item 68 of this project's own auto-memory left off — Sprints 5.17–5.23 were already implemented and, per `git log`, had since been committed by the user themselves (a single commit, `4871453`, bundling all seven sprints' worth of `analytics/`/`wellness/`/`learning/` code together, plus a separate documentation-only commit `259733f` for the Sprint Book files) — confirmed via `git log`/`git show --stat` before starting, not assumed from memory alone, since memory had correctly flagged its own prior "all seven remain uncommitted" note as certain to be stale by now.

**Six production files changed**: `config/schema.py`/`config/defaults.yaml` (two new `LearningConfig` fields), `personas/persona_manager.py` (`SwitchReason.WELLNESS` plus a disclosed `DAILY_ROUTINE` reordering), `decision/authority.py` (`_WELLNESS_KEYWORDS`-gated `WELLNESS` routing, `_INFERRED_FUTURE_ENGINE` removed), `voice/pipeline.py` (the renamed/widened dispatcher, `_handle_wellness_turn()`, two new TaskScheduler jobs, eight new constructor parameters), `main.py` (`_Level5PartBModules`/`_construct_level5_part_b_modules()`/`_null_level5_part_b_modules()`/`_register_level5_part_b_modules()`, wired into `main()`).

**A real, load-bearing design decision not spelled out by this sprint's own literal text, resolved and disclosed directly in code**: `personas/persona_manager.py`'s own Architecture Notes text ("`WELLNESS` placed directly below `DAILY_ROUTINE`, above `CONTEXT_DETECTION`/`EXPLICIT_SELECTION`") is genuinely self-contradictory under the pre-5.24 declaration order — `DAILY_ROUTINE` already ranked below both of those before this sprint, so "directly below DAILY_ROUTINE" and "above CONTEXT_DETECTION/EXPLICIT_SELECTION" cannot simultaneously hold without moving `DAILY_ROUTINE` too. Resolved by reordering `DAILY_ROUTINE` up alongside the new `WELLNESS` member — the only reading under which the sprint's own Acceptance Criteria (a *reliable* forced switch to Minie) is actually achievable: with `WELLNESS` ranked below `EXPLICIT_SELECTION`/`CONTEXT_DETECTION` (the literal-Files-to-Modify-only reading), any stale `_active_reason` left over from an earlier, unrelated conversation would refuse the wellness switch outright via `select()`'s own priority-refusal rule, since `PersonaManager` never resets `_active_reason` between sessions. Zero production risk — `DAILY_ROUTINE` has never had a live caller anywhere in this codebase (confirmed via `grep` before touching the enum), so no existing tested behavior depends on its prior position; six new unit tests in `test_persona_manager.py` cover the full override lattice (`WELLNESS` over `EXPLICIT_SELECTION`/`CONTEXT_DETECTION`; `DAILY_ROUTINE`/`CRITICAL_EMERGENCY` over `WELLNESS`; `EXPLICIT_SELECTION` cannot override an active `WELLNESS`).

**A second real gap this sprint's own Files to Modify didn't explicitly resolve, found and closed directly**: the Data Flow diagram names `WellnessTracker.evaluate_triggers() → PriorityQueueManager.enqueue()` as a real step, but `wellness_tracker.py` has no `PriorityQueueManager` dependency of its own and sits outside this sprint's own Files to Modify — the same is true of `learning/recommendation.py`'s `RecommendationEngine` for `GENERAL_SUGGESTION`. Resolved by giving `CommunicationPipeline` two new TaskScheduler jobs of its own (`_maybe_enqueue_wellness_prompt()` on `WellnessConfig.idle_check_interval_seconds`, `_generate_and_enqueue_recommendations()` on the two new `LearningConfig` interval fields) — the only place in the whole graph that legitimately owns this step for either source without touching a file outside this sprint's own declared scope. Both are deduplicated (per still-crossed trigger type for wellness — cleared once actually announced; per `based_on_pattern_id` for recommendations, since `generate_recommendations()` is deliberately stateless/idempotent and would otherwise re-enqueue the same recommendations every single cycle), disclosed in each method's own docstring rather than silently added.

**A third, smaller disclosed narrowing**: `_handle_wellness_turn()`'s own Expected Functions text describes a richer "per-trigger elapsed time" readout, but `WellnessTracker` exposes no public accessor for its own private `_continuous_active_seconds`/`_daily_active_seconds` counters, and `wellness_tracker.py` is outside this sprint's own Files to Modify. Composed instead from what IS public — `AnalyticsDashboardService.daily_summary()`'s own real total active time, plus whatever `evaluate_triggers()` itself already returns (a currently-due prompt, if any) — an honest, narrower implementation rather than reaching into a collaborator's private state from outside its own class.

**`_construct_level5_part_b_modules()`'s own signature deviates from the sprint file's literal `sqlite_client: SqliteClient` parameter** — every other `_construct_level*_modules()` function in `main.py` (Level 3/4/4B) instead builds a fresh `SqliteClient(database_config.sqlite_path)` per store, never sharing one instance across store classes even against the identical file; followed that repeatedly-reinforced, load-bearing convention instead, disclosed in the function's own docstring.

**`_Level5PartBModules`'s own null-fallback shape is deliberately simpler than Level 5 Part A's** — Sprint 5.15 scenario (e) made every Part A field always-real-but-inert on a construction failure; here, since `CommunicationPipeline`'s own six new constructor parameters are already typed `X | None` per this sprint's own literal text, the null fallback (`_null_level5_part_b_modules()`) just threads literal `None` through, and every dependent code path (`start()`'s three new job registrations, `_maybe_enqueue_wellness_prompt()`, `_generate_and_enqueue_recommendations()`, `_handle_wellness_turn()`) already has its own None-guard — a real, disclosed, considered supersession of Part A's own pattern, not an oversight.

**Testing.** 10 new integration tests (`tests/integration/test_companion_intelligence_integration.py`) covering all six of this sprint's own Acceptance Criteria, plus two supporting scenarios (escalation-manager `register_prompt_shown()` wiring; a `WellnessTriggerType`-specific dedup check) — `fast_scheduler_harness` (Sprint 4.18's own existing fixture, unmodified) sufficed for the WELLNESS/GENERAL_SUGGESTION announcement tests via direct enqueue (mirroring that file's own `_due_item()` precedent, bypassing real detection to isolate the consume/announce half); a new `fast_level5_part_b_harness` fixture (fast `WellnessConfig`/`LearningConfig` intervals alongside the existing fast `SchedulerConfig`) was needed for the one test proving `PatternRecognizer`/`RecommendationEngine`'s own real recurring cadence; a new `pipeline_harness_without_level5_part_b` fixture (`CommunicationPipeline` constructed with all six Level 5 Part B parameters forced to `None`, real objects still built/started underneath for harness simplicity — disclosed in its own docstring as a pragmatic divergence from main.py's true null-fallback, which skips their construction entirely) covered the graceful-degrade scenario. Two real bugs caught and fixed while writing these tests, not left for a hypothetical future run: a two-sample `AppFocusSample` pair placed `session_gap_seconds` apart (300s vs. the real 180s default) split into two zero-duration sessions instead of merging into one real-duration session, silently producing the exact "not enough information" fallback the test wasn't supposed to exercise; a manual polling loop against `ReminderEngine`'s own real (slow, unconfigured-fast) detection cadence in the null-fallback SCHEDULED_REMINDER regression test never actually got the item enqueued at all — both fixed by, respectively, shortening the gap and enqueueing directly (matching `_due_item()`'s own established "construct directly, bypass detection" precedent) rather than waiting on a poll that would never fire within the test's own patience.

11 new unit tests: 6 in `test_persona_manager.py` (the full `WELLNESS` priority-rank override lattice), 5 in `test_authority.py` (`_mentions_wellness_keywords()`-gated routing, including the authority-independent case and the negative ACTION_REQUEST/no-keyword cases) — plus one PRE-EXISTING test (`test_emotional_support_never_actually_selects_wellness`) found genuinely broken by this sprint's own removal of `_INFERRED_FUTURE_ENGINE`, not silently left failing: its own name and assertion ("never actually selects wellness," a reasoning_text naming "Wellness Engine") were literally true before this sprint and literally false after — renamed and rewritten to assert the real, narrower remaining gap (`EMOTIONAL_SUPPORT` at `INFORM` authority with no wellness keyword still falls back to `CONVERSATIONAL_RESPONSE`, now with no special reasoning-text sentence, since the mechanism that produced one no longer exists).

**A genuinely large ripple effect, found by actually running the full suite, not assumed from the diff alone**: `CommunicationPipeline`'s constructor signature change (eight new parameters) broke `tests/unit/voice/test_pipeline.py`'s own fixture at collection time — 52 setup ERRORs (not failures) across the whole file. Fixed by extending the `collaborators()` fixture with seven new `MagicMock` collaborators plus real `WellnessConfig()`/`LearningConfig()` instances (mirroring `scheduler_config`/`memory_config`'s own established "real plain dataclass, not mocked" precedent), extracting the `pipeline()` fixture's own constructor call into a reusable `_build_pipeline()` helper (needed by several new None-dependency tests), and a bulk rename of every `_check_and_announce_due_reminder`/`"proactive_reminder_announcement"` reference to its new name — then extended, not just patched, with 18 new dispatch-level unit tests (the widened three-source announcement dispatch including the forced-switch/refused-switch/no-switch cases, `_maybe_enqueue_wellness_prompt()`'s own dedup/None-guard/adaptive-override behavior, `_generate_and_enqueue_recommendations()`'s own dedup/None-guard behavior, `_handle_wellness_turn()`'s own four reply shapes, and the live `EngineSelection.WELLNESS` turn-routing dispatch) — matching this file's own already-established rigor (an exhaustive adversarial-sweep test for the OLD single-source method already existed; the widened version deserved the same standard, not a mechanical patch-and-move-on). Also updated 5 pre-existing `tests/system/` acceptance test files' own hardcoded `module_states()` exact-set assertions (`test_level2/3/4_part_a/4_part_b/5_part_a_acceptance.py`) for the five new Level 5 Part B `CoreManager` registrations — found the same way Sprint 4.11 first hit this exact mechanical consequence, by running the affected test and reading its own diff output, not by grepping for the pattern preemptively (the grep sweep done at the start of this sprint for "module_states" returned no truncated-early false negative on inspection, but did require checking all 13 files it initially matched to separate the 5 real full-graph exact-set assertions from 8 unrelated/narrower uses).

**Full-suite verification, genuinely eventful across two runs**: run 1 (before the `test_pipeline.py` fix) surfaced the 52 setup errors above plus the already-documented `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` real-Ollama-nondeterminism flake (1758 passing). Run 2 (after the fix, the authoritative one) — 1828 passing, 4 skipped, 1 deselected, 2 failures: the same real-Ollama flake (unchanged, in a file this sprint never touches) and `test_full_level2_acceptance_scripted_conversation`, which did NOT fail in run 1 — investigated per this project's own established technique rather than assumed: 5 further standalone re-runs of that single test produced 4 passes and 1 failure, the classic intermittent (not deterministically-reproducing) signature this project has documented repeatedly since Sprint 3.13 as the `wait_for_dormant` host-load flake class; `voice/quiet_mode.py`/`voice/session_manager.py` (the actual files that test's own failure trace touches) are both untouched by this sprint, and nothing in that test's own dependency chain reaches `wellness/`/`analytics/`/`learning/`. `ruff check .` clean across the whole repository (both the six production files and the eight test files this sprint touched, plus the one new test file).

`backlog/technical_debt.md` item 17 updated (`WELLNESS`/`GENERAL_SUGGESTION` marked resolved with the real classes/mechanisms named; `IMPORTANT_ALERT` explicitly reconfirmed as the one still-open source). `docs/STATUS.md` (Level 5 Part B's own Sprint 5.24 integration narrative added; Phases 5.2 Wellness Engine/5.3 Analytics/5.4 Learning Engine rows all updated to reflect their own real live callers, Analytics moving to `Complete` for the first time) and `docs/sprint_book/INDEX.md` (5.24 row → `Complete`) both updated.

**This closes Level 5 Part B's own component-and-integration work through Sprint 5.24 (8 of 10 Part B sprints now implemented) — only `IMPORTANT_ALERT` remains a genuinely open Priority Queue source anywhere in the codebase, named explicitly rather than overstated as resolved. Sprint 5.25 (Error Handling & Recovery Hardening, Part B) is next.**
