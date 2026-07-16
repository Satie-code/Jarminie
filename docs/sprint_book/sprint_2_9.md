# Sprint 2.9 — Persona Base & Jarvis Persona

## Sprint ID

2.9

## Sprint Name

Persona Base & Jarvis Persona

## Purpose

Begin Phase 2.3 (Persona Engine) with the shared `Persona` abstraction and its first concrete persona, per [01_Project_Vision.md](../01_Project_Vision.md): *"Jarvis — The logical, professional, productivity-focused system brain."* and [02_System_Architecture.md](../02_System_Architecture.md): *"Professional execution... Voice: Professional male voice."*

## Engineering Rationale

Part 1 is explicit that JARMINEI is *"one intelligence that expresses itself through two personas"* — a persona in this architecture is an **identity and voice binding**, not a separate reasoning system. Real language understanding and response generation belong to the Decision Engine (Level 3, Phase 3.3, driven by Ollama per [03_Engineering_Standards.md](../03_Engineering_Standards.md)), which does not exist yet and is explicitly excluded from Level 2's scope. This sprint therefore defines `Persona.compose_reply()` as a **deliberately minimal placeholder** — a small, deterministic acknowledgement-style response — solely so the Communication Pipeline (2.12) has something real to speak through Text-to-Speech end-to-end. This is not technical debt in the Technical Debt Policy sense (it is not an undocumented shortcut); it is the correct, intentionally-scoped Level 2 boundary, and its planned replacement by Sprint 3.7's Intent Detection / the Decision Engine is recorded here explicitly so no future sprint mistakes the placeholder for a finished feature.

## Objectives

- A `Persona` abstract base defining identity (`name`, `voice_id`) and the reply-composition contract, so `TextToSpeech.speak()` (2.4) and the future Decision Engine both depend on one stable interface.
- `JarvisPersona`, the first concrete implementation: professional/calm/analytical tone, bound to `VoiceConfig.jarvis_voice_id`.
- The placeholder `compose_reply()` behavior must be honest about being a placeholder — e.g. a plain acknowledgement of what was heard — never a fabricated "smart" response that could be mistaken for real reasoning.

## Dependencies

2.4 (Text-to-Speech Engine — supplies `voice_id` binding target)

## Files to Create

- `personas/base.py` — `Persona` (ABC).
- `personas/jarvis.py` — `JarvisPersona`.
- `tests/unit/personas/test_jarvis.py`
- `tests/unit/personas/conftest.py` — a fake `ConversationContext` fixture builder, reused by 2.10/2.11's tests.

## Files to Modify

None.

## Expected Classes

- `Persona(ABC)` — `name: str` (property), `voice_id: str` (property), `describe(self) -> str` (short identity string for logs/UI, e.g. Debug Console or Status Panel display — reuses Sprint 1.9's existing log-viewing infrastructure with zero changes needed there), `compose_reply(self, transcript: str, context: ConversationContext) -> str` (abstract).
- `JarvisPersona(Persona)` — constructor DI: `(voice_config: VoiceConfig)`; `voice_id` returns `voice_config.jarvis_voice_id`.

## Expected Interfaces

- `Persona(ABC)` — the interface `PersonaManager` (2.11) and `VoiceSessionManager`/`CommunicationPipeline` (2.12) depend on; neither ever references `JarvisPersona` or `MiniePersona` by concrete type.

## Expected Functions

- `JarvisPersona.compose_reply(transcript: str, context: ConversationContext) -> str` — Level 2's placeholder implementation: a short, clearly-templated acknowledgement (e.g. confirms what was heard) with a professional tone consistent with Jarvis's characterization. No external model call, no business logic beyond template formatting.
- `JarvisPersona.describe() -> str` — returns e.g. `"Jarvis — professional execution persona"`.

## Data Flow

```
ContextManager.current_context()  (2.8)
      ↓
JarvisPersona.compose_reply(transcript, context)
      ↓
reply text
      ↓
VoiceSessionManager.speak_reply(text, persona.voice_id)  (2.5) → TextToSpeech.speak()  (2.4)
```

## Acceptance Criteria

- `JarvisPersona.voice_id` always resolves to `VoiceConfig.jarvis_voice_id` from the injected config, never a hardcoded string.
- `compose_reply()` never raises for any input transcript, including an empty string (Fail Gracefully — a persona reply failure must not break a live conversation turn).
- `describe()` output is suitable for direct display in Debug Console / Status Panel without further formatting.

## Testing Checklist

- [ ] Unit: `Persona` cannot be instantiated directly (ABC enforcement).
- [ ] Unit: `JarvisPersona.voice_id` reflects `VoiceConfig.jarvis_voice_id`, including a non-default configured value.
- [ ] Unit: `compose_reply()` handles a normal transcript, an empty transcript, and a very long transcript without raising.
- [ ] Unit: `describe()` returns a non-empty, persona-identifying string.

## Documentation Checklist

- [ ] `personas/base.py` docstring: explicit statement that `compose_reply()` is a Level 2 placeholder, to be replaced by Decision Engine output at Sprint 3.7+, cross-referencing this sprint's Engineering Rationale.
- [ ] `docs/STATUS.md` — Phase 2.3 (Persona Engine) row updated to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Low-Medium — the abstraction is small; the discipline is in keeping the placeholder honest and clearly labeled.

## Estimated Development Time

0.5–1 day.

## Risks

- **Placeholder reply quality could be mistaken for "the conversation feature," inviting scope creep** (e.g. someone adding ad hoc keyword-response rules to make it "seem smarter") — explicitly discouraged; any real reasoning belongs in Sprint 3.7+, not here. If richer placeholder behavior is wanted for demo purposes, it must stay template-based and clearly documented as such.
- **`Persona` interface stability**: once the Decision Engine (Level 3) exists, `compose_reply()`'s signature may need an additional parameter (e.g. an LLM client) — flagged now as an anticipated, not yet needed, interface change; do not add speculative parameters in this sprint.

## Next Sprint

2.10 — Minie Persona.
