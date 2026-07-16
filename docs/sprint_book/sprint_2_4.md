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
