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

## Sprint Completion Report (2026-07-17)

282/282 tests passing project-wide (256 prior + 26 new), `ruff check .` clean, stable across 3 repeated full-suite runs. `docs/STATUS.md` intentionally **not touched** — per this sprint's own Documentation Checklist, hardening an already-complete phase doesn't change its status.

### Scenario-by-scenario

- **(a) Microphone disconnect** — Found a real gap: `MicrophoneManager.stop()` called `self._backend.close()` with no exception handling; a real disconnected device can make `close()` itself raise, which would leave `_is_open`/`_mode` never reset (stuck thinking the device is still open). Fixed with try/finally. Session-level containment (`_session_loop()` catching `MicrophoneError` → `end_session(ERROR)`) already existed from Sprint 2.5 and needed no code change, just verification: added a unit test isolating that exact path (previously untested in isolation — only STT failure had a dedicated test) and an integration test proving the full chain reaches `QuietModeController` → `DORMANT`.
- **(b) Whisper failure** — Found a real gap: a crash *during* `transcribe()` (not just a load failure) left `self._model` untouched, so `health_check()` kept reporting healthy even though the last inference attempt failed. Added a `_healthy` flag (same pattern already established by `MicrophoneManager`), set `False` on a crash and restored `True` on the next successful call. Confirmed `start()` was already correctly retry-safe after a failed load (unchanged).
- **(c) Coqui unavailable** — Same `_healthy`-flag gap and fix as (b), applied to `speak()`'s synthesis and playback paths. **Explicitly declined the Data Flow's optional "text-only fallback" suggestion** — that's new user-facing behavior, not failure containment, and the sprint's own text says to "confirm scope before adding one"; existing behavior (Core continues running, TTS marked failed and visible via `module_states()`) already satisfies the actual Acceptance Criteria.
- **(d) Wake-word thread death** — `health_check()` was already accurate (Sprint 2.12's frame-stealing fix). Added a regression test proving the exact `stop()`-then-`start()` sequence `CoreManager.restart_module()` performs successfully relaunches a dead thread. **Did not build an automatic driver that detects a dormant-period thread death and calls `restart_module()` on its own** — see the ManagedModule-fit discussion below for why.
- **(e) Persona.compose_reply() failure** — Added `PersonaManager.compose_reply_safely()`, catching any exception and returning a safe generic fallback reply. Found a more serious, adjacent gap while wiring this in: `CommunicationPipeline._handle_turn_complete()` had **no exception handling at all**, and nothing upstream of it (in `VoiceSessionManager._session_loop()` → `_on_utterance_ready()` → the relay) caught anything either — meaning *any* unexpected failure anywhere in the turn-handling chain would silently kill the session's background thread, leaving it stuck rather than ended. Fixed by wrapping the whole method in try/except, ending the session gracefully (`SessionEndReason.ERROR`) on any unexpected failure — this is the fix the sprint's own "Files to Modify" description for `voice/pipeline.py` was pointing at ("ensures a failure at any wiring step ends the current turn/session gracefully"). Added `tests/unit/voice/test_pipeline.py` — `CommunicationPipeline` had no dedicated unit tests until now, only the Sprint 2.12 integration test.
- **(f) SQLite write failure** — `record_turn()` already failed gracefully per Sprint 2.7's own design (confirmed, no change needed). Writing the adversarial integration test surfaced a **second, more interesting real gap**: `get_recent_turns()` — used by Context Manager for every turn, not just the write path — had no failure handling at all, so a broken connection there aborted the *entire* turn (no reply composed or spoken) rather than degrading to "no context available." Fixed the same way as `record_turn()`: catch, log, return an empty list — Context Manager already treats an empty list as a normal case (Sprint 2.8's own "empty session" handling), so no caller needed to change. This is arguably the most valuable finding of the sprint: the adversarial *integration* test caught something a purely unit-level test of `record_turn()` alone never would have, since the failure path that mattered ran through a *different* method than the one scenario (f) literally named.

### The `ManagedModule` interface-fit question (Objectives, answered explicitly as required)

**Confirmed sufficient — no interface change.** Every fix in this sprint works entirely within the existing `start()`/`stop()`/`health_check()` contract, using the same "boolean `_healthy` flag" pattern already established in Sprint 2.1 (`MicrophoneManager`), now extended to `WhisperSpeechToText` and `CoquiTextToSpeech`. `CoreManager.restart_module()`/`check_health()` (Sprint 1.5) already provide everything the recovery scenarios need.

**One real, deliberately unresolved gap, surfaced rather than papered over**: nothing in the application ever *automatically* calls `check_health()`/`restart_module()` — Status Panel (Sprint 1.7) only *displays* `module_states()`, it doesn't drive recovery. For scenarios (a)/(b)/(c), this doesn't matter much in practice, since a failure there naturally surfaces through a live session ending with `SessionEndReason.ERROR` — a human immediately notices (the conversation just stopped) even without automatic recovery. Scenario (d) is different: a wake-word thread can die during a long **dormant** period with no session active at all, and nothing would notice until someone tried the wake phrase and got no response. Building an automatic periodic health-poll-and-restart driver was considered and **deliberately not built this sprint**, for two independent reasons: (1) this sprint's own Risks explicitly warn against "speculative resilience machinery" beyond what a real scenario needs, and a generic poller is exactly that shape; (2) any design giving `CommunicationPipeline` (or anything else) a live `CoreManager` reference to call `restart_module()` reactively would require changing `main.py`'s composition code to pass it in — and `main.py` is **not** in this sprint's own "Files to Modify" list. Recommended as a concrete, scoped candidate for Sprint 2.14 (Integration Testing & Level Freeze) or Level 6 (6.2 Reliability) — a small, dedicated "health watchdog" component, not folded speculatively into this sprint's hardening.

### Acceptance Criteria Checklist

- ✔ Each of the six scenarios has at least one dedicated regression test (several have two — one isolated unit test plus one full-pipeline integration test).
- ✔ No scenario results in an unhandled exception reaching `CoreManager` or crashing `main.py` — confirmed both by the new tests and by the fact that `CoreManager`'s own `_start_module()`/`_stop_module()`/`check_health()` already wrap every call generically (Sprint 1.5), an existing safety net this sprint's fixes now sit correctly *inside* rather than needing to duplicate.
- ✔ Every degraded-module state is visible via `module_states()` — the `_healthy` flag additions are what make this claim actually *true* for STT/TTS (previously `health_check()` could lie about a crashed-but-still-loaded engine).
- ✔ `ManagedModule` interface-fit question explicitly answered above (sufficient; one real, documented, deliberately-deferred gap).

**Sprint 2.14 (Integration Testing & Level Freeze) is next.**
