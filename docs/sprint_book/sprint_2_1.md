# Sprint 2.1 — Microphone Manager

## Sprint ID

2.1

## Sprint Name

Microphone Manager

## Purpose

Provide the single hardware-facing abstraction over the laptop's microphone that every later Level 2 sprint depends on. Owns device selection, stream lifecycle, and — critically — the arbitration between **passive** (wake-word-only) and **active** (full utterance capture) listening modes that the Microphone Rule in [02_System_Architecture.md](../02_System_Architecture.md) requires: *"Before wake word: only detect wake phrase. No conversation recording. No memory creation. No analysis."*

## Engineering Rationale

The Master Sprint Book originally sequenced Wake Word Detector before Microphone Manager. Re-examining that ordering while writing this Sprint Book surfaced a Dependency Injection violation: a `WakeWordDetector` built first would have to open its own throwaway audio stream, which would then be thrown away and replaced once a real `MicrophoneManager` arrived a sprint later — the same kind of avoidable rework Level 1 never needed (Configuration → Logging → Health → Core was purely additive, each sprint building on a stable predecessor, never refactoring one). Flipping the order so the hardware abstraction exists first means `WakeWordDetector` (2.2) receives a `MicrophoneManager` instance via DI from day one, exactly as [03_Engineering_Standards.md](../03_Engineering_Standards.md)'s Dependency Injection rule requires ("avoid creating X inside Y; instead Y receives an X instance"). This is the one deliberate deviation from the roadmap-granularity ordering recorded in [INDEX.md](INDEX.md) prior to this Sprint Book — the component identities and dependency graph are otherwise unchanged, only 2.1 and 2.2 swap places.

Putting the passive/active arbitration here (mechanism) rather than in Quiet Mode Controller (2.6, policy) keeps Single Responsibility intact: this module owns *how* audio is captured and *which mode is currently allowed*; Quiet Mode Controller will later own *when* to switch modes.

## Objectives

- A `MicrophoneManager` that opens/closes the system default (or configured) input device exactly once and exposes raw audio frames to callers.
- A `MicrophoneMode` state (`PASSIVE_LISTENING` / `ACTIVE_CAPTURE` / `MUTED`) that gates what a caller can do — passive mode yields only the small rolling buffer wake-word scanning needs; active mode yields the full utterance stream STT needs. Only one mode is ever active.
- Clear, typed failure reporting when no input device exists, permission is denied, or the device disappears mid-stream (laptop-realistic failure modes Level 1 never had to handle).
- Establish `voice/errors.py` as the shared error hierarchy for every Level 2 module, mirroring the existing `config/errors.py` pattern.

## Dependencies

1.5 (Core Manager — `ManagedModule`, `CoreManager`), 1.2 (Configuration Manager — `VoiceConfig`)

## Files to Create

- `voice/errors.py` — `VoiceError(Exception)` (base), `MicrophoneError(VoiceError)`.
- `voice/microphone.py` — `MicrophoneMode` (Enum), `AudioBackend` (Protocol), `SoundDeviceAudioBackend` (concrete impl), `MicrophoneManager`.
- `tests/unit/voice/test_microphone.py`
- `tests/unit/voice/conftest.py` — a fake `AudioBackend` fixture (produces silent/synthetic frames, never touches real hardware) reused by every later voice-layer test file, per the "expose shared test helpers as fixtures, not importable functions" gotcha already documented from Sprint 1.7.

## Files to Modify

- `requirements.txt` — add `sounddevice>=0.4` under a new "Phase 2.1 — Voice Pipeline (audio I/O)" section. Neither `openai-whisper`, `openwakeword`, nor `coqui-tts` (already listed) provides a maintained, cross-platform microphone *capture* API on their own; `sounddevice` also covers Sprint 2.4's playback need, so one library serves both directions of audio I/O rather than pulling in a second one later.
- `config/schema.py` — add to `VoiceConfig`: `mic_device_index: int | None = None` (None = system default), `mic_sample_rate_hz: int = 16000` (Whisper's native rate, avoids a resampling step in Sprint 2.3). Add corresponding bounds validation to `AppConfig._validate_voice()`.

## Expected Classes

- `AudioBackend(Protocol)` — `open(device_index: int | None, sample_rate_hz: int) -> None`, `read(num_frames: int) -> bytes`, `close() -> None`. Interface-first per [03_Engineering_Standards.md](../03_Engineering_Standards.md), so `sounddevice` can be swapped later without touching `MicrophoneManager`.
- `SoundDeviceAudioBackend(AudioBackend)` — thin wrapper around `sounddevice.RawInputStream`.
- `MicrophoneManager(ManagedModule)` — constructor DI: `(voice_config: VoiceConfig, backend: AudioBackend)`.

## Expected Interfaces

- `ManagedModule` (reused, unchanged) — `start()` opens the device in `PASSIVE_LISTENING` mode; `stop()` closes it; `health_check()` reports whether the underlying stream is still alive and readable.

## Expected Functions

- `MicrophoneManager.read_frame() -> bytes` — returns the next frame from whichever backend stream is currently open; behavior depends on `current_mode()`.
- `MicrophoneManager.set_mode(mode: MicrophoneMode) -> None` — the single choke point that enforces "only one mode at a time"; raises `MicrophoneError` if called with an unsupported transition (e.g. `MUTED` while a caller still expects frames).
- `MicrophoneManager.current_mode() -> MicrophoneMode`
- `MicrophoneManager.health_check() -> bool` — catches a disappeared/disconnected device and reports `False` rather than letting a read raise out of a background thread.

## Data Flow

```
Physical microphone
      ↓
SoundDeviceAudioBackend.read()
      ↓
MicrophoneManager (mode gate: PASSIVE_LISTENING | ACTIVE_CAPTURE | MUTED)
      ↓                                   ↓
WakeWordDetector (2.2)          VoiceSessionManager (2.5) / SpeechToText (2.3)
  (passive frames only)            (active frames only, after mode switch)
```

## Acceptance Criteria

- `MicrophoneManager.start()` opens the configured device in `PASSIVE_LISTENING` mode; `stop()` releases it cleanly.
- Exactly one mode is active at any time; attempting an invalid concurrent mode raises `MicrophoneError` rather than silently allowing both.
- A backend failure (device missing, permission denied, disconnected mid-stream) is caught, logged, and reported via `health_check() -> False` — never raised uncaught out of a background thread (Fail Gracefully Rule).
- No frame is ever readable in `MUTED` mode.

## Testing Checklist

- [ ] Unit: `start()`/`stop()` lifecycle against the fake `AudioBackend` fixture.
- [ ] Unit: `set_mode()` transition table — every valid and invalid transition.
- [ ] Unit: `read_frame()` returns backend data only in a mode that permits it; raises/returns clearly otherwise.
- [ ] Unit: a backend that raises on `read()` is caught by `health_check()`, not propagated.
- [ ] Unit: `AppConfig._validate_voice()` rejects an out-of-range `mic_sample_rate_hz` (e.g. 0 or negative).

## Documentation Checklist

- [ ] `voice/microphone.py` module docstring: mode state diagram, Microphone Rule reference.
- [ ] `voice/errors.py` docstring: error hierarchy purpose, reused by every later Level 2 sprint.
- [ ] `docs/STATUS.md` — Phase 2.1 row updated from `Planned` to `Designing` once this sprint starts.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium — first real-hardware-facing module in the project; the fake-backend testing seam is the main design challenge, not the logic itself.

## Estimated Development Time

1–1.5 days.

## Risks

- **No physical microphone in CI/dev sandbox environments.** Mitigated by the `AudioBackend` Protocol seam — all automated tests run against `SoundDeviceAudioBackend`'s fake substitute; a manual real-hardware check is a Testing Checklist item, not an automated one, matching the "mocked tests miss integration bugs" lesson from Sprint 1.8 by explicitly not over-trusting the fake alone at pipeline-integration time (Sprint 2.12).
- **`sounddevice` platform behavior on Windows** (the project's only target platform, per [01_Project_Vision.md](../01_Project_Vision.md)) is not yet verified against a real device index list — flag for confirmation during implementation, not assumed here.

## Next Sprint

2.2 — Wake Word Detector.

---

## Sprint Completion Report

### Summary

Implemented `MicrophoneManager`: device open/close lifecycle, the `PASSIVE_LISTENING`/`ACTIVE_CAPTURE`/`MUTED` mode gate, and a `SoundDeviceAudioBackend` behind an `AudioBackend` Protocol seam. Established `voice/errors.py` as the shared error hierarchy for Level 2. Verified against both a fake backend (automated suite) and, opportunistically, the real microphone available on this development machine (a real-hardware smoke script, not part of the committed suite) — confirming `sounddevice`/PortAudio work correctly on Windows, which de-risks the one item this sprint's own spec flagged as unverified.

### Files Created

- `voice/errors.py` — `VoiceError`, `MicrophoneError`.
- `voice/microphone.py` — `MicrophoneMode`, `AudioBackend`, `SoundDeviceAudioBackend`, `MicrophoneManager`.
- `tests/unit/voice/conftest.py` — `FakeAudioBackend`, `fake_audio_backend` fixture, `voice_config_factory`.
- `tests/unit/voice/test_microphone.py` (16 tests).

### Files Modified

- `config/schema.py` — `VoiceConfig` gained `mic_device_index: int | None = None`, `mic_sample_rate_hz: int = 16000`; `AppConfig._validate_voice()` rejects a non-positive sample rate.
- `config/defaults.yaml` — added the two new `voice:` fields at their default values, matching the existing convention of every schema field appearing in the shipped defaults file.
- `requirements.txt` — added `sounddevice>=0.4`.
- `tests/unit/config/test_schema.py` — added `test_non_positive_mic_sample_rate_hz_raises`.
- `docs/STATUS.md` — Phase 2.1 row → `Developing`.
- `.venv` — installed `sounddevice` (+ its `cffi`/`pycparser` transitive deps), per the established per-phase install practice from `backlog/technical_debt.md` item 1.

### Engineering Decisions

- **Check order in `read_frame()`**: "not open" is checked before "MUTED," not the reverse — `_mode` defaults to `MUTED` before `start()` is ever called, so checking MUTED first would have misreported a genuinely never-started manager as merely muted. Caught by a failing test (`test_read_frame_raises_before_start`) during implementation, not assumed correct in the plan.
- **`set_mode()` is mechanism-only, as flagged in the approved plan**: any of the three modes is settable once the device is open; this sprint does not police *which* transitions make sense for the conversation state (that's Quiet Mode Controller's job, Sprint 2.6).
- **Mode changes never reopen/close the underlying stream** — `MUTED` is a logical gate on `read_frame()`, not a hardware pause, avoiding repeated expensive PortAudio stream open/close cycles (Resource Protection).
- **`health_check()` reports last-known state rather than probing** — consistent with the existing "Core owns how, a caller owns when" pattern from `core/manager.py`; a failed `read_frame()` is what actually flips it to unhealthy, mirroring how `ResourceMonitor`/`CoreManager.check_resources()` is caller-triggered, not internally polled.
- **Frame size derived from `mic_sample_rate_hz`** (30ms chunks) rather than a second, independent constant — verified at two different sample rates (16kHz → 480 samples, 8kHz → 240 samples) to confirm it actually scales rather than just working at the default.

### Tests Added

16 in `tests/unit/voice/test_microphone.py` (start/stop lifecycle, health check across start/stop/failure, frame-size derivation at two sample rates, MUTED gating, mode-transition validity before/after open, backend-failure → `MicrophoneError` + unhealthy), 1 in `tests/unit/config/test_schema.py` (sample-rate validation). 113/113 total passing, `ruff check .` clean. Plus a real-hardware smoke script (scratchpad, not committed, matching the Sprint 1.6 precedent for this kind of verification) exercising the actual Realtek microphone on this machine end-to-end — passive frame, active frame, MUTED rejection, and post-stop health all confirmed against real audio hardware, not just the fake.

### Documentation Updated

`voice/microphone.py` and `voice/errors.py` module docstrings (mode gate, Microphone Rule reference, error hierarchy purpose). `docs/STATUS.md`. This Sprint Completion Report.

### Acceptance Criteria Checklist

- ✔ `start()` opens the configured device in `PASSIVE_LISTENING`; `stop()` releases it cleanly.
- ✔ Exactly one mode active at a time; the API only ever exposes `current_mode()` as a single value — no dual-mode state is representable.
- ✔ Backend failures are caught, logged, and surface via `health_check() -> False`, never raised out of a caller's control flow uncaught.
- ✔ No frame is ever readable in `MUTED` mode (raises `MicrophoneError`, confirmed the backend's `read()` is never even called in that case).

### Remaining Risks

- `sounddevice` behavior was verified only on this one development machine's microphone/driver combination (Realtek, MME/WASAPI backends available) — different hardware on the eventual target laptop could still surface a different real-world issue; the risk is reduced, not eliminated.
- `MicrophoneManager` itself has no automatic reconnect/retry if a device disappears mid-stream — it correctly reports unhealthy via `health_check()`, but recovery (via `CoreManager.restart_module()`) is Sprint 2.13's (Error Handling & Recovery Hardening) responsibility, not this sprint's, per the Sprint Book's own scoping.
- `config/loader.py`'s env-var coercion (`_coerce()`) does not special-case `Optional`/Union-typed fields — an env override for `mic_device_index` (typed `int | None`) would currently fall through to being left as a raw string rather than coerced to `int` or `None`. Not exercised by any acceptance criterion in this sprint (no test needs it), and no existing Level 1 field hit this case either; flagged here rather than silently patched, since fixing `_coerce()` was outside this sprint's approved Files to Modify.

### Technical Debt

None introduced (the `_coerce()` Optional-typing gap above is a pre-existing limitation surfaced by this sprint's new field, not a shortcut taken by it — recorded as a Remaining Risk rather than formal technical debt since nothing currently depends on it working).

### Recommendations for Sprint 2.2

- `WakeWordDetector` should receive its `MicrophoneManager` via constructor DI and call `read_frame()` in `PASSIVE_LISTENING` mode from its own background thread — no changes to `MicrophoneManager`'s public API are anticipated.
- The real-hardware smoke test pattern established here (open → read in each mode → confirm MUTED rejection → stop) is cheap to extend once Sprint 2.2 exists — worth chaining a wake-word-in-the-loop version of it rather than writing one from scratch.
