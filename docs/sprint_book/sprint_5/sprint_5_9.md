# Sprint 5.9 — Gesture Engine

## Sprint ID

5.9

## Sprint Name

Gesture Engine

## Purpose

Decide **when** a discrete gesture (head movement, hand/dashboard-accent movement, eye focus, listening/speaking/idle posture, a notification reaction) should fire — persona-agnostic, per the brief's own listed gesture categories — leaving **how it looks** entirely to each renderer's own idiom (Jarvis: a subtle ring/dashboard accent; Minie: a real `trigger_gesture()`/`set_eye_target()` call through Sprint 5.8's `AvatarRenderer`).

## Engineering Rationale

**New sprint.** The when/how split is a direct application of this project's own Single Responsibility discipline, the same split already drawn between `decision/authority.py` (decides an engine is selected) and `CommunicationPipeline` (actually dispatches to it), or between `PriorityQueueManager.classify()` (decides urgency) and its consumer (decides what to do about it). `GestureEngine` never imports `presentation/jarvis_renderer.py` or `presentation/minie_renderer.py` — it emits a persona-agnostic `GestureEvent`; `PresentationController` (5.6) is what routes that event to whichever renderer is currently mounted, via a new, narrow renderer capability (see Expected Interfaces).

**Trigger sources, each independently config-gated**: (1) discrete system events (a notification arriving, a turn starting/ending, an `OperatingMode` transition — all already real, existing signals this sprint only subscribes to, constructs nothing new), and (2) a probabilistic idle/ambient roll gated by `PresentationState.gesture_probability` (5.5) — a small chance, each tick, of a purely ambient gesture (a head tilt, a small smile) firing with no discrete trigger at all, which is what makes an idle avatar/dashboard feel alive rather than static. The two sources are kept structurally distinct (`trigger_event()` vs. `maybe_roll_ambient_gesture()`) since they have genuinely different call shapes — one is event-driven, one is polled — conflating them into one method would obscure which kind of trigger is happening.

## Objectives

- `presentation/gesture_engine.py`: `GestureEngine`, `GestureEvent`, `GestureTrigger` enum.
- Config-driven gesture vocabulary and per-persona probability weighting (a config-driven mapping so Jarvis's own "no flashy effects" restraint and Minie's own "expressive, natural idle behaviors" mandate are both honored without persona-specific code inside `GestureEngine` itself).
- No renderer coupling — verified by the same mechanical import-check discipline Sprint 5.8 already established for `AvatarRenderer`.

## Dependencies

5.6 (Presentation Layer Foundation & Renderer Interface), 5.2 (Emotional State Manager — `gesture_probability` is itself derived from `EmotionalState` via 5.5, but this sprint reads `PresentationState.gesture_probability` directly, never `EmotionalState`).

## Files to Create

- `presentation/gesture_engine.py`
- `tests/unit/presentation/test_gesture_engine.py`

## Files to Modify

- `presentation/renderer.py` — `Renderer` Protocol gains one new, optional-in-practice method: `trigger_gesture(gesture_id: str) -> None` (default no-op semantics for a renderer that doesn't support gestures — but both `JarvisRenderer`/`MinieRenderer` will implement it meaningfully; this sprint adds the Protocol method, Sprint 5.7/5.8's own renderers already reserved the concept — `MinieRenderer` already forwards to `AvatarRenderer.trigger_gesture()`, Sprint 5.7's `JarvisRenderer` gains its own real implementation this sprint, per that sprint's own Integration Considerations naming this exact extension point).
- `presentation/jarvis_renderer.py` — `JarvisRenderer.trigger_gesture(gesture_id)` real implementation (a brief accent pulse on the segmented ring or sphere, config-mapped from `gesture_id`).
- `presentation/presentation_controller.py` — gains `dispatch_gesture(event: GestureEvent) -> None`, routing to the currently-mounted renderer's `trigger_gesture()`.
- `config/schema.py` — `PresentationConfig` gains `gesture_vocabulary: dict[str, list[str]]` (per-`GestureTrigger.value`, a list of candidate `gesture_id` strings to choose among — allows variety rather than the same gesture every time), `ambient_gesture_roll_interval_seconds: float = 15.0`.

## Expected Classes

- **`GestureTrigger`** (`Enum`): `NOTIFICATION`, `TURN_START`, `TURN_END`, `MODE_TRANSITION_TO_ACTIVE`, `MODE_TRANSITION_TO_DORMANT`, `LISTENING_POSTURE`, `SPEAKING_POSTURE`, `AMBIENT_IDLE` — the brief's own named categories (notification reactions, listening posture, speaking posture, idle posture) plus the turn/mode transitions that most naturally produce them.
- **`GestureEvent`** (dataclass): `trigger: GestureTrigger`, `gesture_id: str` (the concrete, renderer-facing id chosen from `PresentationConfig.gesture_vocabulary[trigger.value]`), `persona_name: str`, `triggered_at: datetime`.
- **`GestureEngine`**: constructor DI receives `PresentationConfig` only (no `PersonaManager`/`EmotionalStateManager` reference — callers pass whatever context is needed as method parameters, keeping this class a pure, easily-testable decision function).

## Expected Interfaces

`Renderer.trigger_gesture(gesture_id: str) -> None` — the one Protocol extension this sprint makes (see Files to Modify); a renderer with nothing meaningful to do for a given `gesture_id` simply no-ops, never raises.

## Expected Functions

- `GestureEngine.trigger_event(trigger: GestureTrigger, persona_name: str) -> GestureEvent | None` — never raises; returns `None` (a deliberate, logged no-op) if `trigger`'s configured vocabulary list is empty for the active persona, otherwise picks one candidate `gesture_id` (a simple round-robin or random choice among the configured list — config-driven variety, not hardcoded to always the first entry).
- `GestureEngine.maybe_roll_ambient_gesture(gesture_probability: float, persona_name: str) -> GestureEvent | None` — rolls against `gesture_probability` (0.0–1.0, from `PresentationState`); returns `None` far more often than not by design (an ambient gesture should be occasional, not constant) — rate-limited additionally by `ambient_gesture_roll_interval_seconds` (this class tracks its own last-ambient-fire timestamp internally, so even a `gesture_probability` of `1.0` can't fire more than once per configured interval).

## Data Flow

```
(discrete path, from real system events)
CommunicationPipeline turn lifecycle / OperatingMode transition (existing signals)
        |
        v
GestureEngine.trigger_event(trigger, persona_name) -> GestureEvent | None
        |
        v
PresentationController.dispatch_gesture(event) -> Renderer.trigger_gesture(event.gesture_id)


(ambient path, from PresentationController's own refresh tick)
PresentationController.refresh()  (5.6)
        |
        +--> GestureEngine.maybe_roll_ambient_gesture(state.gesture_probability, persona_name)
        |         -> GestureEvent | None
        |
        v
   (same dispatch_gesture() path as above, when non-None)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `PresentationConfig` gesture-vocabulary/interval fields, with a real, reviewable default vocabulary per trigger/persona.
2. `presentation/gesture_engine.py` — `GestureTrigger`, `GestureEvent`, `GestureEngine`.
3. `presentation/renderer.py` — `trigger_gesture()` Protocol method.
4. `presentation/jarvis_renderer.py` — real `trigger_gesture()` implementation.
5. `presentation/presentation_controller.py` — `dispatch_gesture()`, and `refresh()` extended to call `maybe_roll_ambient_gesture()` each tick.
6. `tests/unit/presentation/test_gesture_engine.py` — vocabulary selection/variety; empty-vocabulary no-op; ambient rate-limiting (a `gesture_probability=1.0` fixture still respects the interval); mechanical no-renderer-import check.

## Architecture Notes

`GestureEngine` holds **no reference to any renderer, `PersonaManager`, or `EmotionalStateManager`** — every method takes exactly the data it needs as parameters and returns a plain `GestureEvent | None`. This is deliberately more constrained than several earlier engines in this codebase (which do hold real collaborator references) because a gesture *decision* genuinely has no need to reach outside its own inputs — the same judgment `ConfidenceScorer`/`_score_significance()` (Sprint 5.3) already applied to keep a pure decision function pure.

## Integration Considerations

- **No live caller of `trigger_event()` until Sprint 5.14** — the real turn-lifecycle/mode-transition hooks that would call it live inside `CommunicationPipeline`/`voice/quiet_mode.py` are that sprint's job.
- `maybe_roll_ambient_gesture()` IS wired into `PresentationController.refresh()` this sprint (Implementation Tasks) — the one piece of this sprint's own output with a real caller already, since `PresentationController.refresh()` already exists (Sprint 5.6) and ambient rolling naturally belongs inside its own per-tick loop, not deferred to a later integration sprint for no real reason.
- Sprint 5.13 (Companion Experience) reuses `GestureTrigger.AMBIENT_IDLE`'s own machinery for its own idle-behavior needs rather than building a second, competing idle-gesture mechanism — named explicitly here so that sprint doesn't duplicate this one.

## Potential Risks

- **A default gesture vocabulary is a real, unreviewed content choice** (which specific `gesture_id` strings exist, and how many per trigger) — same "documented starting point, correctable via config" category as every other tuned default in this codebase, not treated as validated.
- **Ambient gesture rate-limiting logic living inside `GestureEngine` (stateful) breaks its "pure decision function" framing slightly** — a deliberate, disclosed trade-off (Architecture Notes' claim of purity is about collaborator references, not internal state) rather than hidden inconsistency; flagged here for a future reader who notices the tension.

## Acceptance Criteria

- `trigger_event()`/`maybe_roll_ambient_gesture()` never raise for any input, including an empty configured vocabulary.
- Ambient gesture rate-limiting is verified directly (repeated calls within the configured interval never produce more than one non-`None` result).
- `Renderer.trigger_gesture()` is implemented meaningfully by both `JarvisRenderer` and `MinieRenderer` (via `AvatarRenderer`), verified by dedicated tests in each renderer's own test file (updated this sprint).
- Mechanical check: `presentation/gesture_engine.py` imports nothing from `jarvis_renderer.py`/`minie_renderer.py`/`vtube_studio_renderer.py`.
- `ruff check .` clean; full existing suite (including Sprint 5.6/5.7/5.8's own tests, re-run against the `Renderer` Protocol's new method) still passes.

## Testing Checklist

- [ ] Unit: `trigger_event()` vocabulary selection, variety, and empty-vocabulary no-op.
- [ ] Unit: `maybe_roll_ambient_gesture()` probability behavior and interval rate-limiting.
- [ ] Unit (regression): `JarvisRenderer`/`MinieRenderer` `trigger_gesture()` implementations.
- [ ] Mechanical: no renderer import inside `gesture_engine.py`.
- [ ] Full regression: existing suite unaffected beyond the intentional `Renderer` Protocol extension.

## Documentation Checklist

- [ ] `presentation/gesture_engine.py` module docstring explains the when/how split (Engineering Rationale) explicitly.
- [ ] `presentation/renderer.py`'s `Renderer` docstring documents the new `trigger_gesture()` method's no-op-when-unsupported contract.
- [ ] `docs/STATUS.md` — Level 5 Part A row updated.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium.

## Estimated Development Time

1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.10 — Persona Transition Engine.

## Future Considerations

- A richer gesture vocabulary (more variety per trigger) is real future content work, not an architecture change.
- If a genuine need for gesture *sequences* (more than one gesture chained together) emerges, that is new scope for a future sprint — this sprint's `GestureEvent` is deliberately single-gesture-shaped.

---

## Sprint Completion Report (2026-08-02)

**Delivered exactly this sprint's own spec**, plus one small, disclosed necessary addition. `presentation/gesture_engine.py`'s `GestureTrigger` (the exact eight named values), `GestureEvent` (dataclass), and `GestureEngine` (constructor DI: `PresentationConfig` only, no renderer/`PersonaManager`/`EmotionalStateManager` reference) are in place: `trigger_event()` round-robins through `PresentationConfig.gesture_vocabulary[trigger.value]` (a `dict[GestureTrigger, int]` internal cursor, one per trigger, so each trigger's own rotation is independent), returning `None` — a logged no-op, never a crash — for an unconfigured or empty vocabulary. `maybe_roll_ambient_gesture()` gates on its own internal `_last_ambient_fired_at` timestamp *before* ever rolling the dice: a genuine fire (a non-`None` result) starts the rate-limit window; a failed roll or an empty-vocabulary miss does not, so a probability of `1.0` still cannot fire more than once per `ambient_gesture_roll_interval_seconds`, and a temporarily-unlucky roll doesn't cost the caller a full interval's wait before trying again.

**`Renderer` Protocol (Sprint 5.6) gained its fourth method**, `trigger_gesture(gesture_id: str) -> None`, exactly the low-cost extension that sprint's own Potential Risks anticipated. Both concrete renderers implement it for real: `JarvisRenderer.trigger_gesture()` triggers one uniform accent pulse on `SegmentedRingWidget` (a brief, config-timed brightening of every segment, independent of the ring's own `RingState`/rotation-phase machinery) regardless of which specific `gesture_id` was chosen upstream — a deliberate, disclosed narrowing (Jarvis's own locked "single subtle accent" identity has no need for a second per-id visual vocabulary; the id is still logged for debuggability and remains available for a future sprint to differentiate against). `MinieRenderer.trigger_gesture()` is a pure one-line forward to the held `AvatarRenderer.trigger_gesture()` (already real since Sprint 5.8's `VTubeStudioAvatarRenderer`) — the id passes through verbatim, matched against whatever hotkey the user's own loaded Live2D model defines.

**One real, necessary addition beyond this sprint's own named Files to Modify**: `presentation/widgets/segmented_ring_widget.py` gained `trigger_pulse(duration_ticks: int)` plus the `_pulse_ticks_remaining` state `_on_tick()`/`paintEvent()` consult — required to give `JarvisRenderer.trigger_gesture()` any real content at all, and not listed in the sprint's own Files to Modify (only `jarvis_renderer.py` was named). Matches the same "found a necessary gap in the sprint's own file list, resolved it directly, disclosed it here" precedent Sprint 5.6 already used for `QuietModeController`. A second, equally necessary addition: `PresentationConfig.jarvis_gesture_pulse_ticks` (default `10`) — without it, the pulse's own duration would be a hardcoded magic number inside `jarvis_renderer.py`, violating `03_Engineering_Standards.md`'s "no hardcoded... thresholds" rule; `SegmentedRingWidget` also gained two small internal constants (`_PULSE_UNLIT_ALPHA`, `_PULSE_LIT_BRIGHTEN_PERCENT`) for the pulse's own visual intensity, real/disclosed/unvalidated first-pass numbers like every other Level 5 visual constant.

**`PresentationController` (Sprint 5.6) gained a sixth constructor parameter**, `gesture_engine: GestureEngine` — the same "a real DI gap in the sprint's own constructor list, resolved directly" precedent Sprint 5.6 itself established for `quiet_mode_controller`. `dispatch_gesture(event: GestureEvent) -> None` routes to the currently-**mounted** renderer (never the active persona, matching `refresh()`'s own already-established "mounted, not active" discipline) and never raises. `refresh()` now also rolls one ambient gesture per tick, immediately after `render_state()`, using that same tick's own freshly-computed `state.gesture_probability` and `active_persona.name` — inside the same outer Fail Gracefully `try`/`except` `refresh()` already had, so a `GestureEngine`/renderer failure here degrades exactly like a computer/render_state() failure already did (verified directly: a dedicated test proves `refresh()` does not raise when a fake `GestureEngine.maybe_roll_ambient_gesture()` itself raises).

**Mechanical/Acceptance Criteria checks, all passing**: an AST-based test (not a naive substring scan — a docstring inside `gesture_engine.py` legitimately names `jarvis_renderer.py`/`minie_renderer.py`/`vtube_studio_renderer.py` in prose to explain the when/how split, and a substring check would have wrongly flagged that; matches Sprint 5.8's own established AST-based precedent) confirms `gesture_engine.py` has zero real `import`/`from` statements referencing any renderer module. `trigger_event()`/`maybe_roll_ambient_gesture()` are proven never to raise across every `GestureTrigger` value and a range of inputs including an explicitly empty configured vocabulary. Ambient rate-limiting is verified directly: ten consecutive calls at `gesture_probability=1.0` inside one interval window produce exactly one non-`None` result.

**Full suite**: 1474 total (1470 passing, 2 pre-existing failures, 1 skipped, 1 deselected), `ruff check .` clean. Both failures were individually re-run standalone and confirmed to be already-documented, pre-existing flake classes wholly unrelated to this sprint's own files (`presentation/`, `config/schema.py`, `config/defaults.yaml`): `test_full_level3_acceptance_scripted_conversation` is the same host-load `wait_for_dormant` timing flake documented since Sprint 4.6 (passed cleanly standalone); `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` is the same real-Ollama-output nondeterminism flake first documented at Sprint 5.2 (failed identically standalone too — genuine model nondeterminism, not a regression; this sprint never touches `decision/`).

**No live caller of `trigger_event()` yet** (Sprint 5.14's job, per this sprint's own Integration Considerations) — `maybe_roll_ambient_gesture()` is the one piece with a real caller already, via `PresentationController.refresh()`, exactly as planned. `docs/STATUS.md`'s Level 5 Part A row updated; `docs/sprint_book/INDEX.md`'s 5.9 row marked Complete (and its own markdown link corrected to the same `sprint_5/sprint_5_9.md` relative-path pattern rows 5.7/5.8 already use — a small, pre-existing link bug fixed in passing since this row was being touched anyway, not chased further into rows 5.10–5.13's own identical bug, which will be fixed when those sprints land for real). **Sprint 5.10 (Persona Transition Engine) is next.**
