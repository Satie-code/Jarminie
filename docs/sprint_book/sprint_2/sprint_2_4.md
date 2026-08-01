# Sprint 2.4 — Text-to-Speech Engine (Coqui, dual voice)

## Sprint ID

2.4

## Sprint Name

Text-to-Speech Engine (Coqui, dual voice)

## Purpose

Generate spoken responses per [02_System_Architecture.md](../02_System_Architecture.md)'s Voice Engine responsibility: *"Generate spoken responses."* Must support both persona voices from day one — [03_Engineering_Standards.md](../03_Engineering_Standards.md) is explicit: *"Voice selection should be handled through the Persona System rather than hardcoded."*

## Engineering Rationale

This sprint has no dependency on the wake-word/mic chain (2.1–2.3) — synthesis is a pure function of `(text, voice_id)` — so it can be built independently and in parallel with those sprints if the team chooses to; it is sequenced here only to keep the roadmap linear. Voice selection is a `voice_id` string parameter, never a hardcoded branch on persona name, so `CoquiTextToSpeech` has zero knowledge that Jarvis/Minie exist — that mapping lives entirely in [config/schema.py](../../config/schema.py)'s `VoiceConfig.jarvis_voice_id` / `minie_voice_id`, read by the Persona classes (2.9, 2.10), not by this module.

## Objectives

- A `TextToSpeech` interface and `CoquiTextToSpeech` implementation that loads voice models once at `start()` and synthesizes+plays audio for a given `(text, voice_id)` pair.
- Playback must not block the calling thread indefinitely in a way that prevents the rest of the pipeline (e.g. session timeout tracking) from making progress — synthesis/playback should be a bounded, awaitable operation, not a fire-and-forget void with no completion signal.
- No text content logged above DEBUG-with-redaction, same rule as Sprint 2.3.

## Dependencies

1.2 (Configuration Manager — `VoiceConfig.jarvis_voice_id`/`minie_voice_id`, `ModelConfig`)

## Files to Create

- `voice/text_to_speech.py` — `AudioOutput` (Protocol), `SoundDeviceAudioOutput` (concrete impl), `TextToSpeech` (Protocol), `CoquiTextToSpeech`.
- `tests/unit/voice/test_text_to_speech.py`

## Files to Modify

- `voice/errors.py` — add `TextToSpeechError(VoiceError)`.
- `config/schema.py` — add `tts_model: str = "tts_models/en/vctk/vits"` to `ModelConfig` (the Coqui model identifier; a single multi-speaker model can serve both `jarvis_voice_id` and `minie_voice_id` as different speaker IDs within it, avoiding two separate model loads).
- `requirements.txt` — confirm `sounddevice>=0.4` (added in Sprint 2.1) covers output playback too; no second audio library needed.

## Expected Classes

- `AudioOutput(Protocol)` — `play(self, audio: bytes, sample_rate_hz: int) -> None`. Interface-first, mirrors `AudioBackend` (2.1) on the output side.
- `SoundDeviceAudioOutput(AudioOutput)` — wraps `sounddevice.play`/`wait`.
- `TextToSpeech(Protocol)` — `speak(self, text: str, voice_id: str) -> None`.
- `CoquiTextToSpeech(ManagedModule, TextToSpeech)` — constructor DI: `(model_config: ModelConfig, output: AudioOutput)`.

## Expected Interfaces

- `TextToSpeech(Protocol)` — the interface Persona classes (2.9+) depend on, never the concrete Coqui type (Interface First Design).
- `ManagedModule` (reused) — `start()` loads the Coqui model; `stop()` releases it; `health_check()` reports whether the model is loaded and the output device is available.

## Expected Functions

- `CoquiTextToSpeech.speak(text: str, voice_id: str) -> None` — synthesizes then plays; blocks until playback completes (bounded, since utterances are short) so the caller (Voice Session Manager, 2.5) can reliably sequence "speak, then resume listening."
- `CoquiTextToSpeech.speak(text, voice_id)` raises `TextToSpeechError` for an unrecognized `voice_id` or a synthesis/playback failure — never silently no-ops.

## Data Flow

```
Persona.compose_reply() output (text) + persona.voice_id
      ↓
CoquiTextToSpeech.speak(text, voice_id)
      ↓
Coqui model synthesis → audio bytes
      ↓
SoundDeviceAudioOutput.play() → speakers
```

## Acceptance Criteria

- `speak()` with `jarvis_voice_id` and with `minie_voice_id` both produce audio through the same running model instance (no reload between calls) — verified against a fake `AudioOutput` capturing the buffer, not requiring an actual audible check in automated tests.
- An unrecognized `voice_id` raises `TextToSpeechError` rather than silently falling back to a default voice (the Persona system must never be allowed to think the wrong voice spoke).
- `health_check()` reflects both model-loaded state and output-device availability.
- No spoken text appears in logs above DEBUG-with-redaction.

## Testing Checklist

- [ ] Unit: `start()`/`stop()` model lifecycle (mocked Coqui model).
- [ ] Unit: `speak()` routes to the correct speaker/voice for both configured `voice_id`s.
- [ ] Unit: an unknown `voice_id` raises `TextToSpeechError`.
- [ ] Unit: a synthesis exception is wrapped in `TextToSpeechError`, not raised raw.
- [ ] Real (manual, not CI): synthesize and play a short phrase for each persona voice, confirm audibly distinct output.

## Documentation Checklist

- [ ] `voice/text_to_speech.py` docstring: voice_id contract, why voice selection lives in config/Persona rather than here.
- [ ] `docs/STATUS.md` — no change (Phase 2.1 still in progress).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High — multi-speaker model configuration and playback-completion timing are the real unknowns; the interface itself is simple.

## Estimated Development Time

1.5–2 days.

## Risks

- **Single multi-speaker model may not cleanly provide two sufficiently distinct voices** ("professional male" vs "soft female" per Part 2) — if the chosen `tts_model` can't, the fallback is two separate single-speaker models loaded at `start()`, a config-only change (`ModelConfig`), not an architecture change. Flag for confirmation once real audio is heard, not assumed resolved here.
- **Blocking playback** could make `VoiceSessionManager` (2.5) unresponsive to a simultaneous timeout tick during a long response — bounded in practice by response length, but worth a specific test once 2.5 exists.

## Next Sprint

2.5 — Voice Session Manager & Timeout.

---

## Sprint Completion Report

### Summary

Implemented `AudioOutput`/`SoundDeviceAudioOutput`, `TextToSpeech`, and `CoquiTextToSpeech`. Automated tests mock `TTS.api.TTS` (per this sprint's own Testing Checklist). Getting the real, non-mocked Coqui model chain working surfaced **four separate real dependency issues in sequence**, each resolved except the last, which needs a decision from you before real audio can be verified.

### Files Created

- `voice/text_to_speech.py` — `AudioOutput`, `SoundDeviceAudioOutput`, `TextToSpeech`, `CoquiTextToSpeech`.
- `tests/unit/voice/test_text_to_speech.py` (12 tests).

### Files Modified

- `voice/errors.py` — added `TextToSpeechError`.
- `config/schema.py` / `config/defaults.yaml` — `ModelConfig.tts_model: str = "tts_models/en/vctk/vits"`.
- `requirements.txt` — `coqui-tts>=0.27` → `coqui-tts[codec]>=0.27`, plus an explicit `torchaudio` line.
- `docs/backlog/technical_debt.md` — items 6 (resolved) and 7 (open, needs your input).
- `.venv` — installed `coqui-tts[codec]`, `torchaudio`, `transformers==4.57.6` (downgraded from an incompatible 5.14.1).

### Engineering Decisions

- **Real Coqui API confirmed to match the sprint's assumed design exactly**: `TTS(model_name=...)` and `.tts(text=..., speaker=...)` — no code changes needed once the import chain worked.
- **`voice_id` validation only enforced when the model actually reports speakers** (`self._known_speakers` non-empty) — a single-speaker model has no list to validate against, so any `voice_id` is accepted in that case (covered by its own test).
- **Same lazy-import + sensitive-logging pattern as Sprints 2.2/2.3** — `from TTS.api import TTS` stays inside `start()`, not at module level; spoken text logged only at DEBUG with `extra={"sensitive": True}`.

### The dependency chain saga (all discovered by actually trying to load the model, not from documentation)

1. `ModuleNotFoundError: torchaudio` — not declared as coqui-tts's dependency despite being imported by its code. **Fixed**: installed `torchaudio` explicitly.
2. `ImportError: isin_mps_friendly` — coqui-tts 0.27.5's XTTS code needs `transformers<5`; pip had resolved the newest 5.14.1. **Fixed**: pinned `transformers<5,>=4.57` (installed 4.57.6).
3. `ImportError: ...torchcodec library is required...` — PyTorch 2.9+ changed its audio I/O backend. **Fixed**: installed `coqui-tts[codec]`.
4. `FileNotFoundError: No espeak backend found` — the VITS/VCTK model's default phonemizer needs the **`espeak-ng` system binary**, not a Python package. **Not fixed** — this is an OS-level install (bigger, less reversible than anything else so far), so I stopped and did not install it without asking. See Remaining Risks.

### Tests Added

12 in `tests/unit/voice/test_text_to_speech.py` (model load/idempotency/failure, stop/health-check, speak-before-start, unrecognized-voice_id rejection, correct routing for two configured voice_ids verified against the *same* loaded model instance, no-known-speakers edge case, synthesis-failure and playback-failure wrapping). **145/145 total passing** (133 from Sprints 2.1–2.3 + 12 new), `ruff check .` clean.

### Documentation Updated

`voice/text_to_speech.py` docstrings. `docs/backlog/technical_debt.md` (items 6, 7). This Sprint Completion Report. `docs/STATUS.md` intentionally unchanged, per this sprint's own Documentation Checklist.

### Acceptance Criteria Checklist

- ✔ `speak()` with two different `voice_id`s both route through the same running model instance (verified via mock — `TTS()` called exactly once across both calls).
- ✔ An unrecognized `voice_id` raises `TextToSpeechError`, never a silent fallback.
- ✔ `health_check()` reflects model-loaded state.
- ✔ No spoken text appears in logs above DEBUG-with-redaction.
- ✔ **Verified** (updated below): the real, audible-distinctness check was completed once `espeak-ng` was installed — see "Real Audio Verification & Voice Selection" below.

### Real Audio Verification & Voice Selection (2026-07-17)

User installed `espeak-ng-x64.msi` (v1.49.2) themselves with administrator rights after a first silent-install attempt from this session failed on insufficient privileges (error 1925). The installer didn't add its directory to `PATH`, so it was added to the current Windows user's `PATH` (`HKCU\Environment`, no admin required) so Coqui's `shutil.which("espeak-ng")` check succeeds in new processes.

With `espeak-ng` available, the real `tts_models/en/vctk/vits` model loaded successfully (109 speakers, 22050 Hz output) and was exercised end-to-end through the real `CoquiTextToSpeech`/`SoundDeviceAudioOutput` classes — genuine synthesis and playback through this machine's real speakers, not mocks.

Picking real speaker IDs for `jarvis_voice_id`/`minie_voice_id` had two obstacles: (1) the model's speaker index is known to *not* reliably match VCTK's published gender/accent metadata for this specific checkpoint ([coqui-ai/TTS#2258](https://github.com/coqui-ai/TTS/issues/2258)), so the public metadata couldn't be trusted; (2) Claude cannot hear synthesized audio, so no amount of listening-in-code substitutes for genuine perceptual judgment. Resolved by combining both: all 108 real speakers were synthesized once and analyzed with `librosa` (mean fundamental frequency + RMS energy) to objectively shortlist "confident" (low pitch, high energy) vs. "soft/gentle" (high pitch, lower energy) candidates — a measurable proxy Claude *can* compute, standing in for a judgment it can't make directly. The user then listened to the shortlists (played live through the real speakers, iterating across several rounds) and made the actual perceptual call.

**Final, user-confirmed choices**: `jarvis_voice_id = "p340"` (≈117 Hz mean pitch, high energy), `minie_voice_id = "p243"` (≈256 Hz mean pitch) — both updated in `config/schema.py`, `config/defaults.yaml`, and `tests/unit/voice/conftest.py`'s fixture defaults (Sprint 1.2's `"jarvis_default"`/`"minie_default"` placeholders retired). Full regression re-run: 145/145 passing, `ruff check .` clean.

### Remaining Risks

- The acoustic-proxy shortlisting (pitch/energy) is a good objective narrowing heuristic, not a guarantee of "confident"/"gentle" perception on its own — the user's own listening pass is what actually confirmed the final choice, which is exactly why this two-step process (compute a shortlist, then have a human judge it) was used rather than picking automatically from the numbers alone.
- `espeak-ng`'s `PATH` entry is user-scoped (`HKCU\Environment`), not machine-wide — a different Windows user account on this same machine, or a fresh environment/CI runner, won't have it without repeating the same `PATH` addition (or their own `espeak-ng` install). Worth remembering if `main.py` is ever run under a different account or a clean CI image.

### Technical Debt

Items 6, 7, and 8 (dependency chain, espeak-ng install, voice ID selection) all resolved and documented in `docs/backlog/technical_debt.md`. None outstanding from this sprint.

### Recommendations for Sprint 2.5

- Build the TTS→STT round-trip test recommended at the end of Sprint 2.3 — now that both real models work end-to-end, this closes Whisper's real-content verification gap with a synthesized-then-transcribed known phrase, no human recording needed.
- `VoiceSessionManager` (2.5) will be the first real caller sequencing `WhisperSpeechToText.transcribe()` and `CoquiTextToSpeech.speak()` together — worth double-checking the blocking-playback risk flagged in this sprint's own spec once that exists.
- If Sprint 2.5+ work happens under a different Windows account or CI environment, re-check `espeak-ng` is discoverable there too (see Remaining Risks).
