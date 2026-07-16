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
