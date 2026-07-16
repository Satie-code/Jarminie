# Sprint 2.2 — Wake Word Detector

## Sprint ID

2.2

## Sprint Name

Wake Word Detector

## Purpose

Implement always-on wake phrase detection per [02_System_Architecture.md](../02_System_Architecture.md)'s Voice Engine: *"Detect wake phrase. Remain dormant before activation."* This is the only processing JARMINEI performs on audio before the user has explicitly addressed it, and the sole trigger that Quiet Mode Controller (2.6) will use to leave its dormant state.

## Engineering Rationale

This sprint also resolves the open risk flagged twice already — in [sprint_1_5.md](sprint_1_5.md)'s Potential Risks and reiterated in [sprint_1_9.md](sprint_1_9.md)'s Recommendations for Level 2 — about whether the 3-method `ManagedModule` Protocol (`start`/`stop`/`health_check`) fits the Voice Engine's "dormant until wake word" lifecycle. It does, once framed correctly: **passive listening is the running state, not a separate one.** `start()` begins a continuous background listening thread (this *is* what "dormant/Quiet Mode" looks like at the wake-word layer); `stop()` ends it; `health_check()` reports thread liveness plus a staleness check (no frames processed in N seconds). Wake-phrase detection itself is not a lifecycle transition at all — it is a plain callback/event fired to whoever is listening (Quiet Mode Controller, from 2.6 onward). No change to the existing `ManagedModule` interface is needed or proposed.

## Objectives

- Continuous, low-overhead scanning of microphone frames (via 2.1's `MicrophoneManager`, in `PASSIVE_LISTENING` mode only) for any of the configured wake phrases.
- A callback-based detection API so downstream modules (Quiet Mode Controller) can react without `WakeWordDetector` knowing anything about what happens after detection — Interface First Design.
- No conversation content is ever retained beyond the rolling scan buffer (Microphone Rule: "No conversation recording. No memory creation. No analysis.").

## Dependencies

2.1 (Microphone Manager)

## Files to Create

- `voice/wake_word.py` — `WakeWordEngine` (Protocol), `OpenWakeWordEngine` (concrete impl), `WakeWordDetector`.
- `tests/unit/voice/test_wake_word.py`

## Files to Modify

- `voice/errors.py` — add `WakeWordError(VoiceError)`.
- `config/schema.py` — add `wake_word_sensitivity: float = 0.5` to `VoiceConfig` (openWakeWord's detection threshold, 0–1); add range validation `(0, 1]` to `AppConfig._validate_voice()`. `wake_phrases` (already present since Sprint 1.2) is reused as-is.

## Expected Classes

- `WakeWordEngine(Protocol)` — `process(self, frame: bytes) -> str | None` (returns the matched phrase, or `None`). Interface-first so `openwakeword` can be replaced later without touching `WakeWordDetector`.
- `OpenWakeWordEngine(WakeWordEngine)` — wraps the `openwakeword` package, configured with `VoiceConfig.wake_phrases` and `wake_word_sensitivity`.
- `WakeWordDetector(ManagedModule)` — constructor DI: `(mic: MicrophoneManager, engine: WakeWordEngine, on_detected: Callable[[str], None])`.

## Expected Interfaces

- `ManagedModule` (reused, unchanged — see Engineering Rationale above).

## Expected Functions

- `WakeWordDetector.start() -> None` — asserts `mic.current_mode() == PASSIVE_LISTENING`, launches `_listen_loop()` on a background thread.
- `WakeWordDetector.stop() -> None` — signals the thread to exit and joins it.
- `WakeWordDetector.health_check() -> bool` — thread alive AND last-frame-processed timestamp within a small tolerance window.
- `WakeWordDetector._listen_loop() -> None` — reads frames from `mic.read_frame()`, feeds each to `engine.process()`, invokes `on_detected(phrase)` on a match.

## Data Flow

```
MicrophoneManager.read_frame()  (PASSIVE_LISTENING only)
      ↓
OpenWakeWordEngine.process(frame)
      ↓ (match)
WakeWordDetector.on_detected(phrase) callback
      ↓
Quiet Mode Controller (2.6) — not built yet; callback wired there
```

## Acceptance Criteria

- With a fake `WakeWordEngine` fixture forced to match on a specific frame, `on_detected` fires exactly once with the correct phrase string.
- No frame content or transcript is stored anywhere beyond the scan itself.
- `stop()` cleanly joins the background thread with no lingering thread on process exit (verified, not assumed — a real thread-join test, not just a mock call assertion).
- A `MicrophoneError` raised by `mic.read_frame()` mid-loop is caught, logged, and reflected in `health_check() -> False`, not raised out of the thread.

## Testing Checklist

- [ ] Unit: `_listen_loop()` invokes `on_detected` only on a genuine match (fake engine returning `None` for non-matching frames).
- [ ] Unit: `start()` raises/logs clearly if `mic.current_mode()` is not `PASSIVE_LISTENING` at call time.
- [ ] Unit: `stop()` joins the background thread within a bounded timeout (real `threading.Thread`, not mocked).
- [ ] Unit: a `MicrophoneError` mid-loop is caught and surfaces via `health_check()`.
- [ ] Unit: `AppConfig._validate_voice()` rejects `wake_word_sensitivity` outside `(0, 1]`.

## Documentation Checklist

- [ ] `voice/wake_word.py` docstring: explains why `start()`/`stop()` map onto continuous listening rather than detection state, cross-referencing this sprint's Engineering Rationale.
- [ ] `docs/STATUS.md` — no change yet (Phase 2.1 remains in progress until Sprint 2.6 closes Quiet Mode).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium — thread lifecycle correctness matters more than the detection logic itself (delegated to `openwakeword`).

## Estimated Development Time

1–1.5 days.

## Risks

- **False positive / false negative tuning** of `wake_word_sensitivity` is inherently environment-dependent (microphone quality, ambient noise) — the default (0.5) is a starting point, not a validated value; flag for real-device tuning during Sprint 2.12 integration, not this sprint.
- **Background thread exception safety**: any uncaught exception inside `_listen_loop()` must not crash the process — the loop itself needs a top-level try/except per iteration, logged, not just around the whole loop (an exception mid-loop should not silently end passive listening without at least a logged, health-check-visible failure).

## Next Sprint

2.3 — Speech-to-Text Engine (Whisper).
