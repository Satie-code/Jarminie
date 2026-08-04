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

- [ ] Integration: real wellness announcement — forced Minie switch, spoken, `resume_previous()` restores the prior persona.
- [ ] Integration: real live-turn wellness query, routed and answered correctly.
- [ ] Regression: `SCHEDULED_REMINDER` announcement path unaffected by the rename/widen.
- [ ] Integration: `GENERAL_SUGGESTION` announcement — no persona switch.
- [ ] Integration: `TaskScheduler` jobs for `PatternRecognizer`/`RecommendationEngine` genuinely fire on their own configured cadence (a fast-interval test harness, mirroring `sprint_4_20.md`'s own `fast_scheduler_app_harness` precedent).
- [ ] Integration: Level 5 Part B construction failure — full graceful degrade, confirmed against every new dependent code path.
- [ ] Unit: `SwitchReason.WELLNESS`'s own priority-rank placement.
- [ ] Unit: `_determine_engine()`'s new `WELLNESS` branch, keyword-gated, narrow.

## Documentation Checklist

- [ ] `voice/pipeline.py`'s own module docstring updated with the new three-source dispatch diagram.
- [ ] `decision/authority.py`'s own module docstring: `WELLNESS` moved from "reserved" to "wired," with the same level of detail its `SCHEDULER`/`INTERNET_AGENT`/`EMOTION_SUPPORT` routing sections already have.
- [ ] `backlog/technical_debt.md` item 17 updated: `WELLNESS`/`GENERAL_SUGGESTION` marked resolved; `IMPORTANT_ALERT` explicitly reconfirmed as the one still-open source.
- [ ] `docs/STATUS.md` — Level 5 Part B's own integration narrative added; Phases 5.2/5.3/5.4 all move to `Complete`.

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
