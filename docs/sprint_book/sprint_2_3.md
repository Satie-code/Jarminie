# Sprint 2.3 — Speech-to-Text Engine (Whisper)

## Sprint ID

2.3

## Sprint Name

Speech-to-Text Engine (Whisper)

## Purpose

Convert captured speech into text once a session is active, per [02_System_Architecture.md](../02_System_Architecture.md)'s Voice Engine responsibility: *"Convert speech into text."* Locked technology per [03_Engineering_Standards.md](../03_Engineering_Standards.md) is Whisper, behind an interface abstract enough to support future engines.

## Engineering Rationale

Whisper transcribes a complete utterance buffer, not a live stream — this sprint owns *transcription only*: given a bounded chunk of audio bytes, return text (plus enough metadata for later confidence-adjacent decisions, though real confidence scoring is Level 3's Dynamic Memory Formula, out of scope here). Deciding *when* an utterance is complete (silence detection, turn boundaries) belongs to Voice Session Manager (2.5), not here — Single Responsibility. Building the `SpeechToText` interface now, with `WhisperSpeechToText` as the only implementation, follows the same Interface First pattern already used for `AudioBackend` (2.1) and `WakeWordEngine` (2.2).

## Objectives

- A `SpeechToText` interface and a `WhisperSpeechToText` implementation that loads the configured Whisper model once (at `start()`, not per-call) and transcribes on demand.
- Transcription failures (corrupt buffer, model not loaded, inference exception) are reported clearly, never crash the caller.
- No raw audio or transcript is logged at any level above DEBUG-with-redaction — this is spoken conversation content, the most sensitive data category [03_Engineering_Standards.md](../03_Engineering_Standards.md)'s Logging Strategy warns against ("Sensitive personal information should never be logged").

## Dependencies

2.1 (Microphone Manager — supplies the audio buffer shape), 1.2 (Configuration Manager — `ModelConfig.whisper_model`)

## Files to Create

- `voice/speech_to_text.py` — `TranscriptionResult` (dataclass), `SpeechToText` (Protocol), `WhisperSpeechToText`.
- `tests/unit/voice/test_speech_to_text.py`

## Files to Modify

- `voice/errors.py` — add `SpeechToTextError(VoiceError)`.

## Expected Classes

- `TranscriptionResult` (dataclass) — `text: str`, `average_confidence: float`, `duration_ms: int`. `average_confidence` here is Whisper's own decode confidence (a model output), not the project's Dynamic Memory confidence score from Part 2 — the two are unrelated and must not be conflated in naming or in later sprints.
- `SpeechToText(Protocol)` — `transcribe(self, audio: bytes) -> TranscriptionResult`.
- `WhisperSpeechToText(ManagedModule, SpeechToText)` — constructor DI: `(model_config: ModelConfig)`.

## Expected Interfaces

- `SpeechToText(Protocol)` — the interface a future non-Whisper engine would implement, per the Engineering Rationale above.
- `ManagedModule` (reused) — `start()` loads the Whisper model named by `ModelConfig.whisper_model`; `stop()` releases it; `health_check()` reports whether a model is currently loaded.

## Expected Functions

- `WhisperSpeechToText.transcribe(audio: bytes) -> TranscriptionResult` — raises `SpeechToTextError` (not a bare exception) on inference failure, caught and logged by the caller (Voice Session Manager, 2.5).

## Data Flow

```
VoiceSessionManager (2.5) — buffered utterance bytes (ACTIVE_CAPTURE frames)
      ↓
WhisperSpeechToText.transcribe(audio)
      ↓
TranscriptionResult (text, average_confidence, duration_ms)
      ↓
Context Manager (2.8) / Persona reply composition
```

## Acceptance Criteria

- `start()` loads the configured Whisper model exactly once; a second `start()` call without an intervening `stop()` does not reload it.
- `transcribe()` on a known-content fixture audio file returns the expected text (this is the one Level 2 sprint that benefits from a real, non-mocked model run in addition to unit tests with a fake — Whisper's accuracy on real audio cannot be usefully verified any other way).
- A transcription failure raises `SpeechToTextError`, is logged, and never propagates as a raw/unlabeled exception.
- No conversation text appears in logs above DEBUG, and only with the existing `SensitiveDataFilter` redaction applied (Sprint 1.3).

## Testing Checklist

- [ ] Unit: `start()`/`stop()` model lifecycle (mocked Whisper model — loading a real model in every unit test run would be far too slow, per Resource Protection / Performance Guidelines).
- [ ] Unit: `transcribe()` wraps an inference exception in `SpeechToTextError`.
- [ ] Unit: `health_check()` reflects model-loaded state correctly across start/stop.
- [ ] Real (non-mocked, manually triggered): transcribe a short fixture WAV with known spoken content, confirm reasonable text output — documented as a Testing Checklist item, not part of the automated CI-run unit suite (matches the "no physical hardware in CI" reasoning from Sprint 2.1, extended here to "no multi-hundred-MB model download in CI").

## Documentation Checklist

- [ ] `voice/speech_to_text.py` docstring: interface contract, model load-once behavior, redaction expectation for any future logging additions.
- [ ] `docs/STATUS.md` — no change (Phase 2.1 still in progress).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High — the interface and lifecycle are straightforward; correctness under real audio and inference latency on CPU-only hardware are the real unknowns.

## Estimated Development Time

1.5–2 days.

## Risks

- **CPU-only inference latency.** Whisper's `base` model (the configured default) is chosen specifically to bound this, but real-device latency is unverified until Sprint 2.12's end-to-end run — if unacceptable, the fix is a config change (`ModelConfig.whisper_model`), not an architecture change.
- **Cold-start model load time** on `start()` could make Core Manager's startup sequence noticeably slower once this module is registered (Sprint 2.12) — worth measuring, not assumed acceptable; Resource Protection principle ("performance optimizations should never reduce code quality unless absolutely necessary" cuts both ways — an unacceptably slow startup is itself a quality problem).
- **Sensitive-data logging discipline** is easy to accidentally violate with a stray debug print during implementation — call out explicitly in code review (Development Guide Step 9).

## Next Sprint

2.4 — Text-to-Speech Engine (Coqui, dual voice).
