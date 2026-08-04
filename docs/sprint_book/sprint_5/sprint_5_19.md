# Sprint 5.19 — Wellness Escalation & Hard Limit

## Sprint ID

5.19

## Sprint Name

Wellness Escalation & Hard Limit

## Purpose

Give Sprint 5.18's raw `WellnessPrompt` trigger detection real escalation and postponement-tracking behavior — per `02_System_Architecture.md`'s Wellness Engine section: "Wellness Escalation: Reminder 1 — Gentle. Reminder 2 — Slightly stronger. Reminder 3 — Strong recommendation." and "Hard Limit Rule: Stop repeated reminders after three postponements. Resume after: New session. Actual break. Significant inactivity." Closes the state-machine half of the Wellness trio; actually enqueuing/speaking a prompt remains Sprint 5.24's own job.

## Engineering Rationale

Corresponds to the roadmap-granularity `Wellness Escalation & Hard Limit` entry (originally numbered `5.18`, Phase 5.2), renumbered to `5.19` per this Sprint Book's own real build order — unchanged in scope, its only real dependency (Sprint 5.18) is now satisfied.

**A real, disclosed state-ownership decision**: the escalation/postponement state lives in a new `WellnessEscalationManager`, not folded directly into `WellnessTracker` (5.18), mirroring the exact "storage/tracking split from behavior/policy" separation `sprint_4_14.md`'s `CalendarStore`/`sprint_4_15.md`'s `ReminderEngine` already established for the Scheduler — `WellnessTracker` decides *whether a threshold is crossed*, `WellnessEscalationManager` decides *whether that crossing is still allowed to produce a prompt at all* (i.e. not hard-limited) and *what wording level* it should carry. Keeping them separate means Sprint 5.22 (Adaptive Wellness) can later observe and adjust `WellnessTracker`'s own thresholds without needing any awareness of escalation state, and a future settings UI could reset escalation state independently of the underlying activity timer.

**Part 2's own "three postponements" and reset-condition list are both taken literally, not reinterpreted** — `max_postponements_before_hard_limit` is a config field (default `3`, per `03_Engineering_Standards.md`'s own "no hardcoded... thresholds" rule) rather than a bare literal `3` anywhere in the implementation, and all three named resume conditions ("New session," "Actual break," "Significant inactivity") reduce to exactly one real signal this codebase already has by Sprint 5.18: `WellnessTracker`'s own significant-inactivity reset (Sprint 5.18's `_on_tick()` already resets `_continuous_active_seconds`/`_daily_active_seconds` on exactly this condition) is reused as the trigger for `WellnessEscalationManager.reset_all()` too — "new session" and "actual break" are, in this codebase's own real terms, indistinguishable from "the user was significantly inactive and has now returned," so no second, separate reset mechanism is built. This is a disclosed simplification, not a silent one: Part 2 lists three phrases but this codebase has only ever had one real underlying signal for any of them (the same "one real mechanism serving several named concepts" reasoning `sprint_4_14.md`'s single-`ScheduledItem`-shape decision already used).

## Objectives

- `WellnessEscalationManager`: per-`WellnessTriggerType` escalation level (1–3) and postponement count, with hard-limit gating.
- `WellnessTracker.evaluate_triggers()` (5.18) gains a real gate against hard-limited trigger types.
- Escalation-level-aware message phrasing (level 1 gentle, level 2 stronger, level 3 strong recommendation), config-driven per trigger type.

## Dependencies

5.18 (Wellness Triggers — `WellnessTracker`, `WellnessPrompt`, `WellnessTriggerType`, and its own significant-inactivity reset signal, reused here per Engineering Rationale above).

## Files to Create

- `wellness/escalation.py` — `WellnessEscalationManager`.
- `tests/unit/wellness/test_escalation.py`

## Files to Modify

- `wellness/wellness_tracker.py` — `evaluate_triggers()` gains an `escalation_manager: WellnessEscalationManager | None = None` parameter (an additive, optional-in-effect signature change, the same shape `Persona.compose_reply()`'s `emotional_state`/`decision_trace` parameters already established); when supplied, a hard-limited trigger type is skipped entirely (never even considered a candidate, not merely suppressed after being chosen) and a produced `WellnessPrompt.escalation_level`/`.message` reflect `escalation_manager`'s own current level for that trigger; `_on_tick()`'s own significant-inactivity branch additionally calls `escalation_manager.reset_all()` when one is supplied.
- `config/schema.py` — `WellnessConfig` gains `max_postponements_before_hard_limit: int = 3` and `escalation_message_templates: dict[str, tuple[str, str, str]]` (per-`WellnessTriggerType.value` key, a 3-tuple of level-1/level-2/level-3 message strings — config-driven phrasing, the same "small, fixed, config-driven phrase set" discipline `PresentationConfig.gesture_vocabulary` already established; a trigger type missing from this map falls back to a single generic, still-escalation-level-aware template rather than raising `KeyError`).
- `config/defaults.yaml` — matching new `WellnessConfig` fields, including all five trigger types' own three-level default phrasing.

## Expected Classes

- `WellnessEscalationManager` — constructor DI: `(wellness_config: WellnessConfig)`. Holds an internal `dict[WellnessTriggerType, _TriggerEscalationState]` (`_TriggerEscalationState`: `level: int`, `postponement_count: int`), lazily initialized per trigger type at level 1 / zero postponements on first access.

## Expected Interfaces

None new.

## Expected Functions

- `WellnessEscalationManager.register_prompt_shown(trigger_type: WellnessTriggerType) -> None` — marks that a prompt at the trigger's current level was actually surfaced (called by Sprint 5.24's real live caller once a prompt is genuinely spoken, not merely produced) — does not by itself change the level; only `register_postponed()` escalates.
- `WellnessEscalationManager.register_postponed(trigger_type: WellnessTriggerType) -> None` — increments the trigger's postponement count; raises its escalation level by one, capped at `3`; once the postponement count reaches `max_postponements_before_hard_limit`, the trigger becomes hard-limited.
- `WellnessEscalationManager.is_hard_limited(trigger_type: WellnessTriggerType) -> bool`
- `WellnessEscalationManager.current_level(trigger_type: WellnessTriggerType) -> int` — always 1–3; never 0, since level exists independently of whether a prompt has been shown yet.
- `WellnessEscalationManager.message_for(trigger_type: WellnessTriggerType) -> str` — resolves `WellnessConfig.escalation_message_templates` at the trigger's `current_level()`, falling back to the generic template when the trigger type has no dedicated entry.
- `WellnessEscalationManager.reset_all() -> None` — the Hard Limit Rule's own resume path: every trigger's level returns to 1, postponement count to 0, hard-limit cleared.
- `WellnessEscalationManager.reset(trigger_type: WellnessTriggerType) -> None` — the narrower, single-trigger version, used by `acknowledge_prompt()`'s own real caller (Sprint 5.24) once a specific reminder is genuinely acted on (e.g. the user actually takes a break), distinct from a blanket `reset_all()` inactivity reset.

## Data Flow

```
WellnessTracker._on_tick()  (5.18)
      ↓
evaluate_triggers(escalation_manager)
      ↓
escalation_manager.is_hard_limited(trigger_type)?  → yes: skip, try next candidate
      ↓ no
WellnessPrompt(escalation_level=escalation_manager.current_level(trigger_type),
               message=escalation_manager.message_for(trigger_type))
      ↓
(held internally this sprint — Sprint 5.24's real caller decides
shown/postponed/acknowledged, calling register_prompt_shown()/
register_postponed()/reset() accordingly)
      ↓
significant inactivity (5.18) → escalation_manager.reset_all()
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `max_postponements_before_hard_limit`, `escalation_message_templates` (all five trigger types plus the generic fallback).
2. `wellness/escalation.py` — `WellnessEscalationManager`: lazy per-trigger state, `register_prompt_shown()`/`register_postponed()`/`is_hard_limited()`/`current_level()`/`message_for()`/`reset_all()`/`reset()`.
3. `wellness/wellness_tracker.py` — `evaluate_triggers()`'s new optional gating/message-resolution behavior; `_on_tick()`'s new `reset_all()` call.
4. Unit tests: escalation level progression 1→2→3 across postponements, capped at 3; hard limit engaging at exactly the third postponement, not the second or fourth; a hard-limited trigger being skipped by `evaluate_triggers()` in favor of the next candidate in `trigger_priority_order` (or `None` if all are hard-limited); `reset_all()` clearing every trigger; `reset()` clearing only one; `message_for()`'s fallback for an unmapped trigger type; `evaluate_triggers()` called with no `escalation_manager` behaving exactly as Sprint 5.18 specified (backward-compatible, no regression).

## Architecture Notes

`WellnessEscalationManager` holds no reference to `WellnessTracker`, `PriorityQueueManager`, or any voice/UI collaborator — a pure, injectable policy object over its own small state, the same "pure decision function over collaborators it doesn't own" discipline `emotion/detection_engine.py`'s `_score_significance()`/`presentation/gesture_engine.py` both already established. `register_prompt_shown()` and `register_postponed()` are deliberately two different methods rather than one boolean-flagged call — a future caller cannot accidentally conflate "the user heard this" with "the user pushed it away," which matters directly for the Hard Limit Rule's own correctness (only postponement counts against the limit; being told something and doing nothing about it is not, per Part 2's own text, a postponement).

## Integration Considerations

- Registered into `main.py`'s composition only insofar as `WellnessTracker` itself is (Sprint 5.24) — `WellnessEscalationManager` has no `ManagedModule` lifecycle of its own (no `start()`/`stop()`/`health_check()`; it is plain in-memory state owned by whichever caller constructs it, the same non-`ManagedModule`-helper-class precedent `decision/context_analyzer.py`'s smaller collaborators already established).
- `register_prompt_shown()`/`register_postponed()`/`reset()` have no real caller yet within this Sprint Book — Sprint 5.24's own job, once a real spoken-prompt/postponement voice interaction exists to call them from.

## Potential Risks

- **In-memory-only state, same limitation class as `WellnessTracker`'s own counters (5.18)** — a restart resets every trigger's escalation level and postponement count, silently un-hard-limiting anything that was hard-limited. Disclosed, not solved this sprint, for the identical reason 5.18 named its own equivalent gap.
- **No distinction between "postponed once today" and "postponed once, three weeks ago"** — `postponement_count` never decays on its own except via a full `reset()`/`reset_all()`; a user who postpones a hydration reminder three times across three entirely separate days (each preceded by its own significant-inactivity reset) never actually reaches the hard limit in practice, since each reset already clears the count — this is a natural, correct consequence of the reset-condition design, not a separate bug, but worth naming so a future reader does not mistake the counters for a rolling window.
- **`escalation_message_templates`' default phrasing is written now with no user testing behind it** — the same content-quality caveat every templated-phrase config in this codebase already carries (`PresentationConfig.gesture_vocabulary`, `decision/authority.py`'s reasoning templates).

## Acceptance Criteria

- Escalation level rises from 1 to 2 to 3 across successive `register_postponed()` calls for a given trigger type, capped at 3.
- The trigger becomes hard-limited exactly upon its third `register_postponed()` call, verified against both the second (not yet limited) and fourth (still limited, no further escalation) calls.
- `evaluate_triggers()` never returns a `WellnessPrompt` for a hard-limited trigger type, correctly falling through to the next candidate in priority order or to `None`.
- `reset_all()`/`reset()` restore the expected scope (all triggers vs. one) to level 1 / zero postponements / not hard-limited.
- `evaluate_triggers()` called without an `escalation_manager` behaves identically to Sprint 5.18's own already-tested behavior (no regression).

## Testing Checklist

- [ ] Unit: escalation level progression and cap.
- [ ] Unit: hard-limit boundary (2nd/3rd/4th postponement).
- [ ] Unit: hard-limited trigger skipped by `evaluate_triggers()`, correct fallback candidate chosen.
- [ ] Unit: `reset_all()` vs. `reset(trigger_type)` scoping.
- [ ] Unit: `message_for()` mapped vs. fallback template.
- [ ] Unit: `register_prompt_shown()` never itself escalates or resets.
- [ ] Regression: `evaluate_triggers()` with no `escalation_manager` matches Sprint 5.18's own existing test expectations.

## Documentation Checklist

- [ ] `wellness/escalation.py` docstring: the "one real reset signal serving three named Part 2 conditions" simplification, stated explicitly (per Engineering Rationale above).
- [ ] `docs/STATUS.md` — Phase 5.2 (Wellness Engine) narrative updated; row stays `Developing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.20 — Analytics Dashboard Data.

## Future Considerations

- A rolling/decaying postponement window (rather than a hard reset-to-zero on inactivity) — no basis in Part 2's own literal text, not built speculatively.
- Per-trigger-type independent hard-limit resets (today `reset_all()` is the only real path Sprint 5.18's own inactivity signal drives) — a Future Consideration if a real need for finer granularity ever surfaces.
- Persisting escalation state across a restart — the same disclosed gap 5.18 already named for its own counters.

## Sprint Completion Report (2026-08-04)

Implemented as specified, continuing directly from Sprint 5.18's own completion ("Sprint 5.19 (Wellness Escalation & Hard Limit) is next"), matching this project's established direct-continue precedent.

Delivered `wellness/escalation.py`'s `WellnessEscalationManager` (constructor DI `(wellness_config,)`, no `ManagedModule` lifecycle — plain in-memory policy state, matching `decision/context_analyzer.py`'s own smaller-collaborator precedent per this sprint's own Integration Considerations) and the two new `WellnessConfig` fields (`max_postponements_before_hard_limit`, `escalation_message_templates`) in `config/schema.py`/`config/defaults.yaml`.

**`is_hard_limited()` computed live from `postponement_count`, not a separate stored flag** — `postponement_count >= max_postponements_before_hard_limit` is the single source of truth, so the count and the hard-limit state can never drift out of sync with each other (a flag set once and never re-derived could, in principle, disagree with the count after a config change or a bug elsewhere). `register_prompt_shown()` calls `_get_state()` purely to guarantee lazy initialization and otherwise does nothing — verified directly by two dedicated tests (before any postponement, and interleaved with one) confirming it never changes `current_level()`/`is_hard_limited()`.

**Two real, disclosed decisions matching this sprint's own Engineering Rationale exactly**: the generic fallback template (`_GENERIC_TEMPLATE`) is a hardcoded module constant in `escalation.py`, not a `WellnessConfig` field — the sprint's own Files to Modify names only `max_postponements_before_hard_limit`/`escalation_message_templates` as new fields, and the fallback exists purely to avoid a `KeyError` for a trigger type a user's own customized config omits, not as a second user-configurable surface. `escalation_message_templates` is typed `dict[str, list[str]]`, not the sprint file's own `dict[str, tuple[str, str, str]]` — the identical mechanical reason `trigger_priority_order` (Sprint 5.18) was already typed `list[str]`: `config/loader.py`'s real YAML load path always produces lists, never tuples.

`wellness/wellness_tracker.py`'s `WellnessTracker` gained a fourth, optional constructor parameter, `escalation_manager: WellnessEscalationManager | None = None` — not explicitly named in the sprint file's own Expected Classes (which only described the new `WellnessEscalationManager` class), but required for `_on_tick()` (a zero-argument `TaskScheduler` callback that can only reach collaborators via `self`) to call `reset_all()` "when one is supplied," exactly as the sprint's own Files to Modify text describes; `evaluate_triggers()`'s own new `escalation_manager` parameter defaults to this constructor-supplied instance when not explicitly passed, so a caller can either wire one in permanently (real Sprint 5.24 usage) or override it per-call (tests). Both defaulting to `None` means `evaluate_triggers()` called with neither reproduces Sprint 5.18's exact original behavior — verified directly by a dedicated regression test, not merely assumed from the code reading correctly.

29 new tests (`tests/unit/wellness/test_escalation.py`, 12; new coverage appended to `test_wellness_tracker.py`, 9 covering escalation-manager wiring plus the regression case). Escalation-level progression/cap, hard-limit boundary (2nd/3rd/4th postponement), `reset_all()`/`reset()` scoping, `message_for()` mapped-vs-fallback (including that the fallback ladder itself still escalates by level, not just returns a constant string), and `register_prompt_shown()`'s own no-op guarantee are each tested directly against `WellnessEscalationManager` in isolation; `evaluate_triggers()`'s hard-limit-skip-to-next-candidate behavior, its all-hard-limited-returns-`None` case, its escalation-level/message pass-through, constructor-supplied-vs-call-time-override precedence, and `_on_tick()`'s own `reset_all()` call on significant inactivity are each tested against the real `WellnessTracker`+`WellnessEscalationManager` pairing, not mocks.

Deliberately NOT given any new caller this sprint, per the sprint's own Integration Considerations — `register_prompt_shown()`/`register_postponed()`/`reset()` remain uncalled outside tests; Sprint 5.24 wires this in for real once a genuine spoken-prompt/postponement voice interaction exists. No SQLite persistence, matching Sprint 5.18's own identical in-memory-only precedent and disclosed restart-loses-state limitation.

**Full-suite verification**: unit suite confirmed clean first (1641 passed, 1 skipped); the complete combined suite (unit + integration + system, opt-in real-model tests deselected via marker) ran clean end to end — 1706 passing + 5 skipped + **zero failures**, notably including no reproduction of Sprint 5.18's own real-Ollama-output nondeterminism flake in this particular run, consistent with genuine model-output variance rather than a deterministic bug (the same class of observation Sprint 5.13's own completion report already made once before). A real, non-mocked load of `config/defaults.yaml` via `config.loader.load_config()` also confirmed the new escalation fields parse and validate cleanly end-to-end. `ruff check .` clean across the entire repository (not just this sprint's own files).

`docs/STATUS.md` (Phase 5.2 Wellness Engine narrative extended with this sprint's own paragraph; row stays `Developing`, per this sprint's own Documentation Checklist — Wellness Engine is not yet fully complete, since Sprint 5.22/Adaptive Wellness remains) and `docs/sprint_book/INDEX.md` (5.19 row → `Complete`) both updated. **Sprint 5.20 (Analytics Dashboard Data) is next.**
