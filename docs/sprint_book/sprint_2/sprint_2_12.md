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

## Sprint Completion Report (2026-07-17)

Delivered the files this sprint's spec named:

- `voice/pipeline.py` — `CallbackRelay`, `CommunicationPipeline(ManagedModule)`.
- `main.py` — `_register_level2_modules()` constructs and registers all 9 Level 2 `ManagedModule`s with `CoreManager`, called from `main()` before `run_app()`.
- `tests/integration/test_communication_pipeline.py` — 2 real, non-mocked integration tests.
- `requirements.txt` — confirmed accurate, no changes needed (as the spec itself expected).

256/256 tests passing project-wide, `ruff check .` clean. This sprint itself added 5 new tests directly (3 wake-word regression tests for the fix described below, 2 real integration tests in `tests/integration/test_communication_pipeline.py`); the rest of the suite carries forward from Sprints 2.1–2.11.

### A real circular-construction problem, resolved (not in the spec's literal text)

`WakeWordDetector.on_detected` and `VoiceSessionManager.on_turn_complete`/`on_session_ended` are all fixed at *their own* constructor time (Sprint 2.2/2.5's design — this sprint's "Files to Modify" deliberately excludes both files, so no setter could be added even if wanted). The spec's own `CommunicationPipeline.start()` description ("wires: `WakeWordDetector.on_detected` → ...") reads as if wiring happens via a live post-construction call, but no such API exists on either class. Worked out the real object-graph order during implementation: `QuietModeController` can be constructed before `WakeWordDetector` (no circularity — `WakeWordDetector` gets `quiet_mode_controller._on_wake_word_detected` directly, a real bound method, at construction), but `VoiceSessionManager` must be constructed *before* `QuietModeController` (whose own constructor needs it) and long before `CommunicationPipeline` (whose constructor needs a built `QuietModeController`) — so `VoiceSessionManager`'s two callbacks cannot point at their real targets when it's built. Resolved with `CallbackRelay` (`voice/pipeline.py`): `main.py` passes a relay in `VoiceSessionManager`'s constructor in place of the real target; `CommunicationPipeline.start()` points each relay at its real target (`self._handle_turn_complete`, `quiet_mode_controller._on_session_ended`) once the full graph exists, and `stop()` clears them again. This is also what makes `health_check()`'s "each wired callback still points where expected" a real, checkable claim (compares each relay's current `.target` against the expected bound method) rather than an assumption. Documented in `voice/pipeline.py`'s own module docstring and in `main.py`'s `_register_level2_modules()` docstring so this doesn't need rediscovering.

### A real bug found by this sprint's own integration testing, fixed immediately

While designing the integration test (real `WakeWordDetector` + real `VoiceSessionManager` sharing one fake microphone stream), traced through `WakeWordDetector._listen_loop()` and found it called `mic.read_frame()` unconditionally, every iteration, with no check of the microphone's mode. Once a session makes the mic `ACTIVE_CAPTURE` (Sprint 2.5), this background thread never stopped competing with `VoiceSessionManager`'s own utterance-capture thread for the same frame stream — a real, structurally-guaranteed concurrency bug that would have corrupted or starved every real conversation turn's captured audio, not a hypothetical. No unit test in Sprints 2.2–2.11 caught it because none of them ran the listen loop concurrently with an active session. Fixed immediately (matching the precedent set at Sprint 2.5's Whisper-hallucination finding — the user wants real bugs like this fixed when found, not deferred) in `voice/wake_word.py`: `_listen_loop()` now pauses (polling every 0.1s) while `mic.current_mode()` isn't `PASSIVE_LISTENING`, resuming automatically once it is; `_last_processed_at` is still updated during the pause so `health_check()` doesn't mistake deliberate idling for the stuck-and-failing state it's meant to catch. 3 new regression tests in `tests/unit/voice/test_wake_word.py` (now 11/11, stable across 4 repeated runs). Documented as a Post-Sprint Fix in `sprint_2_2.md` (the sprint that owns the file) and tracked in `backlog/technical_debt.md` item 10, per this project's established pattern for cross-sprint fixes.

### Verification

**Real, non-mocked integration test** (`tests/integration/test_communication_pipeline.py`): builds the exact same object graph as `main.py`'s own `_register_level2_modules()`, with fakes only at the audio-hardware/ML boundary (`FakeAudioBackend`, `FakeWakeWordEngine`, `FakeSpeechToText`, `FakeTextToSpeech` — matching the "fake only at the seams that need real hardware/models" precedent every Level 2 unit-test file already established since Sprint 2.1) — every other module (mic, wake-word detector, session manager, quiet mode controller, a real SQLite file under `tmp_path`, conversation store, context manager, both personas, persona manager, the pipeline itself) is real. `test_full_wake_to_reply_round_trip` demonstrates Phase 2.1/2.2/2.3's acceptance criteria together: wake phrase activates JARMINEI, a fake utterance is transcribed, Jarvis composes and "speaks" a reply with the correct voice ID, the turn is actually persisted through the real Conversation Session Store, and silence timeout returns the system cleanly to Quiet Mode. `test_explicit_minie_selection_switches_voice_for_next_reply` demonstrates the Testing Checklist's explicit-selection requirement: a "talk to minie please" utterance mid-conversation switches both the active persona and the voice ID used for the very next reply. Both stable across 5 repeated runs (no sleep-and-hope — synchronized on real `threading.Event`s and polled state, matching this project's established testing discipline).

**Real smoke run** (scratchpad, not committed, mirroring the Sprint 2.1–2.5 precedent): ran `main.py`'s actual `_register_level2_modules()` + `CoreManager.startup()`/`shutdown()` directly (not through the Qt GUI event loop) with real Whisper (`base`), real Coqui (`tts_models/en/vctk/vits`, 109 speakers via real `espeak-ng`), real openWakeWord, and a real microphone. All 9 registered modules reached `RUNNING` on startup and `STOPPED` cleanly on shutdown — zero `FAILED` states either direction. **Startup took 13–15s measured** (this sprint's own flagged Risk — well within reason, not "unacceptable," so no Level 6 lazy-loading intervention needed yet). One environment-only hiccup along the way, not a code issue: the persistent shell session used for this work predated an earlier session's `espeak-ng` PATH fix (`HKCU\Environment`), so the very first smoke run failed with `FileNotFoundError: No espeak backend found` purely because that PATH change hadn't propagated to this already-running shell. Confirmed `espeak-ng.exe` was still genuinely installed on disk, added it to the current shell's `PATH` directly, and the identical run then succeeded — not a regression of `backlog/technical_debt.md` item 7, just a reminder that registry-level `PATH` changes don't reach processes that predate them.

**Not verified in this session** (per this sprint's own explicit acknowledgment that it's outside what "this Sprint Book can verify on its own behalf"): a live, human-voice wake-word-to-spoken-reply round trip on the actual target laptop, with a person actually speaking and listening. Everything upstream of that specific interactive step (real model loads, real mic open/close, the wake-word thread actually running against real ambient audio for several seconds without crashing) was exercised in the smoke run above.

### Scope note: `purge_older_than()` still has no caller

Sprint 2.7's own file predicted "the caller that decides cadence arrives with Sprint 2.12's integration," but this sprint's actual spec (Objectives/Files/Acceptance Criteria) never mentions purge scheduling — a real inconsistency between what one sprint file predicted and what the next one, written later, actually specified. Not added unilaterally here: a periodic-timer mechanism is Scheduler-shaped functionality (Level 4, Sprint 4.8+) that Level 2 explicitly excludes, and nothing in this sprint's own acceptance criteria needed it. Tracked as `backlog/technical_debt.md` item 11 rather than guessed at.

### Acceptance Criteria Checklist

- ✔ Phase 2.1/2.2/2.3's acceptance criteria demonstrated together in one real run (integration test, both directions of persona selection).
- ✔ `main.py` still starts and stops cleanly with the full Level 2 module set registered — verified with real models, no regression to Level 1 (full suite, including every Level 1 test, passes unchanged).
- ✔ Every Level 2 module appears in the existing Status Panel via `module_states()` — no `ui/status_panel.py` changes made or needed, confirmed by the smoke run's own `module_states()` output covering all 9 registrations.

**Phase 2.1, 2.2, and 2.3 are confirmed Complete in combination — `docs/STATUS.md` updated with an integration-verified note. Sprint 2.13 (Error Handling & Recovery Hardening) is next.**
