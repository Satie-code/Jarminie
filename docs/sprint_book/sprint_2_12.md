# Sprint 2.12 — Communication Pipeline Integration

## Sprint ID

2.12

## Sprint Name

Communication Pipeline Integration

## Purpose

Wire every component built in Sprints 2.1–2.11 into one real, end-to-end communication pipeline inside `main.py`, the way Sprint 1.5/1.6 wired Config/Logging/Health into a running Core Manager and a real desktop shell. This is where Level 2's combined acceptance criteria from [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md) — spanning Phases 2.1, 2.2, and 2.3 together — first become verifiable as one real system rather than eleven independently-tested pieces.

## Engineering Rationale

Deliberately not part of the user's originally suggested flat sprint list mapping — this Sprint Book instead keeps 2.1–2.11 each single-purpose and defers *all* wiring to one dedicated sprint, matching this task's own suggested "Communication Pipeline Integration" sprint and the Single Responsibility Rule applied at the sprint-planning level, not just the code level: each component sprint's Files to Modify was `None` specifically so this sprint could be the sole place `main.py` changes for all of Level 2. This mirrors Sprint 1.5's own Architecture Notes ("No real subsystems exist yet to register... tests use small mock `ManagedModule` implementations") — 2.1–2.11 proved each module correct in isolation; this sprint proves they're correct together, which per Sprint 1.8's hard-won lesson ("mocked tests systematically miss integration bugs that only a real end-to-end run catches") is a distinct kind of verification neither unit tests nor code review can substitute for.

A second, structural benefit: because `CoreManager.module_states()` already renders *any* registered module generically (Sprint 1.7's Status Panel), every Level 2 module appearing in the Status Panel requires zero UI changes — confirmed by inspection of `ui/status_panel.py` before writing this sprint. This sprint's `ui/*` "Files to Modify" list is therefore empty, a direct payoff of Level 1's extensibility design.

## Objectives

- `voice/pipeline.py`'s `CommunicationPipeline`: owns *only* the event wiring between already-built modules — no new business logic, no new state beyond what wiring requires.
- `main.py` constructs every Level 2 subsystem via DI and registers each with `CoreManager` in dependency order, exactly as `main.py` already does for Level 1's modules.
- A real, end-to-end smoke run: fake/fixture audio in, spoken audio out, exercised through the actual composed pipeline — not mocks standing in for real collaborators at the seams that matter.

## Dependencies

2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11 (all of Level 2's component sprints)

## Files to Create

- `voice/pipeline.py` — `CommunicationPipeline`.
- `tests/integration/test_communication_pipeline.py` — real (non-mocked) collaborators wired together, driven by a fixture WAV file through a fake `AudioBackend`/`AudioOutput` pair (no physical hardware or CI-unfriendly model downloads required — see Risks).

## Files to Modify

- `main.py` — construct `MicrophoneManager`, `WakeWordDetector`, `WhisperSpeechToText`, `CoquiTextToSpeech`, `VoiceSessionManager`, `QuietModeController`, `SqliteClient`, `ConversationSessionStore`, `ContextManager`, `JarvisPersona`, `MiniePersona`, `PersonaManager`, `CommunicationPipeline`; register each `ManagedModule` with `CoreManager` via `register_module()` in dependency order.
- `requirements.txt` — confirm all Phase 2.1 entries (already present since Sprint 1.1's bootstrap) are still accurate; no new packages expected at this sprint.

## Expected Classes

- `CommunicationPipeline(ManagedModule)` — constructor DI: every Level 2 module it wires together (mic, wake word, session manager, quiet mode, conversation store, context manager, persona manager). `start()` connects the callback chain described in Data Flow below; `stop()` disconnects it; `health_check()` reports whether the wiring is intact (each wired callback still points where expected) — a deliberately shallow check, since each individual module's own `health_check()` already covers its internal correctness.

## Expected Interfaces

None new — `CommunicationPipeline` composes existing `ManagedModule` instances; it does not define a new cross-module contract.

## Expected Functions

- `CommunicationPipeline.start() -> None` — wires: `WakeWordDetector.on_detected` → `QuietModeController._on_wake_word_detected`; `VoiceSessionManager.on_session_ended` → `QuietModeController._on_session_ended`; `VoiceSessionManager.on_turn_complete` → (persona selection via `PersonaManager.detect_explicit_selection`/`detect_context_heuristic`/`select`) → `ContextManager.current_context` → `active_persona.compose_reply` → `ConversationSessionStore.record_turn` → `VoiceSessionManager.speak_reply`.
- `main()` (modified) — composition root grows to construct the full Level 2 graph before calling `core_manager.startup()`, unchanged in overall shape (`ConfigLoader` → logging → resource monitor → Core Manager → now also Level 2 modules → `run_app()`).

## Data Flow

```
Microphone (passive)
      ↓
WakeWordDetector → QuietModeController.activate(WAKE_WORD)
      ↓
Microphone (active) + VoiceSessionManager.begin_session()
      ↓
WhisperSpeechToText.transcribe() → transcript
      ↓
PersonaManager.detect_explicit_selection / detect_context_heuristic → select()
      ↓
ContextManager.current_context()
      ↓
active_persona.compose_reply(transcript, context) → reply text
      ↓
ConversationSessionStore.record_turn(...)
      ↓
VoiceSessionManager.speak_reply(reply, persona.voice_id) → CoquiTextToSpeech.speak()
      ↓
(silence timeout) → end_session() → QuietModeController.deactivate()
      ↓
Microphone (passive) — back to Quiet Mode
```

## Acceptance Criteria

- All of Phase 2.1, 2.2, and 2.3's acceptance criteria from [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md) are demonstrated together in one real run: wake phrase activates JARMINEI; speech recognition functions; voice responses function; natural conversation is maintained during a session; correct persona and voice selected; no simultaneous personas.
- `main.py` still starts and stops cleanly with the full Level 2 module set registered (existing Level 1 acceptance — GUI, settings, logging, resource monitoring — shows no regression).
- Every Level 2 module appears in the existing Status Panel via `module_states()` with zero `ui/status_panel.py` changes.

## Testing Checklist

- [ ] Integration: fixture-audio-in → spoken-audio-out full round trip using fake `AudioBackend`/`AudioOutput`, real everything else (real Whisper/Coqui/openWakeWord where feasible in CI time budget, otherwise the smallest real models available — a call to make during implementation, not assumed here).
- [ ] Integration: an explicit "talk to Minie" utterance mid-conversation actually switches the active voice for the next reply.
- [ ] Regression: full existing Level 1 test suite (95 tests as of `v0.1.0`) still passes with Level 2 modules registered.
- [ ] Manual, real hardware: a live wake-word-to-spoken-reply round trip on the actual target laptop — this is the one Testing Checklist item this Sprint Book cannot verify on its own behalf, per the same "no physical mic/speaker in CI" reasoning as Sprint 2.1.

## Documentation Checklist

- [ ] `voice/pipeline.py` docstring: full wiring diagram (matches Data Flow above), explicit statement that this class owns wiring only, no business logic.
- [ ] `docs/STATUS.md` — Phase 2.1/2.2/2.3 rows all confirmed `Complete` in combination; add a note that end-to-end integration is verified as of this sprint.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High — no new algorithms, but the largest surface area of any Level 2 sprint: eleven real collaborators composed together for the first time.

## Estimated Development Time

2–2.5 days.

## Risks

- **Startup time**: registering ~11 additional modules, several loading ML models (Whisper, Coqui, openWakeWord), could make `CoreManager.startup()` noticeably slower than Level 1's near-instant startup — measure real elapsed time; if unacceptable, lazy/parallel model loading is a Level 6 (Sprint 6.1 Performance) concern, not something to solve reactively here.
- **CI feasibility of "real" models**: Whisper/Coqui/openWakeWord model downloads may be too slow/large for routine CI runs — the integration test should default to fakes at the audio-hardware boundary (matches Sprint 2.1's precedent) while still exercising the real wiring logic; a separate, explicitly-triggered "real models" test tier is a reasonable compromise to decide during implementation.
- **First real exercise of `ManagedModule` at scale** (11 concurrent modules, several background threads) may surface registration-order or shutdown-ordering issues `CoreManager` (1.5) never had to handle with only UI-thread modules — if found, the fix belongs in the calling module's `stop()`, not in `CoreManager` itself (Single Responsibility, per Sprint 1.5's Architecture Notes).

## Next Sprint

2.13 — Error Handling & Recovery Hardening.
