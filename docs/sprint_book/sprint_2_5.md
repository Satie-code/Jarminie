# Sprint 2.5 — Voice Session Manager & Timeout

## Sprint ID

2.5

## Sprint Name

Voice Session Manager & Timeout

## Purpose

Own the lifecycle of one active voice interaction — from the moment listening becomes active through however many spoken turns occur, until silence or explicit end returns control to Quiet Mode. Implements [02_System_Architecture.md](../02_System_Architecture.md)'s Voice Engine responsibility: *"Return to standby after inactivity."*

## Engineering Rationale

This is deliberately a **turn-timing and lifecycle** module, not a conversation-history module — it tracks *that* turns are happening and *when* the last one ended, not *what was said* beyond the single in-flight turn. Persisted multi-turn history is Conversation Session Store's job (2.7, Phase 2.2), a different Phase with a different responsibility (Single Responsibility Rule) and explicitly out of this Level's memory-adjacent exclusions if conflated carelessly — this module holds only ephemeral, in-memory timing state that vanishes when the session ends.

## Objectives

- A `VoiceSessionManager` that, once told a session has begun, orchestrates one full turn: switch the microphone to active capture, buffer audio until an end-of-utterance condition, hand the buffer to Speech-to-Text, and (once a reply exists) hand it to Text-to-Speech.
- A configurable silence timeout that ends the session and returns the microphone to passive mode if the user doesn't speak again within the window.
- Session end is reported via an event so Quiet Mode Controller (2.6) can react — this module does not know Quiet Mode exists (Interface First / DI, same pattern as Wake Word Detector's `on_detected`).

## Dependencies

2.3 (Speech-to-Text Engine), 2.4 (Text-to-Speech Engine), 2.1 (Microphone Manager, via mode switching)

## Files to Create

- `voice/session_manager.py` — `SessionState` (Enum), `VoiceSession` (dataclass), `SessionEndReason` (Enum), `VoiceSessionManager`.
- `tests/unit/voice/test_session_manager.py`

## Files to Modify

- `voice/errors.py` — add `SessionError(VoiceError)`.
- `config/schema.py` — add `session_timeout_seconds: float = 30.0` to `VoiceConfig`; add validation (`> 0`) to `AppConfig._validate_voice()`.

## Expected Classes

- `SessionState` (Enum) — `IDLE`, `LISTENING`, `PROCESSING`, `SPEAKING`, `AWAITING_NEXT_TURN`.
- `SessionEndReason` (Enum) — `SILENCE_TIMEOUT`, `EXPLICIT_END`, `ERROR`.
- `VoiceSession` (dataclass) — `session_id: str`, `started_at: datetime`, `last_activity_at: datetime`, `turn_count: int`. Ephemeral only — never written to disk by this module.
- `VoiceSessionManager(ManagedModule)` — constructor DI: `(mic: MicrophoneManager, stt: SpeechToText, tts: TextToSpeech, voice_config: VoiceConfig, on_turn_complete: Callable[[str, str], None], on_session_ended: Callable[[SessionEndReason], None])`. `on_turn_complete` carries `(transcript, session_id)` for Context Manager (2.8) and Conversation Session Store (2.7) to consume — this module has no dependency on either.

## Expected Interfaces

- `ManagedModule` (reused) — `start()`/`stop()` here manage only this module's own background timeout-tracking timer, not the mic/STT/TTS lifecycles (those are started/stopped independently by Core Manager per module); `health_check()` reports whether the timeout tracker is alive.

## Expected Functions

- `VoiceSessionManager.begin_session() -> VoiceSession` — called by Quiet Mode Controller on wake-word detection; switches mic to `ACTIVE_CAPTURE`, starts the silence timer.
- `VoiceSessionManager.end_session(reason: SessionEndReason) -> None` — switches mic back to `PASSIVE_LISTENING`, fires `on_session_ended`.
- `VoiceSessionManager.is_active() -> bool`
- `VoiceSessionManager._on_utterance_ready(audio: bytes) -> None` — internal: calls `stt.transcribe()`, fires `on_turn_complete`, resets the silence timer.
- `VoiceSessionManager.speak_reply(text: str, voice_id: str) -> None` — called once a persona reply exists; delegates to `tts.speak()`, then re-arms listening for the next turn.

## Data Flow

```
Quiet Mode Controller (2.6) → begin_session()
      ↓
mic.set_mode(ACTIVE_CAPTURE) + silence timer armed
      ↓
buffered utterance → stt.transcribe() → on_turn_complete(transcript, session_id)
      ↓                                          ↓
      |                              Context Manager (2.8) / Persona reply
      ↓                                          ↓
speak_reply(text, voice_id) → tts.speak() → silence timer re-armed
      ↓ (timeout, no further speech)
end_session(SILENCE_TIMEOUT) → mic.set_mode(PASSIVE_LISTENING) → on_session_ended
```

## Acceptance Criteria

- `begin_session()` switches the microphone to `ACTIVE_CAPTURE`; `end_session()` always returns it to `PASSIVE_LISTENING`, even when ending due to an error.
- A session with no further speech for `session_timeout_seconds` ends automatically with `SessionEndReason.SILENCE_TIMEOUT`.
- Each completed turn resets the timeout window (an ongoing conversation does not time out mid-use, matching Part 2's "after inactivity" wording — inactivity, not elapsed session length).
- An `stt.transcribe()` failure ends the current turn gracefully (logged, `SessionError` surfaced) without leaving the microphone stuck in `ACTIVE_CAPTURE`.

## Testing Checklist

- [ ] Unit: `begin_session()`/`end_session()` mic mode transitions (fake mic, STT, TTS).
- [ ] Unit: silence timeout fires `end_session(SILENCE_TIMEOUT)` after the configured window with no activity.
- [ ] Unit: a completed turn resets the timeout window (no premature timeout mid-conversation).
- [ ] Unit: an `SpeechToTextError` from `stt.transcribe()` results in a graceful `end_session(ERROR)`, mic returned to passive, not left active.
- [ ] Unit: `AppConfig._validate_voice()` rejects a non-positive `session_timeout_seconds`.

## Documentation Checklist

- [ ] `voice/session_manager.py` docstring: state diagram, explicit note that this holds no persisted history (contrast with 2.7).
- [ ] `docs/STATUS.md` — no change (Phase 2.1 still in progress until 2.6).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium — timer/state-machine correctness under concurrent events (a new utterance arriving right as a timeout fires) is the main design challenge.

## Estimated Development Time

1.5 days.

## Risks

- **Race between "reply finishes speaking" and "silence timer expiring"** could double-fire `end_session()` — needs an explicit guard (idempotent `end_session()`, only the first call takes effect) rather than assuming callers coordinate perfectly.
- **Utterance-boundary detection** (when has the user stopped talking, as opposed to just pausing) is only lightly specified here and depends on whatever `MicrophoneManager`/STT buffering strategy proves practical — flag for a concrete decision during implementation rather than over-specifying an unverified approach now.

## Next Sprint

2.6 — Quiet Mode Controller.

---

## Sprint Completion Report

### Summary

Implemented `SessionState`, `SessionEndReason`, `VoiceSession`, and `VoiceSessionManager` — the five-state turn cycle (IDLE → LISTENING → PROCESSING → AWAITING_NEXT_TURN → SPEAKING → LISTENING...) described in the module's own docstring. Resolved the sprint's own flagged "utterance-boundary detection" design gap with simple energy-based (RMS) silence detection, not a separate VAD model — proportionate to what a turn-taking assistant needs. Verified against fakes (automated suite) **and** a real end-to-end run wiring the actual `MicrophoneManager`, `WhisperSpeechToText`, and `CoquiTextToSpeech` together for the first time — which surfaced a real, worth-discussing finding (see Remaining Risks).

### Files Created

- `voice/session_manager.py` — `SessionState`, `SessionEndReason`, `VoiceSession`, `VoiceSessionManager`.
- `tests/unit/voice/test_session_manager.py` (10 tests).

### Files Modified

- `voice/errors.py` — added `SessionError`.
- `config/schema.py` / `config/defaults.yaml` — `VoiceConfig` gained `session_timeout_seconds: float = 30.0` (from the sprint spec) plus three fields resolving the utterance-boundary design gap: `utterance_silence_ms: float = 700.0`, `utterance_silence_threshold: float = 0.02`, `max_utterance_seconds: float = 30.0`. Validation added to `AppConfig._validate_voice()` for all four.
- `tests/unit/voice/conftest.py` — `FakeSpeechToText`, `FakeTextToSpeech`, `loud_frame`/`quiet_frame` fixtures, and a `frame_queue` on `FakeAudioBackend` so tests can script a loud-then-silent sequence.
- `tests/unit/config/test_schema.py` — 4 new validation tests.

### Engineering Decisions

- **Utterance-boundary detection resolved as energy-based (RMS) silence detection**, not a separate VAD model or a fixed-duration recording: buffer frames while speech-level energy is present, cut once trailing silence exceeds `utterance_silence_ms` *after* some speech was actually heard (the `has_spoken` gate prevents cutting on leading silence before the user starts talking). Computed with stdlib `array`/`math`, no numpy dependency added to this module.
- **Two independent timing mechanisms kept deliberately separate**: `session_timeout_seconds` (inter-turn, background watchdog thread, runs for this module's whole `start()`/`stop()` lifetime) vs. `utterance_silence_ms`/`max_utterance_seconds` (intra-utterance, only active during a single capture). Conflating them would have made the timeout math confusing — a long single utterance and a long pause between turns are different concerns.
- **`max_utterance_seconds` safety cap** (30s default) — not requested by the sprint spec, added as a Resource Protection measure against unbounded buffering if silence detection never triggers (e.g., continuous background noise sitting above the threshold). Flagged explicitly here rather than silently added.
- **`end_session()`'s double-fire race (flagged in the sprint's own Risks) resolved with a lock + idempotency flag** — verified by a dedicated test (`test_end_session_is_idempotent`) calling it twice and confirming only the first call's reason is recorded.
- **The five-state cycle's `AWAITING_NEXT_TURN` state** represents the gap between a turn's transcript being ready (`on_turn_complete` fired) and the external caller (persona composition, Sprint 2.9+) actually invoking `speak_reply()` — the session-loop thread blocks on a `threading.Event` during this gap rather than polling, so it costs nothing while idle.

### Tests Added

10 in `tests/unit/voice/test_session_manager.py` (mic mode transitions on begin/end, end-session idempotency, utterance-boundary detection against a scripted loud-then-silent frame sequence, speak_reply re-arming listening for a second turn, speak_reply-outside-session error, STT-failure-ends-session-gracefully, silence-timeout-ends-session, completed-turn-resets-the-timeout-window, max_utterance_seconds safety cap), 4 in `tests/unit/config/test_schema.py`. **159/159 total passing** (145 from Sprints 2.1–2.4 + 14 new), `ruff check .` clean, no flakiness across 5 repeated runs of the timing-sensitive test file.

**Real (non-mocked) verification**: constructed the actual `MicrophoneManager`, `WhisperSpeechToText`, and `CoquiTextToSpeech` together (first time these three real modules have been wired into one running pipeline), began a real session, captured ~2 real seconds of this room's ambient audio via `max_utterance_seconds`, transcribed it with the real Whisper model, and spoke a real reply through the real Coqui model — full real round trip, session ended cleanly.

### Documentation Updated

`voice/session_manager.py`'s module docstring (state diagram, the two-timing-mechanisms distinction, why energy-based detection was chosen). This Sprint Completion Report. `docs/STATUS.md` intentionally unchanged, per this sprint's own Documentation Checklist (Phase 2.1 stays "in progress" until Sprint 2.6 closes Quiet Mode).

### Acceptance Criteria Checklist

- ✔ `begin_session()` switches the mic to `ACTIVE_CAPTURE`; `end_session()` always returns it to `PASSIVE_LISTENING`, including on the error path (verified for both the fake-based test and the real end-to-end run).
- ✔ A session with no further speech for `session_timeout_seconds` ends automatically with `SILENCE_TIMEOUT`.
- ✔ A completed turn resets the timeout window (verified: session still active well after what would have been the original deadline).
- ✔ An `stt.transcribe()` failure ends the session gracefully (`ERROR`), mic returned to passive, not left active.

### Remaining Risks

- ~~Whisper hallucinated a plausible-sounding sentence from real ambient room noise during the real end-to-end test~~ — **resolved same-day, at the user's request**: see `sprint_2_3.md`'s Post-Sprint Fix and `backlog/technical_debt.md` item 9. `WhisperSpeechToText` now forces empty text whenever its average `no_speech_prob` crosses a configurable threshold, verified against the exact real audio sample that produced the original hallucination (deterministically suppressed across 5 repeated runs).
- The RMS threshold and utterance-silence duration are both, like `wake_word_sensitivity`, starting points rather than validated values — real tuning needs a real conversational environment, deferred to Sprint 2.12 integration as the project's established pattern for this category of parameter.

### Technical Debt

None outstanding. The Whisper hallucination/`no_speech_prob` finding was resolved same-day (see above), not deferred.

### Recommendations for Sprint 2.6

- Quiet Mode Controller's `_on_session_ended` wiring should treat `SessionEndReason.ERROR` the same as any other end reason for returning to `DORMANT` — nothing in this sprint's design requires Quiet Mode to distinguish error-ended sessions from normal ones, but worth confirming that's still true once 2.6 is written.
