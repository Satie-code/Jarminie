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

---

## Sprint Completion Report

### Summary

Implemented `TranscriptionResult`, `SpeechToText` (Protocol), and `WhisperSpeechToText`. Automated tests mock `whisper.load_model()` (per this sprint's own Testing Checklist); the real, non-mocked verification loaded the actual `base` model and ran real inference on synthetic audio — this confirmed the real `whisper.transcribe()` result-dict shape matches exactly what the mocked tests assumed (`text`/`segments`/`language` keys), and surfaced real CPU-inference timing data. One genuine limitation could not be resolved in this sandboxed session: verifying "known spoken content → correct text" needs an actual human voice recording, which I have no way to produce myself — see Remaining Risks.

### Files Created

- `voice/speech_to_text.py` — `TranscriptionResult`, `SpeechToText`, `WhisperSpeechToText`.
- `tests/unit/voice/test_speech_to_text.py` (9 tests).

### Files Modified

- `voice/errors.py` — added `SpeechToTextError`.
- `docs/backlog/technical_debt.md` — item 1 updated (`openai-whisper`/`torch` now installed).
- `.venv` — installed `openai-whisper` (pulls in `torch`, `tiktoken`, `numba`, etc. — the single largest dependency installed so far in this project).

### Engineering Decisions

- **`whisper`/`numpy` imports kept lazy** (inside `start()`/`transcribe()`, not at module top-level) — same rationale as `OpenWakeWordEngine` (Sprint 2.2): importing this module for its `SpeechToText` Protocol/`TranscriptionResult` dataclass shouldn't pay the cost of a heavy ML library import when a caller only needs a fake for testing.
- **`start()` made idempotent** (returns immediately if a model is already loaded) rather than reloading — matches the acceptance criterion "a second start() call... does not reload it" literally, verified by asserting `load_model` is called exactly once across two `start()` calls.
- **Confidence derived from Whisper's `avg_logprob` via `exp()`**, converting a log-probability into a roughly 0–1 scale — explicitly named `average_confidence` and documented as unrelated to Part 2's Dynamic Memory confidence score, per the sprint spec's own explicit warning against conflating the two.
- **Two-tier logging**: transcription duration/confidence (non-sensitive metadata) logged at INFO; the actual transcript text logged only at DEBUG with `extra={"sensitive": True}` — this is the *first real usage* of Sprint 1.3's `SensitiveDataFilter` for its intended purpose (it existed since Sprint 1.3 but nothing had actually invoked it with real conversation-shaped content until now).

### Tests Added

9 in `tests/unit/voice/test_speech_to_text.py` (model load/idempotency/failure, stop/health-check lifecycle, transcribe-before-start, correct-result parsing including the confidence formula, zero-segment edge case, inference-failure wrapping). **133/133 total passing** (124 from Sprints 2.1–2.2 + 9 new), `ruff check .` clean.

**Real (non-mocked) verification**: loaded the actual Whisper `base` model (139MB, downloaded on first use) and ran real inference on 2 seconds of synthetic silent audio — model load took ~32s (one-time, includes download), `transcribe()` took ~2.3s, returned `{"text": "", "segments": [], "language": ...}` (correctly no hallucinated speech on silence). This confirms the real library's result shape matches what the mocked unit tests assumed, and that FP16 is unsupported on this CPU (falls back to FP32 automatically, with a warning) — concrete data point for this sprint's own "CPU-only inference latency" Risk.

### Documentation Updated

`voice/speech_to_text.py` docstrings (interface contract, lazy-import rationale, sensitive-logging discipline). `docs/backlog/technical_debt.md`. This Sprint Completion Report. `docs/STATUS.md` intentionally left unchanged, per this sprint's own Documentation Checklist.

### Acceptance Criteria Checklist

- ✔ `start()` loads the model exactly once; a repeated `start()` does not reload (verified via mock call count).
- ✖ *Partially verified*: `transcribe()` was confirmed correct against the real model's actual output shape and against silent audio (no false transcription) — but "known-content fixture audio → expected text" could not be checked, since no real human speech sample exists in this environment (see Remaining Risks).
- ✔ A transcription failure raises `SpeechToTextError`, logged, never a raw exception.
- ✔ No conversation text appears in logs above DEBUG, and only via the redaction filter.

### Remaining Risks

- **The "known-content" real-speech acceptance criterion is unverified** — I have no way to generate or supply an actual recorded human voice sample in this sandboxed session. Recommend one of: (a) you provide a short recorded WAV (e.g. "hello jarminei") for a manual one-off check, or (b) defer this specific verification to Sprint 2.4/2.12 — once Coqui TTS exists, a TTS→STT round-trip test (synthesize a known phrase, transcribe it back, compare) closes this gap without needing any human-recorded audio at all. I'd suggest (b) as the more durable fix.
- CPU-only inference latency is real and non-trivial (~2.3s for 2s of audio on this machine) — acceptable for now per the sprint's own risk framing, but worth re-measuring once real conversational audio (not silence) is available.
- Cold-start model load (~32s including download) will affect `CoreManager.startup()` once this module is registered (Sprint 2.12) — flagged, not fixed here, exactly as this sprint's own Risks anticipated.

### Technical Debt

None introduced.

### Recommendations for Sprint 2.4

- Build a TTS→STT round-trip test once `CoquiTextToSpeech` exists (per Remaining Risks above) — this is the cleanest way to close Sprint 2.3's one open verification gap without needing a human-supplied recording.
- Budget for `coqui-tts`'s own install/model-download surprises, same pattern as this sprint's whisper install and Sprint 2.2's tflite/onnx discovery — each new ML dependency in this project has so far surfaced at least one real, unanticipated platform detail.

---

## Post-Sprint Fix (2026-07-17, during Sprint 2.5)

Sprint 2.5's real end-to-end verification (wiring this module together with `MicrophoneManager` and `CoquiTextToSpeech` for the first time) captured genuine room silence and got back a fluent, entirely fabricated sentence from Whisper — a real Whisper hallucination, not a bug in this module's own logic at the time. Investigated against Whisper's own source (`transcribe.py`): its built-in `no_speech_threshold` check (default 0.6) is overridden internally whenever a hallucinated segment's `avg_logprob` looks confident enough ("don't skip if the logprob is high enough, despite the no_speech_prob") — so relying on Whisper's own default leniency doesn't reliably prevent this. User asked for it fixed immediately rather than deferred.

**Fix**: added `ModelConfig.whisper_no_speech_threshold` (default 0.6, validated in `(0, 1]`). `WhisperSpeechToText.transcribe()` now computes the average per-segment `no_speech_prob` itself and forces `text=""` whenever it's at or above the threshold — unconditionally, overriding whatever Whisper's own internal logic decided to keep. `TranscriptionResult` gained a `no_speech_probability` field for observability (not something callers need to re-check themselves, since suppression already happened). This deliberately biases toward missing quiet real speech over fabricating fake speech, per the Human First Rule — JARMINEI should never act on words the user never said.

**Verification**: 5 new unit tests (suppression on high `no_speech_prob` despite confident `avg_logprob`, text kept when `no_speech_prob` is low, configurable threshold respected, both existing tests updated with realistic segment shapes). Real, non-mocked confirmation: re-ran the *exact* real ambient-audio sample that produced the original hallucination through the fixed code 5 times — `no_speech_probability=0.762` (correctly above the 0.6 threshold) and `text=''` every time, deterministically. Full suite: 164/164 passing, `ruff check .` clean. Tracked as `backlog/technical_debt.md` item 9 (resolved).

## Post-Sprint Fix (2026-07-17, post-release real-hardware testing)

Real end-to-end use on the actual target laptop (the manual verification step Sprint 2.14 flagged as outstanding) surfaced a second real bug, unrelated to the hallucination fix above: Whisper's "base" model misheard the uncommon proper noun "Minie" — "talk to minie" was transcribed as "talk to my knee", silently breaking `PersonaManager.detect_explicit_selection()`'s substring match against `minie_trigger_phrases` (Sprint 2.11). No automated test could have caught this, since none of them speak real audio.

**Fix**: added `ModelConfig.whisper_initial_prompt` (default: a short sentence naming both personas — "Jarvis and Minie are JARMINEI's two personas."), passed through as Whisper's own `initial_prompt` parameter on every `transcribe()` call — a standard, well-known technique for biasing a Whisper model's output toward specific vocabulary it wouldn't otherwise favor. Passing an empty string resolves to `None` (Whisper's own "no bias" value), so the field can be cleared entirely if a future user wants unprompted transcription. As a pragmatic safety net — a prompt improves but doesn't guarantee recognition of an unusual word — `VoiceConfig.minie_trigger_phrases` (Sprint 2.11, see that file's own note) was also expanded with common mishearing variants ("my knee", "minnie").

**Verification**: 2 new unit tests confirming the configured prompt (and the empty-string → `None` case) actually reaches `model.transcribe()`'s call arguments. Full suite passing, `ruff check .` clean. Tracked as `backlog/technical_debt.md` item 12.
