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

## Sprint Completion Report (2026-08-02)

Implemented as specified, authorized directly ("continue with sprint 5.5") right after Sprint 5.4 closed in the same session.

### Summary

`presentation/presentation_state.py` gives JARMINEI the new top-level `presentation/` package's own middle architectural node: `PresentationState` (the nine brief-mandated fields, carrying no reference back to `EmotionalState`/`Intent`/`ContextAnalysis` — the structural enforcement of "renderers consume, never determine, emotion") and `PresentationStateComputer` (a `Protocol`, mirroring `SpeechToText`/`SearchProvider`'s own interface-first shape). `presentation/jarvis_state_computer.py`'s `JarvisPresentationStateComputer` and `presentation/minie_state_computer.py`'s `MiniePresentationStateComputer` each implement it: Jarvis pins five of six numeric fields to a fixed point within his own narrow, low `PresentationConfig` range (only `animation_speed` — inversely driven by `EmotionalState.stress` — and `avatar_focus` — driven by `OperatingMode` — genuinely move, per this sprint's own Expected Functions); Minie genuinely tracks `EmotionalState.comfort`/`.mood` (a blended "warmth" fraction driving `smile_intensity`/`eye_openness`/`voice_warmth`) and `.energy`/`.stress` (driving `animation_speed`/`particle_density`/`gesture_probability`) across a wide range on every field. `lighting_color`/`ui_accent` are fixed per persona (Jarvis electric-blue/cyan, Minie lavender/rose-gold), never emotion-driven, per this sprint's own Architecture Notes.

`config/schema.py`'s new `PresentationConfig` holds 28 fields: a `{persona}_{field}_min`/`{persona}_{field}_max` pair for each of six numeric dimensions × two personas, plus four locked hex-color fields. `AppConfig._validate_presentation()` validates every min/max pair against its field's own structural domain (0.0-1.0 for five dimensions, 0.5-2.0 for `animation_speed`) via a new shared `_validate_presentation_range()` helper (factored out since `_validate_resources()`'s own inline-loop precedent was applied to only four pairs, not twelve), plus a `#RRGGBB` hex-format check on all four color fields.

Two spec ambiguities were resolved explicitly, not guessed silently:

1. **`tuple[float, float]` as a config field type.** The spec's own Expected Classes describes each field as a "range," but no existing `AppConfig` section anywhere in this codebase uses a `tuple[...]` dataclass field — YAML has no native tuple type, and this project's config loader (`config/loader.py`) has no established round-trip handling for one (it would deserialize as a `list`, untested). Resolved by following `ResourceThresholds`'s own real, established precedent instead (separate `_warning_percent`/`_critical_percent` float fields) — each `PresentationState` field became a `_min`/`_max` float pair, verified to load correctly end-to-end via a real `ConfigLoader().load()` smoke test, not just constructed in Python.
2. **Minie's `animation_speed` formula: energy (Expected Functions) vs. stress (Potential Risks).** The spec's Expected Functions bullet says Minie's `animation_speed` is driven by `EmotionalState.energy`; its own Potential Risks section separately asserts the test expectation "higher stress -> lower `animation_speed` for both [personas]." A pure energy-only formula for Minie would satisfy the first and silently fail the second. Resolved with a blended fraction — `(energy_fraction + (1 - stress_fraction)) / 2` — satisfying both: energy still genuinely drives it (Expected Functions), and higher stress still lowers it (Potential Risks), verified directly by `test_higher_stress_produces_lower_animation_speed_for_both_personas`.

Additionally, `tests/unit/presentation/__init__.py` (named in this sprint's own Files to Create) was deliberately **not** created — `tests/` has had zero `__init__.py` files anywhere, by an established, explicitly documented convention since Sprint 1.1 (`tests/unit/personas/conftest.py`'s own docstring states it directly: "tests/ has no `__init__.py`, by convention"); creating one here would be the only exception in the entire suite, for no functional reason (pytest's own rootdir-relative test discovery needs none). `_select_tone_variant`-style module-private naming (`_clamp`, named directly in this sprint's own Expected Functions) was also revised: the spec's own naming implies a private helper, but it genuinely needs to be shared across two separate modules (`jarvis_state_computer.py`/`minie_state_computer.py`) — a real cross-module import of an underscore-prefixed name has zero precedent anywhere else in this codebase (confirmed by a repo-wide search), so `clamp`/`fraction_of`/`scale_into_range`/`avatar_focus_from_operating_mode` are public names in `presentation_state.py` instead, the same "public when genuinely shared across modules" convention every other cross-module helper in this codebase already follows.

`config/loader.py`'s `_SECTION_SCHEMAS` registration (Sprint 5.1's own disclosed "real gap found and closed beyond the sprint's own stated files" for `EmotionConfig`) was applied proactively here from the start, not found as a gap after the fact — `"presentation": PresentationConfig` was added alongside the `PresentationConfig` class itself in the same pass.

### Files Created

- `presentation/__init__.py`
- `presentation/presentation_state.py`
- `presentation/jarvis_state_computer.py`
- `presentation/minie_state_computer.py`
- `tests/unit/presentation/test_presentation_state.py`

**Not created**: `tests/unit/presentation/__init__.py` — see Summary above.

### Files Modified

- `config/schema.py` — new `PresentationConfig` dataclass, `AppConfig.presentation` field, `_validate_presentation()`, `_validate_presentation_range()`/`_HEX_COLOR_PATTERN` module-level helpers, `import re`.
- `config/defaults.yaml` — matching `presentation:` section.
- `config/loader.py` — `PresentationConfig` added to `_SECTION_SCHEMAS`. **Not named in the sprint file's own Files to Modify** — a real, necessary addition, same category as Sprint 5.1's own disclosed `EmotionConfig` gap (Summary above).
- `tests/unit/config/test_schema.py` — new `PresentationConfig` validation coverage. **Not named in the sprint file's own Files to Modify** — follows directly from the `config/schema.py` addition above.

### Tests Added

- `tests/unit/presentation/test_presentation_state.py` — 27 tests: every field within its documented range across a representative `EmotionalState`/`OperatingMode` spread and across every dimension's own structural extreme (including a "worst case, all dimensions at once" and "best case, all at once" pair); Jarvis's `particle_density`/`smile_intensity` observably (and structurally, by config construction) lower than Minie's across every representative input; higher stress produces lower `animation_speed` for both personas; `avatar_focus` responds correctly to `OperatingMode` for both; Minie's `smile_intensity`/`eye_openness`/`voice_warmth` genuinely increase with comfort/mood, `particle_density` genuinely increases with energy; Jarvis's `smile_intensity`/`particle_density` provably do NOT move with emotional input (pinned); both personas' colors are fixed regardless of emotional state; `persona_name`/`computed_at` correctness; a genuinely-config-driven proof (a custom `PresentationConfig` changes Minie's actual output range); never-raises sweep; direct unit coverage of the shared `clamp`/`fraction_of`/`scale_into_range` helpers.
- `tests/unit/config/test_schema.py` — 9 new tests: defaults are valid; unit-range fields below 0.0/above 1.0 raise (parametrized); min > max raises; `animation_speed` below 0.5/above 2.0 raises (parametrized); invalid hex color (both a garbage string and a missing leading `#`) raises; the shipped Jarvis/Minie particle-density and smile-intensity ranges are confirmed non-overlapping at the config level directly.

### Documentation Updated

- `presentation/presentation_state.py`'s module docstring (the "renderers consume, never determine, emotion" boundary, stated explicitly).
- `presentation/jarvis_state_computer.py`'s/`presentation/minie_state_computer.py`'s own module docstrings (each formula's reasoning, including the two resolved ambiguities above).
- `config/schema.py`'s `PresentationConfig` docstring (field-family meaning/range/persona-applicability, the locked-palette rationale).
- This Sprint Completion Report.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated (see below).

### Acceptance Criteria Checklist

- ✔ Every `PresentationState` field always within its documented valid range for both computers, verified across a representative spread AND every dimension's own structural extreme (including combined worst/best cases).
- ✔ Jarvis's `particle_density`/`smile_intensity` stay observably lower than Minie's across matched inputs — verified as a real per-input comparison AND as a structural config-level guarantee (Jarvis's own range ceiling sits below Minie's own range floor).
- ✔ `ruff check .` clean; full existing suite unaffected (net-new files/config only — no existing production code path touches `presentation/` yet).

### Risks

- Same "two independent formulas risk drifting inconsistently" risk named in the spec — mitigated as designed (shared `clamp`/`fraction_of`/`scale_into_range`/`avatar_focus_from_operating_mode` helpers, plus a dedicated cross-persona direction-consistency test for `animation_speed`/stress).
- The exact hex colors and numeric ranges are real, disclosed, unvalidated first-pass content choices — same category as every other Level 5 config default so far (Sprints 5.1-5.4's own thresholds), correctable via config without a code change.
- No live caller yet — Sprint 5.6 (`PresentationController`) is the very next sprint specifically to close this gap, the tightest component-then-integration gap in this Sprint Book by the spec's own admission.

### Technical Debt

None introduced. The `config/loader.py` `_SECTION_SCHEMAS` registration was done proactively within this sprint, not deferred or found later.

### Recommendations

- Once Sprint 5.6 wires a live `PresentationController` caller, sanity-check the shipped ranges/colors against a real rendered output (even a placeholder renderer) before considering them tuned — same "real usage before tuning further" recommendation every prior Level 5 sprint has made for its own first-pass numbers.
- Whether Minie's `gesture_probability` formula (a disclosed implementation-time choice, not individually specified by this sprint's own Expected Functions) should instead be tuned by whoever builds Sprint 5.9's `GestureEngine`, once real gesture-trigger behavior is observable, is a real open question — not decided here.

### Verification

Full suite: 1326 passing + 2 pre-existing failures (both individually confirmed unrelated to this sprint — the same already-established host-load `wait_for_dormant` timing flake class documented since Sprint 4.6, this run surfacing in `test_level3_acceptance.py`/`test_level4_part_a_acceptance.py`, reconfirmed passing standalone this session; `presentation/` is a brand-new, entirely unwired package with no live caller anywhere, structurally incapable of causing a live-turn timing flake) + 1 skipped + 1 deselected. `ruff check .` clean across the whole repository. A real, non-mocked config-load smoke test (`ConfigLoader().load()`) confirmed the new `PresentationConfig` fields genuinely load end-to-end with their shipped defaults.

**No git commit made** — per this project's own "only commit when explicitly asked" rule, changes left in the working tree; the user has not yet been asked whether to commit.

**Sprint 5.6 (Presentation Layer Foundation & Renderer Interface) is next.**
