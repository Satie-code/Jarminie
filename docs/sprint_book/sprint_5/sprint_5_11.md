# Sprint 5.11 — Voice Personality

## Sprint ID

5.11

## Sprint Name

Voice Personality

## Purpose

Make Jarvis and Minie sound different in *behavior*, not only in the two distinct Coqui speaker IDs already configured since Sprint 2.4 — the brief's own explicit instruction: "Natural pacing. Do not rely solely on different TTS voices. Behavior should also differ." This sprint shapes pacing/emphasis at the text level (pause insertion, phrasing rhythm) before a reply reaches synthesis, and drives real lip-sync on Minie's avatar (Sprint 5.8's `set_mouth_open()`, unwired until now) from actual TTS playback.

## Engineering Rationale

**New sprint.** Two design choices made explicitly:

1. **Text-level shaping, not a new TTS engine or model.** `voice/text_to_speech.py`'s own docstring is explicit: `CoquiTextToSpeech`/`TextToSpeech` own "synthesis and playback only... zero knowledge that Jarvis/Minie exist." This sprint respects that boundary completely — `voice/text_to_speech.py` is **not modified**. Instead, a new `presentation/voice_personality.py` sits between `Persona.compose_reply()`'s already-tone-adapted output (Sprint 5.4) and the existing `TextToSpeech.speak()` call, inserting pacing pauses via Coqui's own supported inline pause markup (a short silence token Coqui's synthesis pipeline already recognizes) at sentence/clause boundaries, weighted by `PresentationState.voice_warmth` (5.5) — Jarvis's own low-`voice_warmth` baseline yields tighter, more clipped pacing (matching the brief's "Confident. Professional. Technical."); Minie's higher baseline yields warmer, slightly more spaced-out, gentler pacing ("Warm. Gentle. Comforting.").
2. **Real lip-sync closes a sprint-5.8-named gap, not new architecture.** `VTubeStudioAvatarRenderer.set_mouth_open()` (Sprint 5.8) was built with no real caller, explicitly deferred to "Sprint 5.11's Voice Personality/TTS integration" per that sprint's own Integration Considerations. This sprint delivers that caller: a lightweight audio-amplitude sampler runs against the same synthesized audio buffer `SoundDeviceAudioOutput.play()` (Sprint 2.4) already plays, driving a sequence of `set_mouth_open()` calls timed against playback — never re-synthesizing audio, never touching `CoquiTextToSpeech` itself.

## Objectives

- `presentation/voice_personality.py`: `VoicePersonalityModulator` — `shape_pacing(text: str, voice_warmth: float) -> str`.
- `presentation/lip_sync.py`: `LipSyncDriver` — `drive_from_audio(audio: bytes, sample_rate_hz: int, avatar_renderer: AvatarRenderer) -> None`, run in parallel with (not blocking) actual audio playback.
- Neither component touches `voice/text_to_speech.py` or `voice/speech_to_text.py`.

## Dependencies

5.5 (Presentation State Engine), 2.4 (Text-to-Speech Engine), 2.9/2.10 (Jarvis/Minie Persona — this sprint's real caller of `shape_pacing()` is wherever the reply text is finalized before `speak()`, i.e. the same call site `Persona.compose_reply()`'s own output flows through).

## Files to Create

- `presentation/voice_personality.py`
- `presentation/lip_sync.py`
- `tests/unit/presentation/test_voice_personality.py`
- `tests/unit/presentation/test_lip_sync.py`

## Files to Modify

- `config/schema.py` — `PresentationConfig` gains `pacing_pause_marker: str = "..."` (Coqui's own recognized short-pause token — a real, reviewable value confirmed against the installed `coqui-tts` version at implementation time, not assumed here), `pacing_low_warmth_pause_weight: float = 0.3`, `pacing_high_warmth_pause_weight: float = 0.7`, `lip_sync_sample_window_ms: float = 50.0`.

## Expected Classes

- **`VoicePersonalityModulator`**: constructor DI receives `PresentationConfig` only. No persona knowledge — a caller (Sprint 5.14's real wiring) passes `voice_warmth` explicitly, keeping this class a pure text transform, the same "pure decision function, no collaborator references" shape `GestureEngine` (5.9) already established.
- **`LipSyncDriver`**: constructor DI receives `PresentationConfig` only. Holds no reference to any renderer at construction — `drive_from_audio()` takes the target `AvatarRenderer` as a method parameter (this class exists to be reusable by whichever renderer wants lip-sync in the future, not hardcoded to Minie specifically, even though Minie is this sprint's only real user of it — Jarvis has no mouth to sync).

## Expected Interfaces

None new — both classes are plain, DI-constructed collaborators, no Protocol needed (single real implementation each, same "don't add an interface without a second implementation" discipline as Sprint 5.1's `EmotionDetectionEngine`).

## Expected Functions

- `VoicePersonalityModulator.shape_pacing(text: str, voice_warmth: float) -> str` — never raises (empty text returns empty text unchanged); splits `text` on existing sentence-ending punctuation, re-joins with `pacing_pause_marker` inserted at a frequency interpolated between `pacing_low_warmth_pause_weight` and `pacing_high_warmth_pause_weight` based on `voice_warmth`. Never alters a word of the actual text — insertion-only, so the Explainability/Human-First guarantee that a reply's *content* is unchanged by presentation (the brief's own "Presentation never changes intelligence") is structurally visible in this function's own signature (`text` goes in, a strict superset with markers inserted comes out — this sprint's own tests assert the de-marked output exactly equals the input).
- `LipSyncDriver.drive_from_audio(audio: bytes, sample_rate_hz: int, avatar_renderer: AvatarRenderer) -> None` — never raises (an empty/malformed audio buffer degrades to a single `set_mouth_open(0.0)` call and returns); runs on its own thread (mirrors `VoiceSessionManager`'s own existing background-thread pattern, Sprint 2.5) sampling RMS amplitude over `lip_sync_sample_window_ms` windows, mapping amplitude to a 0.0–1.0 mouth-open value, calling `avatar_renderer.set_mouth_open()` once per window, timed to approximate real playback duration (`len(audio) / sample_rate_hz` seconds total) — explicitly an approximation run **alongside** `TextToSpeech.speak()`'s own blocking playback call, not synchronized via any shared clock with it (see Potential Risks for the disclosed drift this implies). Always ends with a final `set_mouth_open(0.0)` call, even on early exit/exception, so the avatar's mouth never gets stuck open (a `try`/`finally`, the same defensive-cleanup shape `VoiceConfirmationService`'s own speak-then-listen wrapping already established at Sprint 4.12).

## Data Flow

```
Persona.compose_reply() output (already tone-adapted, Sprint 5.4)
        |
        v
VoicePersonalityModulator.shape_pacing(text, presentation_state.voice_warmth)
        |
        v
   paced_text: str  -->  TextToSpeech.speak(paced_text, voice_id)   (existing, unmodified)


(in parallel, only when the active persona's mounted renderer is an AvatarRenderer)
   synthesized audio buffer  -->  LipSyncDriver.drive_from_audio(audio, sample_rate_hz, avatar_renderer)
        |
        v
   avatar_renderer.set_mouth_open(...)  (repeated, timed to approximate playback)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — new `PresentationConfig` fields; confirm `pacing_pause_marker`'s exact value against the real installed `coqui-tts` version's own supported pause syntax before finalizing the default (a real, verifiable fact, not guessed).
2. `presentation/voice_personality.py` — `VoicePersonalityModulator`.
3. `presentation/lip_sync.py` — `LipSyncDriver`.
4. `tests/unit/presentation/test_voice_personality.py` — pacing-marker insertion frequency across the `voice_warmth` range; de-marked-output-equals-input invariant; empty-text handling.
5. `tests/unit/presentation/test_lip_sync.py` — amplitude-to-mouth-open mapping against synthetic audio fixtures (silence, constant tone, varying amplitude); guaranteed final `set_mouth_open(0.0)` even when the loop is interrupted mid-way (a fake `avatar_renderer` whose `set_mouth_open()` raises partway through, verifying the `finally` cleanup still fires); no real audio hardware/model involved (same "component before integration, fakes only" discipline as every other Part A sprint's own fast test suite).

## Architecture Notes

**Content/presentation boundary made structurally checkable**: `shape_pacing()`'s own contract (marker-insertion only, never text alteration) is directly, mechanically testable — strip `pacing_pause_marker` from the output and it must equal the input byte-for-byte. This is a stronger, more concrete guarantee than most "we promise not to change X" claims in this codebase get, chosen deliberately because voice pacing is exactly the kind of change that could silently drift into altering meaning if left unchecked (e.g. an overly aggressive implementation inserting a marker mid-word).

**Lip-sync timing is an approximation, not a hard real-time guarantee** — `LipSyncDriver` has no access to `SoundDeviceAudioOutput`'s own actual playback clock (that class's own Sprint 2.4 docstring gives it no observable timing API), so `drive_from_audio()` times itself against the audio buffer's own computed duration rather than genuine playback position. Disclosed explicitly here and in this class's own docstring rather than presented as more precise than it is.

## Integration Considerations

- **No live caller until Sprint 5.14** — the real call site (where `Persona.compose_reply()`'s output is currently passed straight to `TextToSpeech.speak()` inside `CommunicationPipeline`) is not modified this sprint.
- **`LipSyncDriver` only has a real effect when the active persona's renderer is an `AvatarRenderer`** (i.e. Minie) — Sprint 5.14's real wiring must gate the call accordingly; this sprint's own `drive_from_audio()` itself has no persona awareness (it just takes whatever `AvatarRenderer` it's given), consistent with keeping it renderer-agnostic per Expected Classes.
- Sprint 5.9's `GestureEngine` and this sprint's `LipSyncDriver` both ultimately call into `AvatarRenderer` but through entirely separate paths (`trigger_gesture()`/`set_eye_target()` vs. `set_mouth_open()`) — no coordination needed between them, since they drive independent Live2D parameters.

## Potential Risks

- **Lip-sync drift (Architecture Notes above) is a real, disclosed limitation** — acceptable for a first implementation; a genuinely synchronized approach would need `AudioOutput` (Sprint 2.4) to expose real playback-position callbacks, a change outside this sprint's own Files to Modify (that interface is explicitly not touched).
- **Coqui's own pause-marker syntax could differ from what this Sprint Book assumes** — flagged as something to confirm against the real installed version at implementation time (Implementation Tasks), not asserted as fact here.
- **A `LipSyncDriver` thread running alongside `TextToSpeech.speak()`'s own blocking call is a real concurrency surface** — mitigated by `LipSyncDriver` never touching shared mutable state beyond the `AvatarRenderer` it's given (which, per Sprint 5.8, already tolerates being called from any thread — `VTubeStudioAvatarRenderer`'s own WebSocket calls are the only I/O involved, no shared lock needed since nothing else in this codebase concurrently calls the same `AvatarRenderer` instance's mouth-open method).

## Acceptance Criteria

- `shape_pacing()`'s de-marked output always exactly equals its input text.
- `shape_pacing()`'s marker-insertion frequency measurably increases with `voice_warmth`.
- `drive_from_audio()` always ends with `set_mouth_open(0.0)`, including when interrupted by an exception partway through.
- `voice/text_to_speech.py`/`voice/speech_to_text.py` are unmodified by this sprint (mechanical check).
- `ruff check .` clean; full existing suite unaffected.

## Testing Checklist

- [ ] Unit: `shape_pacing()` de-marking invariant, frequency-vs-warmth relationship, empty-text handling.
- [ ] Unit: `drive_from_audio()` amplitude mapping against synthetic fixtures, and guaranteed-cleanup-on-exception behavior.
- [ ] Mechanical: no diff in `voice/text_to_speech.py`/`voice/speech_to_text.py`.
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `presentation/voice_personality.py` docstring states the de-marking invariant as this class's own core contract.
- [ ] `presentation/lip_sync.py` docstring discloses the timing-approximation limitation plainly.
- [ ] `docs/STATUS.md` — Level 5 Part A row updated.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Low–Medium.

## Estimated Development Time

1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.12 — Adaptive Workspace.

## Future Considerations

- A genuinely synchronized lip-sync approach (real playback-position feedback from `AudioOutput`) is real future work if the approximation proves visibly off during Sprint 5.16's manual verification — not built speculatively now.
- Richer prosody shaping (emphasis, not just pauses) is plausible future work once a real need is observed.
