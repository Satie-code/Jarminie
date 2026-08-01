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
