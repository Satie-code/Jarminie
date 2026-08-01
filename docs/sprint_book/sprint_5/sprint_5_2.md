# Sprint 5.2 — Emotional State Manager

## Sprint ID

5.2

## Sprint Name

Emotional State Manager

## Purpose

Turn Sprint 5.1's per-turn `EmotionEstimate` into a **continuous, slowly-evolving emotional state** — the brief's own explicit requirement that mood/energy/stress/focus/comfort/social-energy/conversation-momentum "evolve gradually. Not sentence-by-sentence." This is the single read model every later Part A sprint (Persona Behavioral Adaptation, Presentation State Engine, Gesture Engine, Companion Experience) consults — none of them read `EmotionEstimate` directly.

## Engineering Rationale

**New sprint**, the direct, intended consumer Sprint 5.1's own Integration Considerations named. Two design choices made explicitly:

1. **Bounded exponential moving average, not a raw running average or a snap-to-latest.** A raw running average never forgets an outlier from hours ago; snapping to the latest estimate violates the brief's own "not sentence-by-sentence" requirement outright. An EMA (`new_state = old_state * (1 - alpha) + target * alpha`, `EmotionConfig.state_smoothing_alpha`, small by default) gives recent turns more weight than old ones while still requiring several consistent turns to move the state meaningfully — the same "smoothed, not reactive" shape `ResourceMonitor`'s own sampling (Sprint 1.4) uses for a different reason (avoiding false CRITICAL alarms from one noisy sample).
2. **Idle decay toward a neutral baseline, not permanent state.** Without decay, a stress spike from an hour-old conversation would still be silently coloring a brand new session. `decay_toward_baseline(elapsed_seconds)` — called once per turn using the real gap since the previous turn (`ConversationContext.last_activity_at`, already available) — pulls every dimension a fraction of the way back toward its neutral midpoint, proportional to elapsed time, so a long gap (a new day, a new session) naturally returns the state close to neutral without an arbitrary "reset on session start" special case.

## Objectives

- `emotion/state_manager.py`: `EmotionalState` dataclass (seven named dimensions) and `EmotionalStateManager` (`ManagedModule`).
- `apply_estimate()`: bounded EMA nudge from one `EmotionEstimate` toward that estimate's implied target state.
- `decay_toward_baseline()`: proportional pull back toward neutral, given elapsed real time.
- `current_state()`: the read accessor every later sprint uses.
- `EmotionConfig` (Sprint 5.1, this sprint extends it) gains `state_smoothing_alpha`, `baseline_decay_half_life_seconds`, and the `EmotionLabel -> target state deltas` mapping.

## Dependencies

5.1 (Emotion Detection Engine).

## Files to Create

- `emotion/state_manager.py`
- `tests/unit/emotion/test_state_manager.py`

## Files to Modify

- `config/schema.py` — `EmotionConfig` gains `state_smoothing_alpha: float = 0.15`, `baseline_decay_half_life_seconds: float = 1800.0` (30 minutes), `label_state_targets: dict[str, dict[str, float]]` (per-`EmotionLabel.value`, per-dimension target deltas — e.g. `STRESSED` pushes `stress` up and `comfort` down, `EXCITED` pushes `energy` and `mood` up); `_validate_emotion()` extended with bounds checks (`0 < state_smoothing_alpha <= 1`, `baseline_decay_half_life_seconds > 0`).
- `config/defaults.yaml` — matching new fields.

## Expected Classes

- **`EmotionalState`** (dataclass): `mood: float` (-100..100, negative..positive), `energy: float` (0..100), `stress: float` (0..100), `focus: float` (0..100), `comfort: float` (0..100), `social_energy: float` (0..100), `conversation_momentum: float` (0..100, "how engaged/flowing does this conversation feel" — distinct from `energy`, which is about the user, not the conversation itself), `updated_at: datetime`. All seven dimensions start at their neutral midpoint (`mood=0`, the rest `=50`) at construction — an honest "no read yet" starting point, not an assumed-positive or assumed-negative default.
- **`EmotionalStateManager`** (`ManagedModule`): constructor DI receives only `EmotionConfig`. Holds exactly one `EmotionalState` internally (this project's Emotional State is process-wide, not per-session — Part 2's own Emotional Memory language ("long-term emotional context") implies continuity across sessions, which a per-session-scoped state would break; session-scoped *history* of state snapshots, if ever needed, is Sprint 5.3's/Part B's job, not this class's).

## Expected Interfaces

None new — `EmotionalStateManager` implements `ManagedModule`.

## Expected Functions

- `EmotionalStateManager.start()`/`.stop()`/`.health_check()` — `health_check()` always `True` once started (no external resource), same shape as Sprint 5.1's engine.
- `EmotionalStateManager.current_state() -> EmotionalState` — returns a **copy** (`dataclasses.replace()`), never the live internal object, so a caller can't accidentally mutate shared state out from under this manager — the same defensive-copy discipline `ConfidenceScorer.score()`'s own `replace()` usage (Sprint 3.5) already established for a different dataclass.
- `EmotionalStateManager.apply_estimate(estimate: EmotionEstimate) -> EmotionalState` — never raises (an `EmotionLabel.UNKNOWN`/low-confidence estimate is a deliberate no-op, logged at DEBUG, not an error); looks up `EmotionConfig.label_state_targets[estimate.label.value]`, computes a confidence-scaled target (a low-confidence estimate nudges less, never zero-or-full), applies the bounded EMA per dimension, clamps every dimension to its valid range, returns the new state.
- `EmotionalStateManager.decay_toward_baseline(elapsed_seconds: float) -> EmotionalState` — never raises (negative/zero `elapsed_seconds`, e.g. a clock anomaly, is treated as zero elapsed — a no-op, not an error); exponential decay per dimension toward its neutral midpoint using `baseline_decay_half_life_seconds`.

## Data Flow

```
Sprint 5.1's EmotionEstimate
        |
        v
EmotionalStateManager.apply_estimate()  -->  EmotionalState (mutated, bounded EMA)
        |
   (on the SAME turn, called once, in this order:)
        v
EmotionalStateManager.decay_toward_baseline(elapsed_since_last_turn)  -->  EmotionalState
        |
        v
   EmotionalStateManager.current_state()  <-- read by 5.4, 5.5, 5.9, 5.13 (not this sprint)
```

Decay is applied **before** the new estimate's nudge within a single turn-processing call (the caller — Sprint 5.14's real integration — calls `decay_toward_baseline()` then `apply_estimate()` in that order), so a long-idle gap correctly pulls state toward neutral before the fresh turn's own signal is layered on, rather than the reverse (which would apply decay after fresh, more-relevant data — the wrong order for "recent signal should always win").

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — extend `EmotionConfig` per Files to Modify, with a real, reasoned default `label_state_targets` for all nine labels.
2. `emotion/state_manager.py` — `EmotionalState`, `EmotionalStateManager` per Expected Functions.
3. `tests/unit/emotion/test_state_manager.py` — EMA convergence over repeated identical estimates (state should approach but never overshoot the target); a single low-confidence estimate produces a small nudge; decay pulls a displaced state back toward neutral over simulated elapsed time; dimension clamping at range boundaries; `UNKNOWN`/sub-threshold estimates are genuine no-ops.

## Architecture Notes

`EmotionalStateManager` is deliberately **not** a memory layer — it holds exactly one live, in-memory `EmotionalState`, with no persistence of its own and no history. Persisting emotionally-significant *moments* (not the continuous state itself) is Sprint 5.3's distinct responsibility; conflating the two would make this class do two things (Single Responsibility).

`conversation_momentum` is the one dimension `apply_estimate()`/`decay_toward_baseline()` alone cannot fully drive — it is more naturally informed by turn *frequency* (many turns in quick succession = high momentum) than by a single estimate's emotional label. This sprint gives it a small, explicit contribution from `EmotionSignals.pause_before_turn_seconds` (a short pause pushes momentum up, a long one decays it down, folded into `apply_estimate()`'s own per-dimension logic) — not a separate class, to avoid over-fragmenting seven closely related dimensions into their own bespoke update paths.

## Integration Considerations

- **No live caller until Sprint 5.14**, same "component before integration" precedent as every prior sprint's own first component sprint.
- Sprint 5.3 (Emotional Memory) reads `current_state()` at the moment of writing a significant-moment record — a snapshot, not a subscription; `EmotionalStateManager` gains no observer/callback mechanism this sprint (no real need for one yet — avoids speculative complexity).
- Sprint 5.4 (Persona Behavioral Adaptation) and Sprint 5.5 (Presentation State Engine) both take `EmotionalState` as a plain constructor/method parameter, never importing `EmotionalStateManager` itself where a read-only snapshot suffices — keeps their own tests simple (a plain dataclass fixture, no manager to construct).

## Potential Risks

- **Tuning the default `label_state_targets`/`state_smoothing_alpha`/decay half-life is a real, unvalidated guess** — the same honestly-acknowledged category as `MemoryConfig`'s five Dynamic Memory Formula weights or `VoiceConfig.wake_word_sensitivity`: a documented starting point, not a validated constant, correctable without a code change since it's config-driven.
- **Seven dimensions risk feeling arbitrary without real usage data** — mitigated by keeping every dimension's current value and its derivation fully inspectable (`current_state()` returns real numbers, not an opaque score), so a future tuning pass has something concrete to look at.
- **Process-wide (not per-user) state is a real simplification** — acceptable since JARMINEI Part 1/2 describe a single-user companion, not a multi-user system; flagged here so a future multi-profile feature (explicitly named as out-of-scope Future Roadmap territory in `04_Master_Implementation_Plan.md`) knows this class would need real rework, not just a new constructor parameter.

## Acceptance Criteria

- `EmotionalStateManager` never raises for any input, including repeated `UNKNOWN` estimates and a zero/negative `elapsed_seconds`.
- A sustained run of consistent same-label estimates measurably moves the relevant dimension(s) toward that label's target, without ever exceeding the dimension's valid range.
- A long simulated idle gap measurably decays a displaced state back toward neutral.
- `ruff check .` clean; full existing suite still passes.

## Testing Checklist

- [ ] Unit: EMA convergence behavior (monotonic approach to target under repeated identical input, bounded, never overshoots).
- [ ] Unit: decay behavior (proportional pull toward neutral, longer elapsed time = more pull, zero elapsed = no-op).
- [ ] Unit: dimension clamping at both range boundaries.
- [ ] Unit: `current_state()` returns an independent copy (mutating the returned object does not affect internal state).
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `emotion/state_manager.py` module docstring explains the "gradual, not sentence-by-sentence" design goal and why (the brief's own explicit requirement).
- [ ] `config/schema.py`'s `EmotionConfig` docstring extended with the new fields' meaning and defaults.
- [ ] `docs/STATUS.md` — Level 5 Part A row updated.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.3 — Emotional Memory.

## Future Considerations

- If a future sprint genuinely needs emotional-state *history* (not just the current snapshot), that is new scope for whichever sprint needs it — not built speculatively here.
- A push/subscribe mechanism (renderers reacting to a state change immediately rather than being polled) is a plausible future refinement once Sprint 5.6's `PresentationController` exists and a real latency problem with polling is observed — not built ahead of that evidence.
