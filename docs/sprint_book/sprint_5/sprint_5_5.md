# Sprint 5.5 — Presentation State Engine

## Sprint ID

5.5

## Sprint Name

Presentation State Engine

## Purpose

Build the intermediate `PresentationState` layer the brief mandates explicitly: renderers "consume this state. They do not determine emotion themselves." This sprint computes, from `EmotionalState` (5.2) and the active persona, one concrete, renderer-agnostic set of numeric/enum outputs (smile intensity, eye openness, voice warmth, animation speed, particle density, lighting color, UI accent, gesture probability, avatar focus) — and nothing that renders anything. This is the seam the brief's own architecture diagram names directly: `Persona Controller -> Presentation State -> Renderer Interface -> {Jarvis Renderer, Minie Renderer}`. This sprint delivers the middle node; Sprint 5.6 delivers the two nodes around it.

## Engineering Rationale

**New sprint**, and the most consequential naming/architecture decision in Level 5 Part A, made explicitly via `AskUserQuestion` before this Sprint Book was written (see `docs/sprint_book/INDEX.md`'s "Level 5 breakdown changes" note): the brief's own diagram names the top node "Persona Controller," but this codebase already has a `PersonaManager` (`personas/persona_manager.py`, Sprint 2.11) owning *which* persona is active and *why* — a second class named similarly would be exactly the kind of avoidable ambiguity this project's own naming conventions exist to prevent. **This sprint builds the computation the brief calls "Presentation State"; Sprint 5.6 builds the coordinator (named `PresentationController`, not `PersonaController`) that calls it and dispatches the result to a renderer.** Splitting "compute the state" from "coordinate + dispatch" across two sprints (rather than one) mirrors this project's own repeated precedent for keeping computation and orchestration in separate, independently testable units (e.g. `ConfidenceScorer.score()` — pure computation — vs. `MemoryLifecycleManager` — orchestration that calls it).

`PresentationState` is deliberately **persona-agnostic in shape** (the same nine fields exist regardless of which persona is active) but **persona-aware in computation** (Jarvis and Minie map the same `EmotionalState` to different numeric ranges/defaults, per the brief's own locked visual identities — Jarvis "minimal, confident, deliberate," Minie "warm, expressive, gentle") — a `PresentationStateComputer` Protocol with one implementation per persona, the same interface-first shape `SpeechToText`/`SearchProvider` already established, chosen here because a third persona is not a stated goal of this project but the *mapping* genuinely differs enough per persona that a single shared formula would either be bland for both or require ad hoc persona-name branching inside one method — the Protocol keeps each persona's own mapping logic in its own reviewable unit.

## Objectives

- `presentation/__init__.py` — the new top-level package (see `docs/sprint_book/INDEX.md`'s breakdown note for why it's new, not an existing folder).
- `presentation/presentation_state.py`: `PresentationState` dataclass (the nine brief-mandated fields) and `PresentationStateComputer` Protocol.
- `presentation/jarvis_state_computer.py` / `presentation/minie_state_computer.py`: one concrete `PresentationStateComputer` per persona.
- `config/schema.py`: new `PresentationConfig` dataclass (per-persona baseline/range values for each `PresentationState` field).

## Dependencies

5.2 (Emotional State Manager), 5.4 (Persona Behavioral Adaptation — for the persona-identity/tone concepts this sprint's computers build on, though this sprint has no direct code dependency on `personas/`'s own files).

## Files to Create

- `presentation/__init__.py`
- `presentation/presentation_state.py`
- `presentation/jarvis_state_computer.py`
- `presentation/minie_state_computer.py`
- `tests/unit/presentation/__init__.py`
- `tests/unit/presentation/test_presentation_state.py`

## Files to Modify

- `config/schema.py` — new `PresentationConfig` dataclass, `AppConfig.presentation` field, `_validate_presentation()`.
- `config/defaults.yaml` — matching `presentation:` section.

## Expected Classes

- **`PresentationState`** (dataclass, `presentation/presentation_state.py`): `smile_intensity: float` (0.0–1.0), `eye_openness: float` (0.0–1.0), `voice_warmth: float` (0.0–1.0), `animation_speed: float` (0.5–2.0, a multiplier against each renderer's own base animation timing — `1.0` is neutral/default speed), `particle_density: float` (0.0–1.0), `lighting_color: str` (a hex color string, e.g. `"#3AA0FF"` — Jarvis's electric blue / Minie's lavender-warm-white-rose-gold palette, both locked in the brief), `ui_accent: str` (hex color string, the same locked palettes), `gesture_probability: float` (0.0–1.0, read by Sprint 5.9's `GestureEngine` as a roll threshold, not decided by this class), `avatar_focus: str` (an enum-like string — `"user"`/`"task"`/`"idle"`, coarse attention target), `computed_at: datetime`, `persona_name: str` (which persona this state was computed for — carried along so a renderer receiving a stale/mismatched state can detect and discard it, a defensive check exercised in Sprint 5.15).
- **`PresentationStateComputer`** (`Protocol`): `compute(emotional_state: EmotionalState, operating_mode: OperatingMode) -> PresentationState`. Interface-first per `03_Engineering_Standards.md` — mirrors `SpeechToText`/`TextToSpeech`/`SearchProvider`'s own established shape exactly.
- **`JarvisPresentationStateComputer`** / **`MiniePresentationStateComputer`**: each implements `PresentationStateComputer`, constructor DI over `PresentationConfig`.

## Expected Interfaces

`PresentationStateComputer` (above) — the first of two Protocols this Level introduces (the second, `Renderer`, is Sprint 5.6's).

## Expected Functions

- `JarvisPresentationStateComputer.compute(emotional_state, operating_mode) -> PresentationState` — Jarvis's own locked visual identity ("Minimal. Confident. Adaptive... smooth, deliberate, purposeful [animations]. No flashy cyberpunk effects.") is expressed as: a narrower numeric range on every field than Minie's own computer uses (config-driven — `PresentationConfig.jarvis_animation_speed_range`, etc.), `smile_intensity`/`particle_density` pinned low by default (Jarvis's dashboard has no face to smile with and the brief explicitly rules out "flashy" particle effects for him), `lighting_color`/`ui_accent` fixed to the locked electric-blue/cyan palette (not emotion-driven — the brief locks Jarvis's palette; only `animation_speed` and `avatar_focus` meaningfully move with `EmotionalState`/`OperatingMode` for this persona), `avatar_focus` driven primarily by `operating_mode` (`DORMANT` -> `"idle"`, `ACTIVE` -> `"user"`, a device-control/workflow turn in progress -> `"task"` — this last case a stub returning `"user"` until Sprint 5.12 gives it a real signal).
- `MiniePresentationStateComputer.compute(emotional_state, operating_mode) -> PresentationState` — Minie's own locked identity ("Warm. Comforting. Expressive... breathing, blinking, looking around, head tilts, small smiles") maps `EmotionalState.comfort`/`.mood` directly onto `smile_intensity`/`eye_openness`/`voice_warmth` (higher comfort/mood -> warmer, more open, more expressive), `EmotionalState.energy` onto `animation_speed`/`particle_density` (gentle particle ambiance scales with energy, never Jarvis's near-zero default), `lighting_color`/`ui_accent` fixed to the locked lavender/warm-white/rose-gold/soft-teal palette.
- `_clamp(value, low, high) -> float` (module-private, shared helper) — every computed field is clamped to its documented valid range before being placed on `PresentationState`, the same defensive-bounds discipline `EmotionalState`'s own dimension clamping (Sprint 5.2) already established.

## Data Flow

```
EmotionalState (5.2, a snapshot)  +  OperatingMode (existing, voice/quiet_mode.py)
        |
        v
{Jarvis,Minie}PresentationStateComputer.compute()
        |
        v
PresentationState  (persona-agnostic in shape, persona-aware in values)
        |
        v
   (consumed by Sprint 5.6's PresentationController, which selects WHICH
    computer to call based on PersonaManager.active_persona() — not this
    sprint's own responsibility)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `PresentationConfig`: per-persona baseline/range fields for every `PresentationState` dimension, plus the two locked hex-color palettes (`jarvis_lighting_color`/`jarvis_ui_accent`/`minie_lighting_color`/`minie_ui_accent` — the brief's own named colors, e.g. electric blue `#0A84FF`-family for Jarvis, lavender `#C8A8E9`-family for Minie, exact hex values a real, reviewable content choice made at implementation time, not fabricated here); `_validate_presentation()`.
2. `presentation/__init__.py`, `presentation/presentation_state.py` — `PresentationState`, `PresentationStateComputer`.
3. `presentation/jarvis_state_computer.py`, `presentation/minie_state_computer.py`.
4. `tests/unit/presentation/test_presentation_state.py` — both computers across a representative spread of `EmotionalState`/`OperatingMode` fixtures; every field's range respected; Jarvis's own "flashy effects ruled out" constraint verified concretely (e.g. `particle_density` never exceeds a configured low ceiling for Jarvis, unlike Minie).

## Architecture Notes

**"Renderers consume this state. They do not determine emotion themselves"** is enforced by `PresentationState` carrying no reference back to `EmotionalState`, `Intent`, or `ContextAnalysis` — a renderer given only a `PresentationState` object structurally cannot re-derive or second-guess the emotional read that produced it, matching the brief's own explicit intent.

`lighting_color`/`ui_accent` being **fixed per persona rather than emotion-driven** is a deliberate reading of the brief: it names specific locked colors per persona ("Dark theme, Electric blue, Cyan accents" for Jarvis; "Lavender, Warm white, Rose gold, Soft teal" for Minie) as identity, not as a mood ring — only the *values that render* (particle density, animation speed, smile/eye/warmth) are emotion-driven. If a future sprint wants genuine color-shifts-with-mood, that is a real, separate design decision for whoever proposes it, not assumed here.

## Integration Considerations

- **No live caller until Sprint 5.6** builds `PresentationController`, the very next sprint — the tightest "component then integration" gap in this Sprint Book, since 5.5/5.6 are two halves of one architectural seam split for testability, not for a long standalone lifespan.
- Sprint 5.7/5.8 (Jarvis/Minie Renderer) are `PresentationState`'s real terminal consumers — they receive it already-computed, never calling either `PresentationStateComputer` themselves.
- Sprint 5.9 (Gesture Engine) reads `gesture_probability` as one of several inputs to its own trigger logic — a probability, not a command; the Gesture Engine still decides whether/when to actually fire.

## Potential Risks

- **Two independent per-persona formulas risk drifting inconsistently** (e.g. Jarvis and Minie disagreeing about what "high stress" should visually mean) — mitigated by both computers sharing the same `EmotionalState` input shape and the same `_clamp()` helper, and by this sprint's own tests asserting both computers respond in the same *direction* (e.g. higher stress -> lower `animation_speed` for both) even though magnitudes differ.
- **Locked color palettes are content decisions this Sprint Book names in prose but must still be chosen as real hex values at implementation time** — flagged explicitly rather than silently guessed at spec-writing time; not a blocking gate (unlike Sprint 5.8's VTube Studio client choice), since any reasonable value within the named color family is acceptable and correctable via config without a code change.

## Acceptance Criteria

- Every `PresentationState` field is always within its documented valid range for both computers, across the full range of possible `EmotionalState`/`OperatingMode` inputs.
- Jarvis's computed `particle_density`/`smile_intensity` stay observably lower than Minie's across matched inputs (the brief's "no flashy effects for Jarvis" / "expressive" for Minie, verified concretely).
- `ruff check .` clean; full existing suite unaffected (net-new files/config only).

## Testing Checklist

- [ ] Unit: both computers across representative `EmotionalState` fixtures (neutral, high-stress, high-comfort, low-energy).
- [ ] Unit: range/clamping enforcement at both boundaries for every field.
- [ ] Unit: `operating_mode`'s effect on `avatar_focus` for both personas.
- [ ] Unit: `PresentationConfig` validation.
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `presentation/presentation_state.py` module docstring states the "renderers consume, never determine, emotion" boundary explicitly.
- [ ] `config/schema.py`'s `PresentationConfig` docstring documents every field's meaning, range, and which persona it applies to.
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

5.6 — Presentation Layer Foundation & Renderer Interface.

## Future Considerations

- Genuine mood-driven color shifts (Potential Risks/Architecture Notes above) — a real future product decision, not assumed or built here.
- A third persona would need its own `PresentationStateComputer` implementation only — no change to `PresentationState`'s own shape or to any existing computer, confirming the Protocol split was the right call.
