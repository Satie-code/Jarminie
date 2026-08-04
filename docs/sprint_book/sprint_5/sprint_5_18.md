# Sprint 5.18 — Wellness Triggers

## Sprint ID

5.18

## Sprint Name

Wellness Triggers

## Purpose

Give the Wellness Engine its detection half — per `02_System_Architecture.md`'s Wellness Engine section ("Owned exclusively by Minie... Screen time, Hydration, Eye protection, Break reminders, Late-night reminders, Overwork awareness... Soft Wellness Rule: Recommend. Never force.") and `04_Master_Implementation_Plan.md`'s Phase 5.2 ("Break reminders. Hydration reminders. Eye protection... Acceptance Criteria: Gentle reminders."). This sprint decides *when* a wellness prompt should fire; escalation/postponement/the Hard Limit Rule (Sprint 5.19) and actually speaking a prompt (Sprint 5.24) are both deliberately out of scope.

## Engineering Rationale

Corresponds to the roadmap-granularity `Wellness Triggers` entry (originally numbered `5.17`, Phase 5.2), renumbered to `5.18` per this Sprint Book's own real build order (see `docs/sprint_book/INDEX.md`'s "Level 5 Part B breakdown changes" note) — its own two real dependencies (Sprint 4.15's `TaskScheduler`, Sprint 5.2's `EmotionalStateManager`) are both already satisfied; it does not need Sprint 5.17's `UsageTracker` at all, a deliberate architectural choice explained next.

**A real, disclosed independence decision**: Part 2 names Wellness Engine and Analytics Engine as sibling top-level engines, not a dependency chain (mirroring `sprint_4_14.md`'s own "Scheduler is architecturally independent of Device Control/Workflow" reasoning) — and the roadmap-granularity `Depends On` column for this sprint names `5.2` (Emotional State Manager), not `5.20`/`5.17` (Usage & Habit Tracking), confirming this independence was already the intended design, not an oversight this expansion introduces. Concretely: Wellness only needs to know *whether the user is currently present and active*, not *which application* they are using — so `WellnessTracker` reads raw, lightweight OS-level idle time directly (`win32api.GetLastInputInfo()`, already available via the locked `pywin32` dependency, the same library `device_control/window_manager.py`/`application_manager.py` already import) rather than depending on Sprint 5.17's richer, per-application `UsageTracker`. This keeps the two engines honestly decoupled, exactly as Part 2's own architecture describes them, and means Sprint 5.19/5.18 could in principle have been built before Sprint 5.17 — the two are ordered 5.17-before-5.18 here only because Sprint 5.22 (Adaptive Wellness) later needs Sprint 5.21 (Pattern Recognition), which itself needs Sprint 5.17, so keeping the Analytics foundation earliest in the file numbering reads more naturally even though Wellness's own first two sprints do not require it.

**Soft Wellness Rule ("Recommend. Never force.") is enforced structurally, not just documented**: `WellnessTracker` has no method that can pause, block, or lock any other subsystem, any voice session, or the UI — every public method either returns a value (an evaluated `WellnessPrompt | None`) or manages this class's own internal timer state. There is no code path anywhere in this sprint capable of *forcing* anything; a mechanical AST-based test (mirroring `sprint_5_9.md`'s own `gesture_engine.py`-imports-nothing-from-any-renderer precedent) confirms `wellness/` imports nothing from `voice/`, `ui/`, or `device_control/` at this sprint's own stage.

## Objectives

- `WellnessTriggerType` (the five named categories: `BREAK`, `HYDRATION`, `EYE_PROTECTION`, `LATE_NIGHT`, `OVERWORK`) and `WellnessPrompt` (a produced, not-yet-spoken recommendation).
- `WellnessTracker`: a `ManagedModule` that tracks continuous active-presence time via a `TaskScheduler`-driven idle check and evaluates each trigger's own config-driven threshold.
- `WellnessConfig` (new `config/schema.py` section), this Part's second (after `AnalyticsConfig`).

## Dependencies

4.15 (`scheduler/task_scheduler.py`'s `TaskScheduler`, the shared periodic-tick mechanism this sprint reuses exactly as Sprint 5.17 did), 5.2 (`emotion/state_manager.py`'s `EmotionalStateManager` — `EmotionalState.stress`/`.energy` optionally widen the OVERWORK/BREAK trigger's own sensitivity, see Architecture Notes; a null/absent `EmotionalState` degrades to the plain time-threshold check alone, never a hard failure).

## Files to Create

- `wellness/wellness_model.py` — `WellnessTriggerType` (Enum), `WellnessPrompt` (dataclass).
- `wellness/wellness_tracker.py` — `WellnessTracker`.
- `tests/unit/wellness/test_wellness_model.py`
- `tests/unit/wellness/test_wellness_tracker.py`

## Files to Modify

- `config/schema.py` — new `WellnessConfig` dataclass: `idle_check_interval_seconds: float = 60.0` (`WellnessTracker`'s own `TaskScheduler` tick), `inactivity_reset_seconds: float = 900.0` (15 minutes — the "significant inactivity" resume condition Part 2's Hard Limit Rule names; also resets the plain continuous-active-time counter this sprint tracks, independent of any escalation state Sprint 5.19 owns), `break_interval_seconds: float = 3600.0`, `hydration_interval_seconds: float = 2700.0`, `eye_protection_interval_seconds: float = 1200.0` (the 20-20-20 convention: every 20 minutes), `overwork_daily_seconds: float = 21600.0` (6 hours of cumulative active time in one calendar day), `late_night_start_hour: int = 23`, `late_night_end_hour: int = 5` (a wrapping window — `late_night_start_hour > late_night_end_hour` means "wraps past midnight," validated), `trigger_priority_order: tuple[str, ...] = ("break", "eye_protection", "hydration", "overwork", "late_night")` (config-driven, not hardcoded, per `03_Engineering_Standards.md`'s own rule — resolves which single trigger fires when more than one threshold is crossed in the same tick).
- `config/defaults.yaml` — matching `wellness:` section.

## Expected Classes

- `WellnessTriggerType` (Enum) — `BREAK`, `HYDRATION`, `EYE_PROTECTION`, `LATE_NIGHT`, `OVERWORK`.
- `WellnessPrompt` (dataclass) — `prompt_id: str`, `trigger_type: WellnessTriggerType`, `message: str`, `triggered_at: datetime`, `escalation_level: int = 1` (the field Sprint 5.19 gives real behavior to — present now so this sprint's own shape does not need a breaking change later, the same "field exists before the sprint that gives it real behavior" precedent `presentation/presentation_state.py`'s `gesture_probability` already established at Sprint 5.5/5.9).
- `WellnessTracker(ManagedModule)` — constructor DI: `(task_scheduler: TaskScheduler, wellness_config: WellnessConfig, emotional_state_manager: EmotionalStateManager | None = None)`.

## Expected Interfaces

None new.

## Expected Functions

- `WellnessTracker._sample_idle_seconds() -> float` — wraps `win32api.GetLastInputInfo()`/`win32api.GetTickCount()` into elapsed idle seconds; the only OS-facing call in this sprint.
- `WellnessTracker._on_tick() -> None` — samples idle time; when it exceeds `inactivity_reset_seconds`, resets `_continuous_active_seconds` to `0.0` and clears each trigger's own per-day/per-session bookkeeping the same reset would imply (never touches Sprint 5.19's escalation/postponement state, which is that sprint's own concern); otherwise adds the elapsed tick interval to `_continuous_active_seconds` and to the day's cumulative `_daily_active_seconds`, then calls `evaluate_triggers()`.
- `WellnessTracker.evaluate_triggers(now: datetime | None = None) -> WellnessPrompt | None` — a pure function of the tracker's own current counters plus `wellness_config` (deliberately callable directly in tests, independent of the timer, the same "pure decision, separately testable" precedent `presentation/gesture_engine.py`'s `maybe_roll_ambient_gesture()` already established): checks each `WellnessTriggerType` in `trigger_priority_order`, returns the first whose own threshold is currently crossed, or `None` if none are. Never returns more than one `WellnessPrompt` per call — Part 2 names no "multiple simultaneous reminders" behavior, and stacking would itself violate the Soft Wellness Rule's own spirit.
- `WellnessTracker.acknowledge_prompt(trigger_type: WellnessTriggerType) -> None` — resets that trigger's own elapsed counter back to zero (called once a real caller, Sprint 5.24, confirms the user actually heard/acted on a prompt) — deliberately separate from the tick-driven `_continuous_active_seconds`/`_daily_active_seconds` reset, since acknowledging a hydration reminder should not also reset the break timer.

## Data Flow

```
TaskScheduler job (wellness_config.idle_check_interval_seconds)
      ↓
WellnessTracker._on_tick()
      ↓
_sample_idle_seconds()  →  win32api (real OS state)
      ↓
significant inactivity? → reset counters : accumulate counters
      ↓
evaluate_triggers()  →  WellnessPrompt | None
      ↓
(held internally this sprint — Sprint 5.19 adds escalation gating,
Sprint 5.24 adds the real PriorityQueueManager.enqueue() + spoken
announcement)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `WellnessConfig`, including the wrapping-window validation for `late_night_start_hour`/`late_night_end_hour`.
2. `wellness/wellness_model.py` — `WellnessTriggerType`, `WellnessPrompt`.
3. `wellness/wellness_tracker.py` — `WellnessTracker`: idle sampling, counter accumulation/reset, `evaluate_triggers()`, `acknowledge_prompt()`.
4. Unit tests: each trigger's own threshold crossing in isolation; `trigger_priority_order` resolving a simultaneous-crossing tie deterministically; a significant-inactivity tick resetting counters (and therefore suppressing an about-to-fire trigger); `acknowledge_prompt()` resetting only its own trigger's counter; the late-night wrapping-window check at both edges (e.g. 23:00 and 04:59); an absent `emotional_state_manager` degrading to the plain time-only check.
5. A mechanical AST-based test confirming `wellness/` imports nothing from `voice/`, `ui/`, or `device_control/` (per Engineering Rationale above).

## Architecture Notes

The Emotion Engine's real, live `EmotionalState` (5.2) is used only as a narrow, disclosed *sensitivity* input, never a trigger condition of its own: when `emotional_state_manager` is supplied, `evaluate_triggers()` shortens the effective `overwork_daily_seconds`/`break_interval_seconds` threshold by a config-bounded fraction (`WellnessConfig.stress_sensitivity_factor`, default `0.0` — meaning inert unless explicitly configured, a conservative, disclosed default) when `EmotionalState.stress` is high — Part 2's Wellness Engine section does not name emotion-awareness explicitly, but its own Adaptive Wellness Rule ("Learn work patterns. Adjust reminders accordingly") and the project's own cross-cutting Emotion Engine integration precedent (Sprint 5.4's tone adaptation, Sprint 5.14's live wiring) both support a narrow, bounded, opt-in-by-default-zero adjustment here rather than ignoring an already-real signal that is directly relevant to "Overwork awareness." This is a Level 5 Part A → Part B reuse, not a new Emotion Engine capability.

`WellnessTracker` maintains its own private counters (`_continuous_active_seconds`, `_daily_active_seconds`, per-trigger last-fired timestamps) entirely in memory — no SQLite persistence in this sprint. A process restart loses today's accumulated counters, an honest, disclosed limitation (see Potential Risks) rather than a speculative persistence layer with no real Part 2 basis naming one.

## Integration Considerations

- Registered as a `ManagedModule` with `CoreManager` by Sprint 5.24 (Companion Intelligence Integration).
- No real caller of `evaluate_triggers()`'s own returned `WellnessPrompt` exists yet — nothing enqueues it to `PriorityQueueManager.enqueue(PriorityLevel.WELLNESS, ...)` and nothing speaks it. `decision/priority_queue.py`'s `PriorityLevel.WELLNESS` and `decision/authority.py`'s `EngineSelection.WELLNESS` both remain fully reserved after this sprint, exactly as their own docstrings already state — this sprint does not change either.
- Sprint 5.19 (Wellness Escalation & Hard Limit) is this sprint's own real, immediate consumer within this Sprint Book.

## Potential Risks

- **In-memory-only counters do not survive a process restart** — a user mid-way through a long session who restarts JARMINEI gets a fresh, zeroed break/hydration/overwork clock. Acceptable for this sprint's own scope (no Part 2 text names persistence), flagged as a Future Consideration.
- **`GetLastInputInfo()` measures system-wide keyboard/mouse idle time, not "is the user still present and thinking"** — a user reading a long document or in a voice-only conversation with no keyboard/mouse activity would register as idle and incorrectly reset counters. A real, disclosed limitation of the only system-wide idle signal `pywin32` provides without a new dependency; a Future Consideration (e.g. treating an active voice session as presence too) is named, not built speculatively this sprint, since the wiring between `VoiceSessionManager` and `WellnessTracker` is Sprint 5.24's own integration concern.
- **All threshold defaults (`break_interval_seconds`, `hydration_interval_seconds`, etc.) are unvalidated guesses**, the same tuned-constant caveat every comparable default in this codebase already carries — genuinely no clinical or ergonomic authority backs these numbers, and none is claimed.
- **This sprint's own real-world testability is limited to directly driven ticks** (no live caller yet), the same honest scoping limitation `sprint_4_14.md`/`sprint_5_1.md` both already named for their own first-sprint-of-a-phase position.

## Acceptance Criteria

- Each of the five trigger types fires exactly once its own configured threshold is reached, and not before.
- `trigger_priority_order` deterministically resolves a tie when more than one trigger's threshold is crossed in the same tick.
- A tick registering idle time beyond `inactivity_reset_seconds` resets `_continuous_active_seconds`/`_daily_active_seconds` to zero, correctly suppressing a trigger that would otherwise have fired.
- `acknowledge_prompt()` resets only the acknowledged trigger's own counter, leaving the others untouched.
- The late-night window correctly wraps past midnight at both configured edges.
- No method in this sprint's own files can block, pause, or otherwise force any other subsystem — confirmed both by code review and the AST-based import-boundary test.

## Testing Checklist

- [ ] Unit: `WellnessPrompt`/`WellnessTriggerType` construction and defaults (`escalation_level` defaults to `1`).
- [ ] Unit: each trigger type's own threshold-crossing boundary (just-under does not fire, at-or-over does).
- [ ] Unit: `trigger_priority_order` tie resolution.
- [ ] Unit: significant-inactivity reset, including the counter-suppression consequence.
- [ ] Unit: `acknowledge_prompt()` per-trigger isolation.
- [ ] Unit: late-night wrapping-window edges.
- [ ] Unit: `emotional_state_manager` present vs. absent — both must produce a valid result, never raise.
- [ ] Static/AST: `wellness/` imports nothing from `voice/`, `ui/`, `device_control/`.

## Documentation Checklist

- [ ] `wellness/wellness_tracker.py` docstring: the independence-from-`UsageTracker` decision and the Soft Wellness Rule's structural enforcement, both stated explicitly (per Engineering Rationale above).
- [ ] `docs/STATUS.md` — Phase 5.2 (Wellness Engine) row moves to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

5.19 — Wellness Escalation & Hard Limit.

## Future Considerations

- Persisting counters across a restart — flagged above, not built now.
- Treating an active voice session (not just keyboard/mouse activity) as presence — the real idle-signal gap named above, deferred to whichever sprint first needs it (likely Sprint 5.24 or later, once the exact integration shape is decided).
- Per-trigger user-configurable thresholds via a settings UI — no settings-UI surface exists for Wellness anywhere in this Sprint Book; would need one named explicitly by a future sprint.
