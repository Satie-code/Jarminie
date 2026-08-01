# Sprint 5.10 — Persona Transition Engine

## Sprint ID

5.10

## Sprint Name

Persona Transition Engine

## Purpose

Implement the brief's own locked persona-transition flow exactly:

```
Jarvis -> Save presentation state -> Synchronize memory -> Display JARMINEI Core
       -> Particle transition -> Load target renderer -> Restore conversation -> Continue naturally
```

No application restart. No conversation loss. No memory reset.

## Engineering Rationale

**New sprint.** The single most important thing to establish first: **conversation continuity and memory continuity across a persona switch are already real and already solid**, built entirely at Level 2/3 — `ConversationSessionStore`/`ContextManager` (Sprint 2.7/2.8) persist every turn regardless of active persona, `PersonaScopedMemory`'s Shared-memory layer (Sprint 3.2) is readable by both personas by construction, and `PersonaManager.select()`/`resume_previous()` (Sprint 2.11) already switch *which* persona answers the next turn with zero effect on any of that. **This sprint's own job is exclusively the visual/presentation choreography layered on top of already-guaranteed continuity — it is not where "no conversation loss, no memory reset" gets implemented, only where it gets honestly verified as still true and given a real transition animation to sit inside.** Treating "Synchronize memory" as a step this sprint must build from scratch would duplicate work Level 2/3 already did correctly; instead, this sprint's own `Synchronize memory` phase is a verification/logging checkpoint (confirms the already-current `ConversationContext` is available to the new renderer, logs it, does not re-fetch or re-persist anything) — the same "confirmed already correct, add a regression test proving it, don't rebuild it" judgment call Sprint 4.19's own hardening report already used for several of its six scenarios.

`PersonaManager` gains exactly one new constructor parameter — `on_switch: Callable[[str, str], None] | None = None`, invoked at the end of a successful `select()`/`resume_previous()` call with `(old_persona_name, new_persona_name)` — the identical "plain callable fixed at construction time" Dependency Injection shape `WakeWordDetector.on_detected`/`VoiceSessionManager.on_session_ended` already established (per that class's own docstring, quoted in Sprint 2.6's file: *"WakeWordDetector.on_detected and VoiceSessionManager's on_session_ended are both plain callables fixed at their own construction time... The actual Python-level wiring... happens where [they] are themselves assembled"* — the exact same pattern applies here, with the real wiring deferred to Sprint 5.14). `PersonaManager` itself gains no new knowledge of `TransitionEngine`, `Renderer`, or anything presentation-related — it only calls an opaque callback, preserving its own existing Single Responsibility (switching logic only) untouched.

## Objectives

- `presentation/transition_engine.py`: `TransitionEngine`, `TransitionPhase` enum (the seven locked flow steps), `TransitionOverlay` Protocol (a minimal, renderer-agnostic "show a brief in-between visual" seam, real implementation deferred to Sprint 5.14 so this sprint stays Qt-independent and fully unit-testable).
- `personas/persona_manager.py`: `on_switch` constructor parameter, invoked from `select()`/`resume_previous()`.
- A choreographed, bounded-duration sequence: nothing in this flow may block a live conversation turn indefinitely — a hard timeout on the whole sequence degrades to an instant renderer swap with no animation, never a hang (Fail Gracefully, exercised further at Sprint 5.15).

## Dependencies

5.7 (Jarvis Renderer), 5.8 (Minie Renderer & Avatar Renderer Interface), 2.11 (Persona Switching & Explicit Selection).

## Files to Create

- `presentation/transition_engine.py`
- `tests/unit/presentation/test_transition_engine.py`

## Files to Modify

- `personas/persona_manager.py` — `on_switch` constructor parameter; `select()`/`resume_previous()` invoke it after `_set_active()` succeeds, never before (the switch itself must already be real and committed before any presentation-side reaction fires).
- `tests/unit/personas/test_persona_manager.py` — `on_switch` invocation coverage (called with correct old/new names on a real switch; NOT called when `select()` is refused by priority; NOT called when `resume_previous()` has nothing to resume).
- `config/schema.py` — `PresentationConfig` gains `transition_max_duration_seconds: float = 2.5`, `transition_particle_phase_seconds: float = 0.8`.

## Expected Classes

- **`TransitionPhase`** (`Enum`): `SAVING_STATE`, `SYNCING_MEMORY`, `SHOWING_CORE`, `PARTICLE_TRANSITION`, `LOADING_TARGET`, `RESTORING_CONVERSATION`, `COMPLETE` — the brief's own seven-step flow, named directly, each one indiv­idually observable (for testing and for the overlay's own progress display).
- **`TransitionOverlay`** (`Protocol`): the minimal seam a real UI-layer overlay (Sprint 5.14) implements — kept separate from `Renderer` (5.6) since an overlay is transient scaffolding shown *during* a transition, not a persona's own ongoing presentation.
- **`TransitionEngine`**: constructor DI receives `PresentationController` (5.6) and an optional `TransitionOverlay` (defaults to a no-op/null overlay — `NullTransitionOverlay`, this sprint's own concrete no-op implementation — so `TransitionEngine` is fully testable with zero Qt dependency, the same "component before integration, real widget arrives later" discipline every prior presentation sprint used).

## Expected Interfaces

- **`TransitionOverlay`**: `show() -> None`, `set_phase(phase: TransitionPhase) -> None` (lets a real overlay display progress/a particle animation keyed to the current phase), `hide() -> None`.

## Expected Functions

- `TransitionEngine.transition(old_persona_name: str, new_persona_name: str) -> None` — never raises (Fail Gracefully; any phase's own internal failure is caught, logged, and the sequence jumps straight to `LOADING_TARGET`/`COMPLETE` rather than leaving the UI stuck mid-overlay). Runs the seven phases in order:
  1. `SAVING_STATE` — captures the outgoing renderer's last-known `PresentationState` (from `PresentationController`, for potential resume — e.g. if `old_persona_name` is resumed again shortly via `resume_previous()`, its presentation doesn't have to recompute from a cold, neutral starting point; stored in a small in-memory, per-persona-name cache this class owns).
  2. `SYNCING_MEMORY` — a verification checkpoint only (Engineering Rationale): confirms a fresh `ConversationContext`/active-persona read is available, logs it, performs no new I/O of its own.
  3. `SHOWING_CORE` — calls `overlay.set_phase(SHOWING_CORE)`; a real overlay shows a neutral, persona-less JARMINEI visual (not either persona's own renderer) at this point — this sprint does not build that neutral visual itself (Integration Considerations), only the phase signal driving it.
  4. `PARTICLE_TRANSITION` — calls `overlay.set_phase(PARTICLE_TRANSITION)`; held for `PresentationConfig.transition_particle_phase_seconds`.
  5. `LOADING_TARGET` — calls `PresentationController.mount_renderer(new_persona_name)` (Sprint 5.6's own existing method — this sprint is its first real caller).
  6. `RESTORING_CONVERSATION` — if a cached `PresentationState` exists for `new_persona_name` from a prior `SAVING_STATE` phase (i.e. this is a resume, not a first-time switch), applies it as the new renderer's own starting point via one immediate `render_state()` call, so the target persona doesn't visually "reset to neutral" on every resume.
  7. `COMPLETE` — calls `overlay.hide()`.
  The whole sequence is wrapped in a `transition_max_duration_seconds` budget (checked between phases, not preemptively interrupting a phase mid-flight) — a budget overrun skips straight to phase 5 (`LOADING_TARGET`) and 7 (`COMPLETE`), guaranteeing the renderer swap itself always eventually happens even if the animation choreography around it doesn't finish in time.
- `NullTransitionOverlay` — a real, concrete no-op `TransitionOverlay` (all three methods do nothing), this sprint's own default.

## Data Flow

```
PersonaManager.select() / .resume_previous()   (existing, Sprint 2.11)
        |
        v (on_switch callback, new this sprint)
TransitionEngine.transition(old_persona_name, new_persona_name)
        |
        +--> SAVING_STATE: cache PresentationController's last state for old_persona_name
        +--> SYNCING_MEMORY: verify ConversationContext availability (no-op I/O)
        +--> SHOWING_CORE: overlay.set_phase(...)
        +--> PARTICLE_TRANSITION: overlay.set_phase(...), held briefly
        +--> LOADING_TARGET: PresentationController.mount_renderer(new_persona_name)
        +--> RESTORING_CONVERSATION: replay cached state for new_persona_name, if any
        +--> COMPLETE: overlay.hide()
        |
        v
   (the actual next conversation turn proceeds entirely unaffected — this whole
    sequence never touches ConversationSessionStore/MemoryStore directly)
```

## Implementation Tasks

1. `personas/persona_manager.py` — `on_switch` parameter and invocation.
2. `config/schema.py`/`config/defaults.yaml` — new `PresentationConfig` timing fields.
3. `presentation/transition_engine.py` — `TransitionPhase`, `TransitionOverlay`, `NullTransitionOverlay`, `TransitionEngine`.
4. `tests/unit/personas/test_persona_manager.py` — `on_switch` invocation coverage.
5. `tests/unit/presentation/test_transition_engine.py` — full seven-phase sequence against a spy `TransitionOverlay` (asserts phase-call order); budget-overrun degrade path (a slow fake phase forces the skip-to-`LOADING_TARGET` behavior, verified `mount_renderer()` still gets called); resume-replay behavior (switch away then back, verify the second mount receives the cached state).

## Architecture Notes

**This sprint does not implement the real neutral "JARMINEI Core" visual, the real particle-rendering visual, or any Qt widget at all** — `TransitionOverlay` is a Protocol; `NullTransitionOverlay` is its only concrete implementation this sprint ships. A real, on-screen version (Sprint 5.14) is genuinely new Qt/`QPainter` work in the same spirit as Sprint 5.7's sphere/ring, deliberately deferred so this sprint's own choreography logic (ordering, timeout, resume-replay) is fully verifiable without a `QApplication` — the same "logic and rendering are separately testable" split every presentation sprint in this Level applies.

## Integration Considerations

- **`on_switch` has no real caller until Sprint 5.14** — `main.py`'s own `PersonaManager` construction is where the real `TransitionEngine.transition` bound method gets passed in.
- **A real `TransitionOverlay` (the actual neutral-core/particle visual) is Sprint 5.14's job**, built and embedded into `MainWindow` alongside the renderer-hosting work that sprint already has to do.
- Sprint 5.13 (Companion Experience)'s own greeting/idle behaviors run independently of transitions — a persona switch mid-greeting is not a case this sprint special-cases; `TransitionEngine.transition()`'s own bounded-duration guarantee is what keeps that interaction safe by construction (nothing can hang indefinitely regardless of what else is happening).

## Potential Risks

- **A transition triggered by a rapid double-switch** (the user changes their mind mid-animation) — this sprint's own `transition_max_duration_seconds` budget bounds how long any single transition can occupy, but a *second* `transition()` call arriving while the first is still in its particle phase is a real, named edge case explicitly deferred to Sprint 5.15's own hardening scenario list (interrupted-transition handling), not solved here.
- **`transition_particle_phase_seconds`/`transition_max_duration_seconds` are unvalidated timing guesses**, the same disclosed-default category as every other tuned constant in this Sprint Book.

## Acceptance Criteria

- `transition()` always calls `mount_renderer(new_persona_name)` exactly once per invocation, regardless of whether the full seven-phase choreography completes or the budget forces an early skip.
- `transition()` never raises for any overlay behavior, including an overlay whose methods themselves raise.
- `PersonaManager.select()`/`resume_previous()` invoke `on_switch` only on an actual, successful switch — never on a refused/no-op call.
- A resumed persona's renderer receives its previously-cached `PresentationState` as an immediate starting point, verified directly.
- `ruff check .` clean; full existing suite (including `PersonaManager`'s own pre-existing tests, unaffected by the new optional constructor parameter) still passes.

## Testing Checklist

- [ ] Unit: full seven-phase sequence, correct order, against a spy overlay.
- [ ] Unit: budget-overrun degrade path still calls `mount_renderer()`.
- [ ] Unit: resume-replay (switch away, switch back, cached state applied).
- [ ] Unit (regression): `PersonaManager.select()`/`resume_previous()` `on_switch` invocation correctness, including the refused/no-op negative cases.
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `presentation/transition_engine.py` module docstring quotes the brief's own locked seven-step flow directly and explains which steps are real work vs. verification checkpoints (Engineering Rationale).
- [ ] `personas/persona_manager.py`'s docstring updated to document `on_switch`'s new role, cross-referencing this sprint.
- [ ] `docs/STATUS.md` — Level 5 Part A row updated.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium–High.

## Estimated Development Time

2 days.

## Risks

See Potential Risks above.

## Next Sprint

5.11 — Voice Personality.

## Future Considerations

- Interrupted/overlapping transitions (Potential Risks above) — Sprint 5.15's job.
- The real neutral "JARMINEI Core"/particle overlay visual — Sprint 5.14's job.
