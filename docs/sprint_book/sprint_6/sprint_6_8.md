# Sprint 6.8 — Proactive Assistant

## Sprint ID

6.8

## Sprint Name

Proactive Assistant

## Purpose

Build the sprint the brief itself frames as the whole Part's real test of restraint: safe proactive behavior — upcoming deadline, forgotten reminder, battery critical, long coding session, missed meal, project inactivity — that "never interrupts unnecessarily" and "respects Quiet Mode." This sprint is placed deliberately late in the build order (after Context Engine, Decision Engine v2, Knowledge Graph, and Learning Engine v2) because a safe proactive trigger needs all four: situational grounding, risk/confirmation gating, project-activity history, and habit-based thresholds.

## Engineering Rationale

**Reuses, and finally completes, machinery this codebase has been carrying reserved-but-unfinished since Level 3.** `decision/priority_queue.py`'s `PriorityLevel.IMPORTANT_ALERT` has been declared since Sprint 3.10; `backlog/technical_debt.md` item 17 has tracked, across four separate resolutions (Sprints 4.6, 4.15, 4.18, 5.24), that `IMPORTANT_ALERT` is the *one* `PriorityLevel` source still without a real periodic producer — every other source (`SCHEDULED_REMINDER`, `WELLNESS`, `GENERAL_SUGGESTION`) already has one. **`ProactiveAssistant` is `IMPORTANT_ALERT`'s first real producer**, closing that item's last open gap. It also produces `GENERAL_SUGGESTION` for its own softer triggers (long session, missed meal), reusing that existing `PriorityLevel` rather than adding a new one — `PriorityLevel`'s docstring already states it mirrors "Part 2's own numbered list literally" (five fixed members), so this sprint does not widen it.

**Announcement reuses the existing, already-generalized dispatch mechanism, not a parallel one.** `voice/pipeline.py`'s `_check_and_announce_priority_item()` (generalized from `_check_and_announce_due_reminder()` at Sprint 5.24 specifically anticipating "a future, still-unhandled `PriorityItem` type") is where `ProactiveAssistant`'s own enqueued items get announced — Sprint 6.13 (Integration) is what wires the connection; this sprint builds the producer only, following the same "component sprint ships untethered" precedent every other Sprint 6 component has used.

**A real, deliberate safety design**: every trigger this sprint proposes passes through Sprint 6.5's `DecisionEngineV2.requires_confirmation()`-equivalent judgment before ever reaching the announcement queue — not because announcing a suggestion is itself a risky *action*, but because Level 6's own "Never interrupt unnecessarily" design principle deserves the same rigor as a risky action would get. Concretely: a trigger is gated by (a) `QuietModeController`'s existing quiet-mode/operating-mode state (untouched, reused exactly as `WellnessTracker`/`ReminderEngine` already are), and (b) a per-trigger-type cooldown (new to this sprint) preventing the same trigger from re-firing every poll — mirroring `CommunicationPipeline._maybe_enqueue_wellness_prompt()`'s own established in-memory deduplication precedent from Sprint 5.24.

## Objectives

- `ProactiveTriggerType` — the six named triggers.
- `ProactiveAssistant(ManagedModule)`: a `TaskScheduler`-driven periodic evaluator producing `PriorityItem`s from real system/context/knowledge/learning signals.
- `ProactiveConfig` (new `config/schema.py` section) — one threshold per trigger.

## Dependencies

6.3 (`ContextEngine`/`WorkingContext`), 6.5 (`DecisionEngineV2`), 6.6 (`KnowledgeGraphStore`, for project-inactivity), 6.7 (`PatternRecognizer`'s widened detectors, for habit-based long-session/missed-meal framing), 4.15 (`TaskScheduler`), 3.10 (`PriorityQueueManager`/`PriorityLevel`), existing `wellness/wellness_tracker.py` (the "missed meal"/"long session" trigger shapes closely mirror `WellnessTriggerType`'s own existing idle/continuous-activity triggers — reused as a design precedent, not as a dependency; Wellness and Proactive Assistant remain sibling engines, exactly as Wellness and Analytics were designed to stay siblings at Level 5 Part B).

## Files to Create

- `proactive/proactive_model.py` — `ProactiveTriggerType` (Enum: `UPCOMING_DEADLINE`, `FORGOTTEN_REMINDER`, `BATTERY_CRITICAL`, `LONG_SESSION`, `MISSED_MEAL`, `PROJECT_INACTIVITY`), `ProactivePrompt` (dataclass).
- `proactive/proactive_assistant.py` — `ProactiveAssistant`.
- `tests/unit/proactive/test_proactive_model.py`
- `tests/unit/proactive/test_proactive_assistant.py`

## Files to Modify

- `config/schema.py` — new `ProactiveConfig` dataclass: `evaluation_interval_seconds: float = 300.0` (a coarser cadence than Wellness's own idle-check interval — proactive triggers are, by design, lower-frequency/higher-deliberation than wellness prompts), `deadline_warning_hours: float = 24.0`, `battery_critical_percent: float = 15.0` (mirrors `core/resource_monitor.py`'s own existing critical-threshold shape), `long_session_hours: float = 3.0`, `missed_meal_window_start_hour: int = 12`/`missed_meal_window_end_hour: int = 14` (a configurable lunch window, not a hardcoded assumption — a dinner-window pair is a plausible future addition, not built without a named second window in this brief), `project_inactivity_days: int = 7`, `trigger_cooldown_seconds: float = 3600.0` (a fired trigger will not re-fire for this long, regardless of whether its own condition is still true — the deduplication mechanism named in Engineering Rationale).
- `config/defaults.yaml` — matching `proactive:` section.
- `config/loader.py` — `_SECTION_SCHEMAS` entry.

## Expected Classes

- `ProactiveTriggerType` (Enum) — the six brief-named triggers, exactly as listed.
- `ProactivePrompt` (dataclass) — `trigger_type: ProactiveTriggerType`, `message: str`, `priority: PriorityLevel` (existing type — `IMPORTANT_ALERT` for `UPCOMING_DEADLINE`/`BATTERY_CRITICAL`/`FORGOTTEN_REMINDER`, `GENERAL_SUGGESTION` for `LONG_SESSION`/`MISSED_MEAL`/`PROJECT_INACTIVITY` — a deliberate severity split mirroring how Wellness already treats a hard trigger differently from a soft one), `subject_entity_id: str | None` (a `knowledge/` `Entity` reference, when the trigger concerns one — e.g. `PROJECT_INACTIVITY`), `evaluated_at: datetime`.
- `ProactiveAssistant(ManagedModule)` — constructor DI: `(task_scheduler: TaskScheduler, priority_queue_manager: PriorityQueueManager, context_engine: ContextEngine, decision_engine_v2: DecisionEngineV2, knowledge_graph_store: KnowledgeGraphStore | None, pattern_recognizer: PatternRecognizer | None, proactive_config: ProactiveConfig)`. `knowledge_graph_store`/`pattern_recognizer` optional — `PROJECT_INACTIVITY`/habit-informed thresholds degrade to their fixed config defaults when absent, matching the "optional collaborator, graceful degrade" shape `ContextEngine` itself already established at Sprint 6.3.

## Expected Interfaces

None new.

## Expected Functions

- `ProactiveAssistant.start()`/`stop()`/`health_check()` — registers/removes one `TaskScheduler` job on `proactive_config.evaluation_interval_seconds`, matching `WellnessTracker`'s own established shape exactly.
- `ProactiveAssistant._on_tick() -> None` — calls `_evaluate_triggers()`; for each fired, non-cooled-down `ProactivePrompt`, enqueues it via `priority_queue_manager.enqueue()` at its own `priority`.
- `ProactiveAssistant._evaluate_triggers() -> list[ProactivePrompt]` — builds one `WorkingContext` via `context_engine.build()`, then checks each of the six triggers against it: `UPCOMING_DEADLINE`/`FORGOTTEN_REMINDER` from `working_context.upcoming_scheduled_items`; `BATTERY_CRITICAL` from `working_context.resource_status`; `LONG_SESSION` from `working_context.recent_applications`' own contiguous-session duration; `MISSED_MEAL` from the current hour falling inside the configured window with no qualifying break detected in `recent_applications`; `PROJECT_INACTIVITY` from `knowledge_graph_store.find_entities(EntityType.PROJECT)`'s own `last_referenced_at` fields, when `knowledge_graph_store` is supplied.
- `ProactiveAssistant._is_cooled_down(trigger_type: ProactiveTriggerType) -> bool` — the in-memory per-trigger-type dedup, matching `_maybe_enqueue_wellness_prompt()`'s own Sprint 5.24 precedent exactly.

## Data Flow

```
TaskScheduler job (proactive_config.evaluation_interval_seconds)
      ↓
ProactiveAssistant._on_tick()
      ↓
_evaluate_triggers()
      ↓
ContextEngine.build()  →  WorkingContext (real, current, cross-subsystem snapshot)
      ↓
   six trigger checks against WorkingContext (+ optional KnowledgeGraphStore/PatternRecognizer)
      ↓
list[ProactivePrompt]  →  filtered by _is_cooled_down()
      ↓
priority_queue_manager.enqueue(prompt, priority)   →  same queue WELLNESS/SCHEDULED_REMINDER already use
      ↓
(wired at 6.13) voice/pipeline.py's _check_and_announce_priority_item()  →  spoken, respecting
QuietModeController's existing DORMANT-only announce gate — unchanged, reused exactly
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml`/`config/loader.py` — `ProactiveConfig`.
2. `proactive/proactive_model.py` — `ProactiveTriggerType`, `ProactivePrompt`.
3. `proactive/proactive_assistant.py` — `start()`/`stop()`/`health_check()`, `_on_tick()`, `_evaluate_triggers()` (all six checks), `_is_cooled_down()`.
4. Unit tests: each of the six triggers independently, both firing and not-firing cases, against a fake `ContextEngine`/`WorkingContext`; cooldown suppression (a still-true condition does not re-fire within `trigger_cooldown_seconds`, but does after); `PROJECT_INACTIVITY`/habit-informed checks degrading cleanly when `knowledge_graph_store`/`pattern_recognizer` are `None`; `start()`/`stop()` job lifecycle against a real `TaskScheduler` with a fast interval (matching this codebase's now-standard "real collaborator, short interval, bounded wait" test precedent).

## Architecture Notes

`ProactiveAssistant` never calls `DecisionEngineV2.rank_actions()` — proactive prompts are not `ActionRequest`s, they are announcements, so `requires_confirmation`-style dispatch gating does not apply to them the way it does to a genuine action candidate. The dependency on `decision_engine_v2` named in Objectives above is intentionally narrower than that: this sprint uses it only for `ReasoningEngine`-derived confidence (via `DecisionEngineV2`'s own composition) when a trigger's own evidence is thin (e.g. a `PROJECT_INACTIVITY` reading based on very few `last_referenced_at` samples) — a low-confidence trigger is suppressed rather than announced, the same "when genuinely uncertain, default to not interrupting" instinct Level 6's own design principles name directly ("Never interrupt unnecessarily").

Six triggers, six independent checks, one shared cooldown mechanism — deliberately not a rules-engine/plugin abstraction for triggers (no basis in this brief for more than six, and a generic trigger-plugin system would be real, unrequested infrastructure for a fixed, small, named list).

## Integration Considerations

- No live announcement path yet — `ProactiveAssistant.enqueue()`s land in the same `PriorityQueueManager` `WellnessTracker`/`ReminderEngine` already use, but nothing in this sprint changes `voice/pipeline.py`. Sprint 6.13 (Integration) registers `ProactiveAssistant` as a real `ManagedModule` in `main.py` and confirms `_check_and_announce_priority_item()`'s existing dispatch table already handles `IMPORTANT_ALERT`/`GENERAL_SUGGESTION` sources generically (it does, per Sprint 5.24's own design — this sprint should need **no changes to that dispatch table itself**, only a new producer feeding it, closing `backlog/technical_debt.md` item 17 for real at last).
- Sprint 6.12 (Adaptive Prioritization) is what later arbitrates a `ProactivePrompt` against a simultaneously-competing live conversation or another priority source — this sprint enqueues honestly, it does not itself decide whether "now" is a good moment beyond the cooldown/confidence gates above.

## Potential Risks

- **All six threshold defaults (`deadline_warning_hours`, `battery_critical_percent`, `long_session_hours`, the meal window, `project_inactivity_days`, `trigger_cooldown_seconds`) are unvalidated guesses** — real, disclosed, matching every comparable tuned constant in this codebase; a strong candidate for the Sprint 6.15 real-usage verification pass to revisit.
- **`MISSED_MEAL`'s own detection (no qualifying break in `recent_applications` during the configured window) cannot distinguish "the user is deep in focused work" from "the user is away from the machine entirely"** — a real, honest limitation of window-focus-based inference; disclosed rather than solved with a fabricated confidence.
- **`PROJECT_INACTIVITY` requires `knowledge_graph_store` to be supplied and populated** — on a fresh install (or before Sprint 6.6's entities exist for a given project), this trigger silently never fires rather than fabricating urgency from no evidence, the correct degrade per the Fail Gracefully Rule but worth stating plainly as a real, expected early-life gap.
- **Six triggers competing for the same `evaluation_interval_seconds` tick could, in a genuinely bad-luck moment, all fire in the same poll** — `_on_tick()` enqueues all that pass their own gates in one pass; nothing in this sprint limits how many `ProactivePrompt`s can be queued at once. Sprint 6.12 (Adaptive Prioritization) is the sprint that arbitrates competing announcements — this sprint's own job is only to produce them honestly, not to also solve "too many at once," which is explicitly a later sprint's responsibility.

## Acceptance Criteria

- Each of the six triggers fires a `ProactivePrompt` with the correct `PriorityLevel` when its own condition is genuinely met against a real `WorkingContext`, and does not fire when it isn't.
- A fired trigger does not re-fire within `trigger_cooldown_seconds` even if its underlying condition remains true; it does fire again once the cooldown expires and the condition is still (or newly) true.
- `PROJECT_INACTIVITY` and any habit-informed threshold adjustment degrade to silence (no crash, no fabricated urgency) when `knowledge_graph_store`/`pattern_recognizer` are `None`.
- `start()` registers exactly one `TaskScheduler` job; `stop()` removes it.
- Nothing in this sprint calls `ActionRegistry.dispatch()`, `WorkflowExecutor.run()`, or any other executor — verified by a dedicated test asserting zero such calls occur during `_on_tick()`.

## Testing Checklist

- [ ] Unit: `ProactiveTriggerType`/`ProactivePrompt` construction.
- [ ] Unit: each of the six triggers, firing and non-firing cases, against a fake `ContextEngine`.
- [ ] Unit: cooldown suppression and expiry.
- [ ] Unit: `PROJECT_INACTIVITY`/habit-informed checks with `knowledge_graph_store`/`pattern_recognizer` present vs. `None`.
- [ ] Unit: `start()`/`stop()` against a real `TaskScheduler` with a fast interval.
- [ ] Unit: zero-executor-call proof during `_on_tick()`.
- [ ] Unit: `ProactiveConfig` validation.

## Documentation Checklist

- [ ] `proactive/proactive_assistant.py` docstring: the closing of `backlog/technical_debt.md` item 17's `IMPORTANT_ALERT` gap, stated explicitly, and the shared-dispatch-table (no `voice/pipeline.py` change needed) design.
- [ ] `docs/STATUS.md` — Level 6 Part A narrative extended.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

High.

## Estimated Development Time

2.5–3 days.

## Risks

See Potential Risks above.

## Next Sprint

6.9 — Multi-Step Workflow Engine.

## Future Considerations

- User-configurable per-trigger enable/disable (a settings-surface concern — no sprint in this Book names a UI change; `ui/` is out of scope here).
- A second meal-window pair (dinner) — no basis named in this brief beyond "missed meal" singular; not built speculatively.
- Trigger-specific cooldowns (rather than one shared `trigger_cooldown_seconds`) — a plausible refinement once Sprint 6.15's real-usage pass shows the shared value is too coarse for some triggers; not assumed necessary here.

## Sprint Completion Report (2026-08-09)

Implemented as specified, authorized directly ("continue with sprint 6.8") in the same session as Sprints 6.4–6.7, right after 6.7 closed.

Delivered a new `proactive/` package: `proactive/proactive_model.py` (`ProactiveTriggerType`, `ProactivePrompt`) and `proactive/proactive_assistant.py` (`ProactiveAssistant`, a real `ManagedModule`), plus `ProactiveConfig` (`config/schema.py`/`config/defaults.yaml`/`config/loader.py`), continuing this Book's own established declaration order.

**Closes `backlog/technical_debt.md` item 17 for real, at last** — `PriorityLevel.IMPORTANT_ALERT` (declared Sprint 3.10, tracked open across four prior partial resolutions at Sprints 4.6, 4.15, 4.18, 5.24) finally gets its first real periodic producer (`UPCOMING_DEADLINE`/`BATTERY_CRITICAL`/`FORGOTTEN_REMINDER`). `ProactiveAssistant` also produces `GENERAL_SUGGESTION` for its three softer triggers (`LONG_SESSION`/`MISSED_MEAL`/`PROJECT_INACTIVITY`), reusing that existing `PriorityLevel` rather than widening the enum, per this sprint's own Engineering Rationale. `_on_tick()` only ever calls `priority_queue_manager.enqueue()` — the exact same queue `WellnessTracker`/`ReminderEngine` already feed; `voice/pipeline.py`'s `_check_and_announce_priority_item()` dispatch table needs no change (confirmed directly: this sprint's own `git diff` touches nothing outside `proactive/`/`config/`/tests), only a new producer feeding it, exactly as this sprint file's own Integration Considerations predicted.

**A real bug found and fixed by running the tests, not merely writing them** — the single most valuable finding of this sprint: `_evaluate_triggers()` was first implemented computing `now` internally via `datetime.now(UTC)`, rather than accepting an injectable parameter. Two of the very first test run's 31 tests failed as a direct, immediate consequence: a `FORGOTTEN_REMINDER` case whose fixture was built relative to a fixed `_NOW` while the real code compared against the real wall clock, and a `MISSED_MEAL` case whose fixture assumed the current hour fell inside the configured window when the real wall clock's hour did not. This is the exact failure mode `wellness/wellness_tracker.py`'s own `evaluate_triggers(now: datetime | None = None, ...)` was already built to prevent — that module's own docstring states the reason explicitly: "so a real late-night test run can never make an unrelated boundary test flaky." `_evaluate_triggers()` was widened to accept the identical `now: datetime | None = None` parameter (defaulting to real time in production), and every test in the new suite was updated to pass an explicit, fixed `now` — not just the two that failed, since every other trigger test had been passing only by coincidental proximity between the fixed test fixture and whatever the real wall clock happened to read at run time, the same latent flakiness risk whether or not it happened to surface today.

**Two real, disclosed "accepted but not yet consumed" constructor collaborators — the same pattern this Sprint Book has now established three separate times** (Sprint 6.5's `DecisionEngineV2.authority_evaluator`, Sprint 6.7's optional `PatternRecognizer.workflow_store`, and now both `decision_engine_v2` and `pattern_recognizer` here): `decision_engine_v2` is required per this sprint's own literal Expected Classes signature, but `DecisionEngineV2` exposes no method suited to producing a bare confidence estimate for non-`ActionRequest` evidence — its own `rank_actions()` needs a real `ActionRequest`, and `knowledge/knowledge_model.py`'s `Entity` (`PROJECT_INACTIVITY`'s only evidence source) carries a single `last_referenced_at` timestamp, no "how many samples" dimension for a confidence estimate to even be about. `pattern_recognizer` is likewise accepted (optional, per Expected Classes) but no trigger check calls it — neither this sprint's own Expected Functions text nor any composed data type names a concrete "habit-informed threshold" mechanism. Both stored, neither called, both disclosed in the module's own docstring — real, disclosed gaps for Sprint 6.12/6.13 to actually wire, not invented here.

**Two real design decisions this sprint file's own text left without a concrete formula, both resolved directly and disclosed, distinct in kind from a textual correction — genuine judgment calls, not spec errors**:

1. `LONG_SESSION` is measured as total logged active `UsageSession` time within `ContextEngine`'s own bounded `usage_lookback_hours` window (each session's own `ended_at - started_at`, summed), not strict single-unbroken-block contiguity as this sprint file's own prose phrase ("contiguous-session duration") suggests literally — `UsageSession` carries no gap/break information beyond its own start/end timestamps, and no gap-tolerance constant is named anywhere in `ProactiveConfig`. Summing real logged active time within the already-bounded window is the honest, buildable proxy this data actually supports; disclosed as a real limitation (a stale burst of activity can still read as "long session" until it ages out of the lookback window), matching this sprint's own Potential Risks framing rather than fabricating false precision.
2. `MISSED_MEAL`'s "no qualifying break detected" uses a real, disclosed, unvalidated local constant (`_QUALIFYING_BREAK_SECONDS = 900.0`, 15 minutes) as the minimum gap between two consecutive sessions overlapping the configured meal window that counts as a genuine break — not promoted to `ProactiveConfig` since this sprint's own Files to Modify names no such field.

Every other design decision followed the sprint file's own explicit text directly: `_is_cooled_down()` dedups per `ProactiveTriggerType` only (not per specific item), matching `_maybe_enqueue_wellness_prompt()`'s own Sprint 5.24 precedent exactly for these six inherently-singular-per-poll triggers; `UPCOMING_DEADLINE` vs. `FORGOTTEN_REMINDER` are cleanly distinguished by `scheduled_at` relative to `now` against the same `working_context.upcoming_scheduled_items` list (confirmed via `CalendarStore.list_due_within()`'s own real docstring that overdue items genuinely surface in that list, not silently excluded); `PROJECT_INACTIVITY` degrades to silence (never a crash or fabricated urgency) when `knowledge_graph_store` is `None`.

41 new tests: `tests/unit/proactive/test_proactive_model.py` (3 — `ProactivePrompt` defaults/subject-entity-id carrying, `ProactiveTriggerType`'s exact six-member set), `tests/unit/proactive/test_proactive_assistant.py` (28 — all six triggers' firing and non-firing cases including edge cases per trigger — completed/non-`DEADLINE`/beyond-window for `UPCOMING_DEADLINE`, completed-but-overdue for `FORGOTTEN_REMINDER`, no-battery-present for `BATTERY_CRITICAL`, empty-sessions for `LONG_SESSION`, a real detected break and an out-of-window case for `MISSED_MEAL`, non-`PROJECT`-entity and `None`-store degrade for `PROJECT_INACTIVITY`; cooldown suppression, expiry, and correct priority/source on enqueue; `start()`/`stop()`/`health_check()` against a real `TaskScheduler` with a fast interval; the AST-based zero-executor-import proof), plus 10 more `ProactiveConfig` validation tests in `test_schema.py`.

Full suite (unit + integration, opt-in real-model marker excluded): 2135 passing, 1 skipped (2136 total, up from 2095), zero failures, zero new flakiness (the wall-clock bug above was caught and fixed before this count, not left as latent flakiness). `ruff check .` clean repo-wide (one unused import and two line-length violations caught and fixed in the new test file before this count).

`docs/STATUS.md` (Level 6 Part A narrative extended, Part A header → "8/15 implemented," Learning & Proactive Assistance phase → "6.7 and 6.8 Complete"), `docs/sprint_book/INDEX.md` (6.8 row → `Complete`), `docs/backlog/technical_debt.md` (new item 46, `proactive/` top-level package addition, same treatment as items 2/40/42/43/44/45; item 17's own row updated with a final resolution note, closing the last of its four-part gap) all updated.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Sprints 6.4–6.7's own still-uncommitted work, the user not yet asked whether to commit. **Sprint 6.9 (Multi-Step Workflow Engine) is next.**
