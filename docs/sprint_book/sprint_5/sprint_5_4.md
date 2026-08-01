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
