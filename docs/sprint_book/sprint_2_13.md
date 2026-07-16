# Sprint 2.13 — Error Handling & Recovery Hardening

## Sprint ID

2.13

## Sprint Name

Error Handling & Recovery Hardening

## Purpose

Apply the Fail Gracefully Rule ("Failure of one subsystem must never terminate the entire application. Unavailable modules should report their status while allowing the remaining modules to continue functioning.") deliberately and exhaustively across the now-complete communication pipeline, per [02_System_Architecture.md](../02_System_Architecture.md) and [01_Project_Vision.md](../01_Project_Vision.md)'s Guiding Engineering Principles.

## Engineering Rationale

Level 1 never planned a dedicated error-handling sprint — its equivalent hardening happened as an ad hoc "Post-Release Review" ([sprint_1_9.md](sprint_1_9.md)) after all nine sprints were already done, because a mostly-synchronous desktop app (config/logging/health/four UI windows) has a small, mostly-foreseeable failure surface. Level 2 is categorically different: real audio hardware that can disappear mid-use, three separately-loaded ML models that can fail to load or crash mid-inference, multiple background threads, and a multi-step pipeline where a failure anywhere must not silently stall the whole conversation. That risk surface justifies planning this hardening pass *in advance*, as its own sprint, rather than hoping a retroactive review catches everything — which is exactly what this task's own suggested structure calls for with a distinct "Error Handling & Recovery" sprint. This sprint also serves as the deferred confirmation point promised by Sprint 2.2's Engineering Rationale and Sprint 1.9's Recommendations: whether `ManagedModule`'s 3-method contract held up across all of Level 2's real modules, now that all of them exist together.

## Objectives

- Enumerate and close every realistic Level 2 failure mode with a specific, tested recovery behavior — not generic `try/except: log` blocks.
- Confirm (or, if genuinely necessary, flag as an explicit decision point — never silently change) whether `ManagedModule` needs anything beyond `start()`/`stop()`/`health_check()` for Level 2's real modules.
- No failure anywhere in the pipeline should ever propagate as an unhandled exception out of a background thread or a `CoreManager`-invoked call.

## Dependencies

2.12 (Communication Pipeline Integration)

## Files to Create

None expected — this sprint hardens existing files rather than adding new ones. (If a genuinely new shared concept emerges, e.g. a `RecoveryPolicy` helper reused across modules, document it here as a deviation before implementing, per the Development Guide's Step 4 planning discipline.)

## Files to Modify

- `voice/microphone.py` — device-disconnect mid-stream handling (scenario a, below).
- `voice/speech_to_text.py` — model load failure / inference crash handling (scenario b).
- `voice/text_to_speech.py` — engine/model unavailable fallback (scenario c).
- `voice/wake_word.py` — background thread death recovery (scenario d).
- `personas/persona_manager.py` / `personas/base.py` callers — `compose_reply()` failure fallback (scenario e).
- `voice/conversation_store.py` — write failure isolation (scenario f, largely already covered by Sprint 2.7's own `record_turn()` design — this sprint verifies it under adversarial conditions rather than assuming the earlier design holds).
- `voice/pipeline.py` — ensures a failure at any wiring step ends the current turn/session gracefully rather than leaving the pipeline in an inconsistent state.
- `core/module_registry.py` (only if the ManagedModule-fit confirmation above finds a real, specific gap — not a default expectation).

## Expected Classes

None new by default (see Files to Create). Existing `VoiceError` subclasses (from 2.1–2.11) are reused as the typed-exception vocabulary this sprint builds recovery behavior around, rather than inventing a parallel error taxonomy.

## Expected Interfaces

No changes to `ManagedModule` unless Objectives' confirmation step finds a specific, demonstrated gap — and if so, that gap and its proposed resolution must be presented as a plan before any interface change, per this task's constraint against introducing architecture changes unilaterally.

## Expected Functions

No new public functions expected; existing functions across the Files to Modify list above gain additional caught-exception paths and corresponding regression tests, in the same style as the Post-Release Review's fixes in [sprint_1_9.md](sprint_1_9.md) (e.g. `ModuleRegistry.has()` guarding `check_health()`/`restart_module()` against an unregistered name).

## Data Flow

Not a new pipeline — this sprint adds recovery branches at existing Data Flow points from Sprints 2.1–2.12. Representative failure-path additions:

```
(a) MicrophoneManager.read_frame() raises MicrophoneError (device unplugged)
      → VoiceSessionManager.end_session(ERROR), logged
      → QuietModeController.deactivate() (returns to DORMANT, not crashed)

(b) WhisperSpeechToText fails to load / crashes mid-inference
      → health_check() → False → CoreManager.restart_module("stt")
      → if still failing: voice input reported unavailable via module_states(), Core continues running

(c) CoquiTextToSpeech unavailable at startup
      → JARMINEI runs with voice output disabled; status visible in Status Panel / Debug Console
      → (a text-only fallback path is a reasonable improvement to consider here, provided it introduces
         no new user-facing feature beyond making an existing failure visible — confirm scope before adding one)

(d) WakeWordDetector's background thread dies unexpectedly
      → health_check() → False → CoreManager.restart_module("wake_word") relaunches it

(e) Persona.compose_reply() raises
      → PersonaManager catches, logs, returns a safe generic fallback reply — turn continues, not aborted

(f) ConversationSessionStore.record_turn() write fails (disk full/locked)
      → logged, turn dropped, session continues uninterrupted
```

## Acceptance Criteria

- Each of the six scenarios above (a–f) has a dedicated regression test proving the failure is contained and the rest of the pipeline keeps functioning.
- No scenario results in an unhandled exception reaching `CoreManager` or crashing `main.py`.
- Every degraded-module state is visible via the existing `module_states()` / Status Panel / Debug Console — Explainability Rule applied to failure states, not just normal operation ("JARMINEI should always provide the reasoning behind its behavior" extends to *why something isn't working*).
- The `ManagedModule` interface-fit question is explicitly answered in this sprint's completion report (once implemented): confirmed sufficient, or a specific, presented gap.

## Testing Checklist

- [ ] Regression: simulated mid-session microphone disconnect ends the session and returns to Quiet Mode without crashing.
- [ ] Regression: forced Whisper model load failure triggers `restart_module()` and, on continued failure, leaves Core running with voice input marked unavailable.
- [ ] Regression: forced Coqui unavailability leaves Core running with voice output marked unavailable.
- [ ] Regression: forced wake-word thread death is caught by `health_check()` and recovered via `restart_module()`.
- [ ] Regression: a `Persona.compose_reply()` exception yields a safe fallback reply, not a crashed turn.
- [ ] Regression: a forced SQLite write failure during `record_turn()` is logged and does not interrupt the live session.
- [ ] Full regression: entire Level 1 + Level 2 test suite green, no prior test broken by this sprint's changes.

## Documentation Checklist

- [ ] Each modified file's docstring: document the specific failure mode(s) it now handles and why (mirrors the specificity of [sprint_1_9.md](sprint_1_9.md)'s Post-Release Review findings).
- [ ] `docs/STATUS.md` — no phase-status change; this sprint hardens already-complete phases rather than completing a new one.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium — no new architecture, but disciplined, scenario-by-scenario coverage across many files.

## Estimated Development Time

1.5–2 days.

## Risks

- **Enumerated scenarios (a–f) are informed by realistic laptop conditions but are not guaranteed exhaustive** — exactly the same caveat Sprint 1.9's Post-Release Review recorded about its own findings; treat this sprint as thorough, not infallible, and expect Level 6 (Sprint 6.3 Stress & Recovery Testing) to catch anything still missed at a whole-system level.
- **Over-engineering temptation**: a hardening-focused sprint invites speculative resilience machinery (generic retry frameworks, circuit breakers) beyond what any of the six real scenarios need — resist; match the fix to the specific failure, per the Development Philosophy's stance against premature generality.

## Next Sprint

2.14 — Integration Testing & Level Freeze.
