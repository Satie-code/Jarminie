# Sprint 2.10 — Minie Persona

## Sprint ID

2.10

## Sprint Name

Minie Persona

## Purpose

Add the second concrete persona, per [01_Project_Vision.md](../01_Project_Vision.md): *"Minie — The calm, caring, conversational companion persona."* and [02_System_Architecture.md](../02_System_Architecture.md): *"Companion behavior... Voice: Soft female voice."*

## Engineering Rationale

A separate sprint for the second persona (rather than folding it into 2.9) mirrors the Level 1 precedent of one-subsystem-per-sprint even when two subsystems are structurally similar (e.g. Sprints 1.2–1.4 each got their own sprint despite following the same DI pattern) — it keeps each sprint's diff small and its acceptance criteria unambiguous, and makes `personas/base.py`'s abstraction get exercised by a second real implementation before Persona Switching (2.11) has to depend on it. Minie's Level 2 responsibilities are intentionally narrower than Part 1/2 describe in full: wellness reminders, hydration, and break reminders belong to Minie in the finished product, but the Wellness Engine itself is Level 5 (Phase 5.2) and explicitly outside this task's scope ("No ... wellness ... functionality should be included" is implied by the task's productivity/scheduling/learning exclusion list, and wellness logic has its own dedicated future phase). This sprint gives Minie an identity and voice and the same placeholder `compose_reply()` pattern as Jarvis — nothing wellness-specific yet.

## Objectives

- `MiniePersona`, bound to `VoiceConfig.minie_voice_id`, with a gentle/warm/caring tone distinct from Jarvis's.
- Confirm `personas/base.py`'s `Persona` ABC needs no changes to accommodate a second implementation — if it does, that is a signal the abstraction from 2.9 was under-designed and must be fixed here, not worked around.

## Dependencies

2.9 (Persona Base & Jarvis Persona)

## Files to Create

- `personas/minie.py` — `MiniePersona`.
- `tests/unit/personas/test_minie.py`

## Files to Modify

None expected — see Objectives above regarding `personas/base.py`.

## Expected Classes

- `MiniePersona(Persona)` — constructor DI: `(voice_config: VoiceConfig)`; `voice_id` returns `voice_config.minie_voice_id`.

## Expected Interfaces

None new — implements `Persona` (2.9) only.

## Expected Functions

- `MiniePersona.compose_reply(transcript: str, context: ConversationContext) -> str` — same placeholder-acknowledgement pattern as `JarvisPersona`, styled with a warmer, more casual tone consistent with Minie's characterization. Still no external model call, no wellness logic, no emotional inference (Emotion Engine is Level 5, Phase 5.1 — out of scope).
- `MiniePersona.describe() -> str` — returns e.g. `"Minie — companion persona"`.

## Data Flow

Identical shape to Sprint 2.9's Data Flow, with `MiniePersona` substituted for `JarvisPersona`:

```
ContextManager.current_context()  (2.8)
      ↓
MiniePersona.compose_reply(transcript, context)
      ↓
reply text
      ↓
VoiceSessionManager.speak_reply(text, persona.voice_id)  (2.5) → TextToSpeech.speak()  (2.4)
```

## Acceptance Criteria

- `MiniePersona.voice_id` always resolves to `VoiceConfig.minie_voice_id`.
- `compose_reply()` never raises for any input, matching Jarvis's robustness guarantee.
- `JarvisPersona` and `MiniePersona` are interchangeable everywhere a `Persona` is expected (verified by running the same test suite shape against both, e.g. a shared parametrized test fixture) — the concrete proof that `Persona`'s abstraction is sound.

## Testing Checklist

- [ ] Unit: `MiniePersona.voice_id` reflects `VoiceConfig.minie_voice_id`.
- [ ] Unit: `compose_reply()` robustness (empty/long/normal transcript), mirroring 2.9's cases.
- [ ] Unit: a shared parametrized test (both `JarvisPersona` and `MiniePersona`) confirms both satisfy the `Persona` contract identically in shape.

## Documentation Checklist

- [ ] `personas/minie.py` docstring: same placeholder-disclosure statement as Jarvis's, plus explicit note that wellness/emotional behavior is deferred to Level 5.
- [ ] `docs/STATUS.md` — no change (Phase 2.3 still in progress until 2.11).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Low — structurally identical to 2.9 by design.

## Estimated Development Time

0.5 day.

## Risks

- **Tone differentiation between placeholder replies may read as superficial** (both persona replies are template-based, not truly distinct reasoning) until the real Decision Engine (Level 3) exists — acceptable and expected at this Level; do not over-invest in making the placeholder "feel" more different than it structurally is.
- Same interface-stability risk as 2.9's Risks section regarding a future `compose_reply()` signature change.

## Next Sprint

2.11 — Persona Switching & Explicit Selection.
