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

## Sprint Completion Report (2026-08-02)

Implemented as specified, authorized directly ("Continue with sprint 5.2") right after Sprint 5.1 closed in the same session.

### Summary

`emotion/state_manager.py` delivers `EmotionalState` (seven dimensions, neutral-midpoint defaults) and `EmotionalStateManager` (`apply_estimate()`, `decay_toward_baseline()`, `current_state()`), exactly per the spec's Expected Classes/Functions. `EmotionConfig` gained `state_smoothing_alpha`, `baseline_decay_half_life_seconds`, and `label_state_targets` (with real, disclosed default targets for all nine `EmotionLabel` values), each validated in `_validate_emotion()`.

One design ambiguity in the sprint file itself was resolved, not guessed silently: the Engineering Rationale's own EMA formula (`new_state = old_state * (1 - alpha) + target * alpha`) names `label_state_targets` as **target values**, while the Files to Modify section describes them as "target deltas." Implemented as target values (matching the formula, the more precise of the two descriptions) — a label's own dict names only the dimensions it meaningfully moves; dimensions it doesn't name are left untouched for that label, which is mathematically equivalent to "no delta" and reconciles both phrasings without contradiction. Documented in `config/schema.py`'s own `_default_label_state_targets()` docstring so this reading is explicit, not implicit.

`conversation_momentum` (Architecture Notes' own instruction: "folded into `apply_estimate()`'s own per-dimension logic," driven from `EmotionSignals.pause_before_turn_seconds`) is implemented as a dedicated step inside `apply_estimate()`, separate from the six `label_state_targets`-driven dimensions and from the `EmotionLabel.UNKNOWN` short-circuit — a short/absent pause pushes it up, a long one pulls it down, using the existing `EmotionConfig.long_pause_threshold_seconds` (Sprint 5.1) as the reference point rather than adding a redundant new threshold field. This means momentum genuinely updates even on an `UNKNOWN`-label turn (real pause data is still available and meaningful regardless of whether emotion classification succeeded) while the other six dimensions correctly stay untouched — both spec requirements ("UNKNOWN is a no-op" and "momentum reflects turn cadence") hold simultaneously without conflict.

`decay_toward_baseline()` implements a standard half-life exponential: `decay_factor = 0.5 ** (elapsed_seconds / half_life)`, applied per-dimension against each dimension's own neutral midpoint (`mood`→0, all others→50) — verified directly that exactly one half-life of elapsed time leaves ~50% of the original displacement remaining (`test_half_life_decays_approximately_halfway`), not just asserted in prose.

### Files Created

- `emotion/state_manager.py`
- `tests/unit/emotion/test_state_manager.py`

### Files Modified

- `config/schema.py` — `EmotionConfig` gains `state_smoothing_alpha`, `baseline_decay_half_life_seconds`, `label_state_targets` (+ `_default_label_state_targets()` factory and the module-level `_EMOTIONAL_STATE_DIMENSION_RANGES` constant, duplicated rather than imported from `emotion/` per this file's own established dependency-direction-leaf discipline); `_validate_emotion()` extended with bounds checks for all three new fields, including per-dimension range validation for `label_state_targets`.
- `config/defaults.yaml` — matching `emotion:` section additions.
- `tests/unit/config/test_schema.py` — 4 new validation tests.

### Tests Added

- `tests/unit/emotion/test_state_manager.py` — 21 tests: lifecycle; default-state neutrality; `current_state()` independent-copy defense; `apply_estimate()` (never raises on `UNKNOWN`, `UNKNOWN` leaves label-driven dimensions untouched, EMA converges monotonically without overshooting across 50 repeated identical estimates, low confidence nudges less than high confidence, dimension clamping holds under 200 repeated extreme estimates, short/long pause correctly move `conversation_momentum` in opposite directions, `updated_at` advances); `decay_toward_baseline()` (zero/negative elapsed is a no-op, decay genuinely pulls a displaced state back toward but not past neutral, longer elapsed decays more, one half-life leaves ~50% displacement remaining within 5% tolerance, clamping holds through decay, never raises on an extreme elapsed value).
- `tests/unit/config/test_schema.py` — `state_smoothing_alpha` out-of-range, non-positive `baseline_decay_half_life_seconds`, `label_state_targets` unknown-dimension key, `label_state_targets` out-of-range value.

### Documentation Updated

- `emotion/state_manager.py`'s module and class docstrings state the "gradual, not sentence-by-sentence" design goal, the "not a memory layer" boundary, and the process-wide (not per-session) state scope explicitly.
- `config/schema.py`'s `EmotionConfig` docstring extended with the three new fields' meaning/defaults.
- This Sprint Completion Report.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated (see below).

### Acceptance Criteria Checklist

- ✔ `EmotionalStateManager` never raises for any input, including repeated `UNKNOWN` estimates and a zero/negative `elapsed_seconds` — verified directly.
- ✔ A sustained run of consistent same-label estimates measurably moves the relevant dimension(s) toward that label's target, without ever exceeding the dimension's valid range — verified across 50 and 200-iteration runs.
- ✔ A long simulated idle gap measurably decays a displaced state back toward neutral — verified, including the half-life-specific quantitative check.
- ✔ `ruff check .` clean; full existing suite still passes.

### Risks

- `label_state_targets`/`state_smoothing_alpha`/`baseline_decay_half_life_seconds` are real, disclosed, unvalidated first-pass defaults (Potential Risks, unchanged from the spec) — correctable via config without a code change.
- No live caller yet — this sprint's own correctness is verified in isolation only; real behavior against a genuine sequence of live `EmotionEstimate`s from an actual conversation is Sprint 5.14's job.

### Technical Debt

None introduced.

### Recommendations

- Same as Sprint 5.1's own recommendation: once Sprint 5.14 wires a live caller, capture real `EmotionalState` trajectories from actual conversation sessions and sanity-check that the seven dimensions move in ways that feel right before tuning further.

### Verification

Full suite: 1173 passing + 2 correctly-skipped opt-in markers + 3 failures, all individually confirmed pre-existing and unrelated to this sprint's own `config/`/`emotion/` changes — `test_full_level2_acceptance_scripted_conversation`/`test_full_level3_acceptance_scripted_conversation` (the established "passes standalone, times out only under full-suite host-resource load" flake class; both confirmed 5/5 passing when run standalone together) and `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` (a real, opt-in Ollama-backed test whose own assertion depends on genuine live LLM output — confirmed via 3 standalone reruns to fail intermittently regardless of this sprint's changes, since `decision/context_analyzer.py`/`decision/llm_client.py` are untouched here; inherent real-model nondeterminism, not a regression). `ruff check .` clean across the whole repository. A real, non-mocked config-load smoke test confirmed `ConfigLoader().load()` genuinely picks up all three new `emotion:` YAML fields end-to-end.

**No git commit made** — per this project's own "only commit when explicitly asked" rule, changes left in the working tree; the user has not yet been asked whether to commit.

**Sprint 5.3 (Emotional Memory) is next.**
