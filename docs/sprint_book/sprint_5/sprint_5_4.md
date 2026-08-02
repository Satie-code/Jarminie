# Sprint 5.4 — Persona Behavioral Adaptation

## Sprint ID

5.4

## Sprint Name

Persona Behavioral Adaptation

## Purpose

Let the user's emotional state genuinely influence *what Jarvis and Minie say and how*, within each persona's own existing template-based `compose_reply()` — never by adding a new reasoning system. This is the sprint that makes "presentation reflects emotion" true at the language layer (voice/visual presentation is Sprint 5.5 onward); it is also where `EngineSelection.EMOTION_SUPPORT` — reserved in `decision/authority.py` since Sprint 3.11 with an explicit "Level 5 (Emotion Engine)" comment — finally gets a real handler.

## Engineering Rationale

**New sprint.** Two design choices made explicitly:

1. **Adaptation happens inside `compose_reply()`'s existing template mechanism, never as a new LLM call.** `personas/base.py`'s own docstring is unambiguous: `compose_reply()` "is still template-based, not a new LLM call of its own... there is no separate Level 3 'Execution Engine' to build." This sprint must not become one. `JarvisPersona`/`MiniePersona.compose_reply()` (Sprint 2.9/2.10) each gain a new, optional `emotional_state: EmotionalState | None` parameter; each persona's own existing phrasing/template selection logic consults it to pick among already-existing tone variants (e.g. a warmer opening line when `comfort` is low, more concise phrasing when `stress` is high) — never to generate new text an LLM would have to produce. This is the literal meaning of the brief's own locked rule: **"Presentation never changes intelligence."**
2. **`EMOTION_SUPPORT` routing is narrow and additive**, mirroring every prior `_determine_engine()` extension exactly (Sprint 4.11's `DEVICE_CONTROL`/`WORKFLOW`, Sprint 4.18's `SCHEDULER`/`INTERNET_AGENT`): `decision/models.py`'s `IntentCategory.EMOTIONAL_SUPPORT` (already exists, unused since Sprint 3.7) now routes to `EngineSelection.EMOTION_SUPPORT` when the Authority level is `RECOMMEND` or higher; `CommunicationPipeline` (Sprint 5.14's job, not this sprint's) will handle it by calling the adapted `compose_reply()` path rather than a distinct execution branch — `EMOTION_SUPPORT` selects a *style* of `CONVERSATIONAL_RESPONSE`, not a different subsystem, an important distinction from `DEVICE_CONTROL`/`SCHEDULER`, which really do dispatch elsewhere.

## Objectives

- `personas/base.py`: `Persona.compose_reply()`'s signature gains `emotional_state: EmotionalState | None = None`.
- `personas/jarvis.py`/`personas/minie.py`: each persona's own template selection consults `emotional_state` for tone/warmth/pacing variation within its existing phrasing.
- `personas/persona_manager.py`: `PersonaManager.compose_reply_safely()` gains the same new parameter, passed through unchanged.
- `decision/authority.py`: `_determine_engine()` gains real `EMOTION_SUPPORT` routing for `IntentCategory.EMOTIONAL_SUPPORT`.
- Never changes factual content, never fabricates claims about the user's feelings out loud as certainty (see Architecture Notes on the "never pretends to possess human emotions" / "behavioral estimation only" rule).

## Dependencies

5.2 (Emotional State Manager), 2.9/2.10 (Jarvis/Minie Persona), 3.11 (Authority Evaluation & Engine Selection).

## Files to Create

None — this sprint extends existing files only.

## Files to Modify

- `personas/base.py` — `Persona.compose_reply()` signature.
- `personas/jarvis.py` — template selection consults `emotional_state`.
- `personas/minie.py` — template selection consults `emotional_state` (Minie's own "wellness, emotional awareness" mandate per `project_jarminei_architecture.md`'s Persona System line makes this persona the primary beneficiary, though both personas participate).
- `personas/persona_manager.py` — `compose_reply_safely()` passes the new parameter through.
- `decision/authority.py` — `_determine_engine()` real `EMOTION_SUPPORT` branch; `EngineSelection.EMOTION_SUPPORT`'s own docstring comment ("reserved: Level 5 (Emotion Engine)") updated to "wired: <this sprint>."
- `tests/unit/personas/test_jarvis.py`, `tests/unit/personas/test_minie.py`, `tests/unit/personas/test_persona_manager.py`, `tests/unit/decision/test_authority.py` — new coverage.

## Expected Classes

None new.

## Expected Interfaces

`Persona.compose_reply()`'s signature change is a **breaking change to an existing interface**, not a new one — every existing caller (`PersonaManager.compose_reply_safely()`, and every test constructing a fake `Persona`) must be updated. The new parameter defaults to `None` specifically so every existing call site that doesn't yet have an `EmotionalState` to pass (there is exactly one real caller of `compose_reply_safely()`, `CommunicationPipeline`, and it isn't updated until Sprint 5.14) continues to work unmodified until then — an additive-in-effect, breaking-in-signature change, the identical shape Sprint 3.12 already used when `compose_reply()` first grew its `decision_trace` parameter.

## Expected Functions

- `Persona.compose_reply(transcript, context, decision_trace, emotional_state=None) -> str` — updated abstract signature.
- `JarvisPersona._select_tone_variant(emotional_state: EmotionalState | None) -> ToneVariant` (module-private, new): a small enum/lookup (`NEUTRAL`, `CONCISE` for high stress, `ENCOURAGING` for low mood/comfort) driving which of a small set of already-existing phrasing templates gets used — never new template text generated at request time.
- `MiniePersona._select_tone_variant(emotional_state: EmotionalState | None) -> ToneVariant` — Minie's own equivalent, with a warmth-leaning variant set appropriate to her own "casual, comfort, wellness" identity.
- `decision/authority.py`'s `_determine_engine()` — new branch: `intent.category == IntentCategory.EMOTIONAL_SUPPORT and authority_level != AuthorityLevel.INFORM` (mirrors the existing narrow-gating style of every other branch in this method) `-> EngineSelection.EMOTION_SUPPORT`.

## Data Flow

```
CommunicationPipeline (existing, not modified this sprint)
        |
        v
PersonaManager.compose_reply_safely(transcript, context, decision_trace, emotional_state)
        |
        v
Persona.compose_reply(transcript, context, decision_trace, emotional_state)
        |
        v
   _select_tone_variant(emotional_state) -> ToneVariant
        |
        v
   (existing template selection logic, now branching on ToneVariant in addition to
    whatever it already branches on)
        |
        v
   reply: str  (same return type/contract as before this sprint)
```

`decision/authority.py`'s new `EMOTION_SUPPORT` branch is a separate, independent data flow (Engine Selection, not Response Generation) — it decides *that* an emotional-support-shaped reply is warranted; the actual tone adaptation above happens regardless of which `EngineSelection` value was chosen, since `compose_reply()` is still the eventual handler for `EMOTION_SUPPORT` exactly as it already is for `CONVERSATIONAL_RESPONSE` (Sprint 5.14 wires this specific dispatch — not this sprint).

## Implementation Tasks

1. `personas/base.py` — signature change, docstring updated.
2. `personas/jarvis.py`/`personas/minie.py` — `_select_tone_variant()`, wired into each persona's existing template logic.
3. `personas/persona_manager.py` — `compose_reply_safely()` passthrough.
4. `decision/authority.py` — `_determine_engine()` branch, docstring comment update.
5. Test updates across all four modified test files, plus new dedicated tone-variant-selection tests.

## Architecture Notes

**"The AI never pretends to possess human emotions. Behavioral estimation only."** — enforced here structurally, not just by convention: `_select_tone_variant()` only ever selects among a small, fixed, human-reviewed set of phrasing templates; it never inserts a first-person claim about JARMINEI's own feelings, and it never states the user's estimated emotional label back to them as a flat assertion (e.g. never "You are stressed.") — at most, an already-existing gentle, tentative phrasing pattern (e.g. Minie's own established "that sounds like a lot" style, not new text this sprint invents) is *selected*, never generated fresh. This mirrors the Emotion Detection Engine's own "behavioral estimate, never diagnosis" discipline (Sprint 5.1) extended into what gets said out loud.

**Presentation-Intelligence boundary, explicit**: this sprint changes *tone selection within an existing template*, never `ContextAnalysis`, `Intent`, memory retrieval, or any fact the reply conveys — the brief's own locked rule ("Presentation never changes intelligence") is the literal design constraint here, not just a description.

## Integration Considerations

- **`emotional_state` has no real caller supplying anything but `None` until Sprint 5.14** — every test this sprint writes constructs a real `EmotionalState` fixture directly (Sprint 5.2's dataclass, no manager needed), the same "component before integration" pattern as 5.1–5.3.
- Sprint 5.11 (Voice Personality) builds on this sprint's output (the already-tone-adapted reply text), adding pacing/pause-shaping before TTS — a distinct, later transformation of the same string, not overlapping responsibility with this sprint's phrasing selection.
- Sprint 5.5 (Presentation State Engine) reads `EmotionalState` independently for visual/voice-warmth parameters — it does not read `ToneVariant` from this sprint; the two are parallel consumers of the same upstream state, not chained.

## Potential Risks

- **A small, fixed set of tone-variant templates risks feeling repetitive over many turns** — acceptable for this sprint (the same limitation the underlying template-based `compose_reply()` already has, unrelated to this sprint's own scope); expanding the template variety is a content/writing task for a future sprint, not an architecture gap.
- **Risk of a tone variant reading as presumptuous** ("Minie assumed I was sad when I wasn't") — mitigated by `EmotionalState`'s own gradual-evolution design (Sprint 5.2: a single misread turn barely moves the state) and by keeping variant selection conservative (a clear threshold, not a hair-trigger).

## Acceptance Criteria

- `compose_reply()` never raises regardless of `emotional_state` being `None` or populated (Fail Gracefully, unchanged contract from Sprint 2.9).
- A constructed `EmotionalState` fixture at each of several distinct configurations produces observably different tone-variant selection in both `JarvisPersona` and `MiniePersona`.
- `EMOTION_SUPPORT` is reachable from a real `EMOTIONAL_SUPPORT`-category `Intent` at `RECOMMEND` authority or above, and only then.
- No code path introduces a first-person emotional claim or a flat "you are X" assertion — spot-checked directly in the new tests' own assertions, not just inferred.
- `ruff check .` clean; full existing suite passes with the new optional parameter in place (every pre-existing `compose_reply()` call site continues to work unmodified).

## Testing Checklist

- [ ] Unit: `_select_tone_variant()` for both personas across representative `EmotionalState` fixtures.
- [ ] Unit: `compose_reply()` with `emotional_state=None` behaves identically to pre-Sprint-5.4 output (regression safety).
- [ ] Unit: `decision/authority.py`'s new `EMOTION_SUPPORT` branch, including the negative case (an `EMOTIONAL_SUPPORT` intent at `INFORM` authority does NOT route there).
- [ ] Full regression: existing suite unaffected by the signature change.

## Documentation Checklist

- [ ] `personas/base.py`'s `Persona` docstring updated to describe the new parameter and the "adaptation, not generation" boundary.
- [ ] `decision/authority.py`'s module docstring's `EngineSelection` table updated (`EMOTION_SUPPORT` moves from "reserved" to "wired").
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

5.5 — Presentation State Engine.

## Future Considerations

- A richer tone-variant template library (more than the small starting set this sprint ships) is real future content work, not an architecture change — flagged for whoever next touches persona phrasing.
- Whether `WELLNESS`-shaped replies (Part B's own future job) should reuse this sprint's `ToneVariant` mechanism is a real open question for whichever Part B sprint first needs it — not decided here.

## Sprint Completion Report (2026-08-02)

Implemented as specified, authorized directly ("continue with sprint 5.4") right after Sprint 5.3 closed in the same session.

### Summary

`personas/base.py`'s `Persona.compose_reply()` gains a new optional `emotional_state: EmotionalState | None = None` parameter — an additive-in-effect, breaking-in-signature change, the identical shape Sprint 3.12's `decision_trace` parameter already used — plus a new shared `ToneVariant` enum (`NEUTRAL`/`CONCISE`/`ENCOURAGING`). `personas/jarvis.py`/`personas/minie.py` each gain a private `_select_tone_variant()` picking among a small, fixed set of already-existing phrasing templates (`_ACKNOWLEDGEMENT_TEMPLATES`) — a warmer `ENCOURAGING` opening when mood/comfort reads low, a shorter `CONCISE` one when stress reads high, `NEUTRAL` (byte-identical to every pre-Sprint-5.4 reply) whenever `emotional_state` is `None` or unremarkable. Minie's own thresholds lean into `ENCOURAGING` more readily than Jarvis's, matching her "casual, comfort, wellness" identity as this sprint's primary, not sole, beneficiary. `PersonaManager.compose_reply_safely()` passes `emotional_state` straight through unchanged. `decision/authority.py`'s `_determine_engine()` gained a real, narrow `EMOTION_SUPPORT` branch and its own signature grew a third `authority_level` parameter to read it.

**A real gap beyond the sprint's own stated Files to Modify was found and fixed**: this sprint's own Expected Functions named plain module-level threshold constants for `_select_tone_variant()`, but `03_Engineering_Standards.md`'s own "no hardcoded... thresholds" rule — and `emotion/detection_engine.py`'s own established precedent, a pure function (`_match_lexical_markers(text, config)`) reading its tunable numbers from an injected `EmotionConfig` rather than a literal — both require these to be config-driven instead. `config/schema.py`'s `EmotionConfig` gained `tone_high_stress_threshold` (shared) and `{jarvis,minie}_tone_low_mood_threshold`/`{jarvis,minie}_tone_low_comfort_threshold` (per-persona), all validated against `_EMOTIONAL_STATE_DIMENSION_RANGES`, with defaults matching this sprint's own originally-specified numbers exactly — so real behavior is unchanged, only where the numbers live. `JarvisPersona`/`MiniePersona` each gained an optional `emotion_config: EmotionConfig | None = None` constructor parameter, defaulting internally to `EmotionConfig()` when omitted — additive, so every existing call site (both harness `conftest.py` files, every pre-Sprint-5.4 test) continues to work unmodified; `main.py` was updated to pass the real `config.emotion` through explicitly rather than rely on the silent default.

Two spec ambiguities were resolved explicitly, not guessed silently:

1. **Reachability of `EMOTION_SUPPORT` without widening `_determine_authority()`.** The spec's own Expected Functions names the gating condition as `authority_level != AuthorityLevel.INFORM`, but `IntentCategory.EMOTIONAL_SUPPORT` is not a member of `_RECOMMEND_INTENT_CATEGORIES`, so no ordinary-priority path produces a non-`INFORM` authority for it. Resolved in favor of leaving `_determine_authority()`/`_RECOMMEND_INTENT_CATEGORIES` untouched (not named in this sprint's own Files to Modify) — the branch is genuinely reachable only via the same `CRITICAL_EMERGENCY`-priority-with-no-matching-procedure path that already produces `RECOMMEND` for any category (the identical mechanism the existing `EMERGENCY_ASSIST`-whitelist tests already exercise), proven directly with three new dedicated tests rather than assumed. This keeps `test_other_categories_are_inform`/`test_emotional_support_never_actually_selects_wellness`/`test_selected_engine_is_always_conversational_or_inform_only` — three pre-existing tests that explicitly assert `EMOTIONAL_SUPPORT` stays `INFORM`/`CONVERSATIONAL_RESPONSE` at ordinary priority — passing completely unmodified.
2. **`_select_tone_variant()`'s "module-private" framing vs. needing config.** The spec calls it module-private and names it as if bound to the persona class (`JarvisPersona._select_tone_variant(...)`). Once thresholds moved to `EmotionConfig` (point above), a pure module-level function taking `config` as an explicit second parameter — mirroring `_match_lexical_markers(text, config)` exactly — was chosen over an instance method reading `self._emotion_config` internally, keeping it directly unit-testable without constructing a full persona, the same testability the spec's own Testing Checklist asked for.

`decision/authority.py`'s module docstring needed more than the one-line "reserved → wired" update the Documentation Checklist named: the pre-existing "EMERGENCY_ASSIST... `_determine_engine()` below always returns CONVERSATIONAL_RESPONSE/INFORM_ONLY regardless of authority_level" paragraph became literally false once `_determine_engine()` gained a real `authority_level`-reading branch (for an unrelated, non-emergency reason) — corrected to carve out the exception rather than leave a self-contradicting docstring. The "selected_engine is CONVERSATIONAL_RESPONSE, INFORM_ONLY, DEVICE_CONTROL, or WORKFLOW... never one of the four still-reserved values" paragraph (already stale since Sprint 4.18 added SCHEDULER/INTERNET_AGENT, pre-dating this sprint) was also corrected specifically where this sprint's own change made its `EMOTIONAL_SUPPORT`-belongs-to-Wellness example newly inaccurate, without attempting a full unrelated rewrite of that paragraph's other pre-existing drift.

### Files Modified

- `personas/base.py` — `ToneVariant` enum; `Persona.compose_reply()` signature + docstring.
- `personas/jarvis.py` — `_ACKNOWLEDGEMENT_TEMPLATES` (three variants), thresholds removed in favor of `EmotionConfig` reads, `_select_tone_variant()`, constructor gains `emotion_config`, `compose_reply()` wired.
- `personas/minie.py` — same shape as `personas/jarvis.py`, warmer-leaning thresholds.
- `personas/persona_manager.py` — `compose_reply_safely()` gains `emotional_state` passthrough.
- `decision/authority.py` — `_determine_engine()` signature + `EMOTION_SUPPORT` branch; `evaluate()`'s call site; `_build_reasoning()` new branch; module docstring updates (Summary above).
- `config/schema.py` — `EmotionConfig.tone_high_stress_threshold`/`{jarvis,minie}_tone_low_mood_threshold`/`{jarvis,minie}_tone_low_comfort_threshold` + validation. **Not named in the sprint file's own Files to Modify** — a real, necessary addition (Summary above).
- `config/defaults.yaml` — matching new field defaults.
- `main.py` — `JarvisPersona`/`MiniePersona` construction passes `config.emotion` explicitly. **Not named in the sprint file's own Files to Modify** — see Summary above.
- `tests/unit/personas/test_jarvis.py`, `tests/unit/personas/test_minie.py`, `tests/unit/personas/test_persona_manager.py`, `tests/unit/decision/test_authority.py` — new coverage (see Tests Added).
- `tests/unit/config/test_schema.py` — new `EmotionConfig` threshold-validation coverage. **Not named in the sprint file's own Files to Modify** — follows directly from the `config/schema.py` addition above.

### Tests Added

- `tests/unit/personas/test_jarvis.py` — 11 new tests: `_select_tone_variant()` across `None`/neutral/high-stress/low-mood/low-comfort/both-present-prefers-CONCISE fixtures, config-driven-not-hardcoded proof, `emotional_state=None` regression-matches-pre-5.4 output, high-stress/low-comfort produce the exact expected reply text, tone variant composes correctly alongside an authority prefix, never-raises with a state and no trace.
- `tests/unit/personas/test_minie.py` — 13 new tests: the same shape as `test_jarvis.py` plus Minie-leans-into-`ENCOURAGING`-more-readily-than-Jarvis (direct cross-persona comparison) and a full adversarial sweep (every `AuthorityLevel` × five representative `EmotionalState`s × both personas × trace-or-no-trace) proving `compose_reply()` never raises.
- `tests/unit/personas/test_persona_manager.py` — 2 new tests: `compose_reply_safely()` genuinely forwards `emotional_state` (not silently dropped, mirroring the existing `decision_trace` forwarding proof) and defaults it to `None`.
- `tests/unit/decision/test_authority.py` — 3 new tests: `EMOTIONAL_SUPPORT` at `RECOMMEND` authority (via `CRITICAL_EMERGENCY` priority, no matching procedure) selects `EMOTION_SUPPORT`; the negative case at `INFORM` authority does not; `EMOTION_SUPPORT` is also reachable at `EMERGENCY_ASSIST` authority (an approved procedure), proving the gate is genuinely `!= INFORM`, not just `== RECOMMEND`.
- `tests/unit/config/test_schema.py` — 5 new tests: each new threshold field's out-of-range case raises with the field name in the message (parametrized across both personas for mood/comfort), plus a defaults-are-valid sanity check.

### Documentation Updated

- `personas/base.py`'s `Persona`/module docstrings (new parameter, "adaptation, not generation" boundary).
- `personas/jarvis.py`/`personas/minie.py`'s module docstrings.
- `decision/authority.py`'s module docstring (`EngineSelection` table, new EMOTION_SUPPORT routing paragraph, two corrected stale paragraphs — see Summary above).
- `config/schema.py`'s `EmotionConfig` docstring.
- This Sprint Completion Report.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated (see below).

### Acceptance Criteria Checklist

- ✔ `compose_reply()` never raises regardless of `emotional_state` being `None` or populated — verified directly via a parametrized adversarial sweep, not just inferred.
- ✔ A constructed `EmotionalState` fixture at each of several distinct configurations produces observably different tone-variant selection in both `JarvisPersona` and `MiniePersona`.
- ✔ `EMOTION_SUPPORT` is reachable from a real `EMOTIONAL_SUPPORT`-category `Intent` at `RECOMMEND` authority or above, and only then — both directions proven.
- ✔ No code path introduces a first-person emotional claim or a flat "you are X" assertion — every new template string spot-checked directly (`_ACKNOWLEDGEMENT_TEMPLATES` in both personas), none exists.
- ✔ `ruff check .` clean; full existing suite passes with the new optional parameter in place.

### Risks

- Same "small, fixed template set risks repetitiveness" and "presumptuous tone variant" risks named in the spec — unchanged, mitigated the same way (conservative thresholds, `EmotionalState`'s own gradual-evolution design upstream).
- `EMOTION_SUPPORT`'s narrow real-pipeline reachability (only via the `CRITICAL_EMERGENCY`-priority path, per Engineering Decision 1 above) means the engine-selection half of this sprint is largely symbolic until either a future sprint widens `_RECOMMEND_INTENT_CATEGORIES` or `PriorityQueueManager.classify()` gains a richer signal — the tone-adaptation half (this sprint's actual user-facing deliverable) is fully real and unconditional regardless, so this doesn't block anything downstream.
- No live caller of `emotional_state` yet beyond direct unit-test construction — Sprint 5.14's job, same precedent as 5.1–5.3.

### Technical Debt

None introduced. The `EmotionConfig`/`main.py` gaps were found and fixed within this sprint, not deferred.

### Recommendations

- Once Sprint 5.14 wires a live `EmotionalStateManager` caller, sanity-check the shipped tone thresholds against real conversation sessions before considering them tuned (same "real usage before tuning further" recommendation Sprints 5.1–5.3 already made for their own first-pass numbers).
- Whether `_RECOMMEND_INTENT_CATEGORIES` should eventually include `EMOTIONAL_SUPPORT` (making `EMOTION_SUPPORT` reachable from ordinary conversational distress, not just `CRITICAL_EMERGENCY`-priority) is a real, deliberately-deferred design question — flagged for whoever next revisits Engine Selection routing, not decided here per this sprint's own narrow-and-additive scope.

### Verification

Full suite: 1236 passing + 2 pre-existing failures (both individually confirmed unrelated to this sprint — `test_full_level3_acceptance_scripted_conversation` is the same already-established host-load timing flake documented since Sprint 4.6, reconfirmed passing standalone this session; `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` is the same real-Ollama-output nondeterminism flake from Sprint 5.2/5.3's own verification, in a file this sprint never touches) + 1 skipped + 1 deselected. `ruff check .` clean across the whole repository. A real, non-mocked config-load smoke test (`ConfigLoader().load()`) confirmed the new `EmotionConfig` threshold fields genuinely load end-to-end with their shipped defaults.

**No git commit made** — per this project's own "only commit when explicitly asked" rule, changes left in the working tree; the user has not yet been asked whether to commit.

**Sprint 5.5 (Presentation State Engine) is next.**
