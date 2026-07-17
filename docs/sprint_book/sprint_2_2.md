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

---

## Sprint Completion Report

### Summary

Implemented `WakeWordDetector` (continuous background listening thread + callback-based detection), the `WakeWordEngine` Protocol, and `OpenWakeWordEngine`. Verified the listen-loop/thread lifecycle against a `FakeWakeWordEngine` (automated suite), and separately verified `OpenWakeWordEngine` against a real, downloaded openWakeWord pretrained model — a real end-to-end run, not just a fake. That real run surfaced and resolved a genuine platform issue (see Engineering Decisions) and also surfaced an important **product-level limitation worth your attention** (see Remaining Risks, first bullet) — the configured default wake phrase, `"hey jarminei"`, has no pretrained model and cannot actually be detected yet.

### Files Created

- `voice/wake_word.py` — `WakeWordEngine`, `OpenWakeWordEngine`, `WakeWordDetector`.
- `tests/unit/voice/test_wake_word.py` (8 tests).

### Files Modified

- `voice/errors.py` — added `WakeWordError`.
- `config/schema.py` — `VoiceConfig.wake_word_sensitivity: float = 0.5`; range validation `(0, 1]` added to `AppConfig._validate_voice()`.
- `config/defaults.yaml` — added `wake_word_sensitivity: 0.5`.
- `tests/unit/voice/conftest.py` — `FakeWakeWordEngine` + `fake_wake_word_engine_factory` fixture.
- `tests/unit/config/test_schema.py` — 3 new tests for the sensitivity bound.
- `.venv` — installed `openwakeword` (already listed in `requirements.txt` since Sprint 1.1's bootstrap; this is its actual first install, per the same per-phase install practice used for `sounddevice` in Sprint 2.1).

### Engineering Decisions

- **Guard-check ordering resolved as planned**: `MicrophoneManager.read_frame()`'s own "not open" check (Sprint 2.1) already takes precedence correctly; this sprint's `WakeWordDetector.start()` separately asserts the mic is in `PASSIVE_LISTENING` before launching the thread at all, so the two modules' checks don't overlap or conflict.
- **Two different failure-handling paths inside `_listen_loop()`, by design**: a `MicrophoneError` (device-level) ends the listening thread — continuing would just busy-loop against an already-broken microphone; any other exception (an engine/processing hiccup) is logged and the loop continues, per this sprint's own Risk that "a single bad frame shouldn't end passive listening." `health_check()`'s staleness window means a *repeatedly*-failing engine still eventually reports unhealthy even though the thread stays alive.
- **`OpenWakeWordEngine` explicitly requests `inference_framework="onnx"`** — a real finding, not something anticipated in the sprint plan: openwakeword defaults to a `tflite` backend, and `tflite-runtime` has no readily available Windows wheel (this project's only target platform). `onnxruntime` is already a transitive dependency of `openwakeword` itself, so pinning to it introduces no new dependency. Discovered by actually attempting to load a real model, not assumed from documentation.
- **Real model files (melspectrogram/embedding/wakeword `.onnx`) are downloaded on demand via `openwakeword.utils.download_models()`**, not automatically inside `OpenWakeWordEngine.__init__()` — baking a network download into a constructor would be a surprising hidden side effect. This is an operational/deployment step (run once, or ship the files), not something this sprint's code does implicitly. Not yet wired into `main.py` since no composition root touches Level 2 modules until Sprint 2.12.

### Tests Added

8 in `tests/unit/voice/test_wake_word.py` (detection fires exactly once on a genuine match; no false positive when the engine never matches; `start()` rejects a non-`PASSIVE_LISTENING` mic; `stop()` really joins the thread — checked via a real `threading.Thread` reference, not a mock; health check false before start / true while running; a `MicrophoneError` mid-loop ends the thread and marks unhealthy; an engine-side failure does *not* end the thread), 3 in `tests/unit/config/test_schema.py` (sensitivity bound). **124/124 total passing** (113 from Sprint 2.1 + 11 new), `ruff check .` clean, no flakiness across 3 repeated runs of the threading-heavy test file. Plus a real (non-committed) verification: downloaded openWakeWord's actual `hey_jarvis` pretrained model and ran `OpenWakeWordEngine` against real silent audio end-to-end, confirming no false positive and, along the way, catching the `tflite`-vs-`onnx` backend issue above.

### Documentation Updated

`voice/wake_word.py` module and class docstrings (state the `start()`/`stop()`-as-continuous-listening framing, the two-failure-path distinction, and the `onnx` backend choice with its rationale). This Sprint Completion Report. `docs/STATUS.md` intentionally left unchanged, per this sprint's own Documentation Checklist (Phase 2.1 stays "in progress" until Sprint 2.6 closes Quiet Mode).

### Acceptance Criteria Checklist

- ✔ With a fake `WakeWordEngine` forced to match on a specific frame, `on_detected` fires exactly once with the correct phrase.
- ✔ No frame content or transcript is stored anywhere beyond the scan itself (verified by inspection — `_listen_loop()` holds no buffer beyond the current frame).
- ✔ `stop()` cleanly joins the background thread — verified against a real `threading.Thread` reference, confirmed not alive afterward.
- ✔ A `MicrophoneError` mid-loop is caught, logged, and reflected in `health_check() -> False`, never raised out of the thread.

### Remaining Risks

- **Product-level, not just engineering**: the shipped default `voice.wake_phrases: ["hey jarminei"]` (set back in Sprint 1.2) has **no corresponding pretrained openWakeWord model** — `OpenWakeWordEngine` will raise `WakeWordError` at construction time if used as-configured today. Getting a real "hey jarminei" detector requires either (a) training a custom wake-word model offline (a data-collection/ML-training task, not something any coding sprint can do), or (b) changing the configured phrase to one of openWakeWord's shipped pretrained names (e.g. `hey_jarvis`) as a stand-in until a custom model exists. This wasn't discoverable until this sprint actually tried to load a real model — flagging it now rather than letting it surface silently later, and leaving the choice to you rather than changing `config/defaults.yaml`'s product-facing wake phrase unilaterally.
- `wake_word_sensitivity`'s default (0.5) remains an unvalidated starting point — real false-positive/negative tuning needs a real microphone in a real environment, deferred to Sprint 2.12 integration as this sprint's own spec already anticipated.
- No automatic reconnect/restart if the microphone fails mid-listen — `health_check()` correctly reports the failure; recovery orchestration is Sprint 2.13's job.

### Technical Debt

None introduced. (The `tflite`/`onnx` backend choice is a resolved engineering decision, not a deferred shortcut; the missing "hey jarminei" model is a pre-existing product/tech-stack reality dating to Sprint 1.2's default, surfaced here rather than caused here.)

### Recommendations for Sprint 2.3

- `WhisperSpeechToText` will need its own real-model verification pass, same pattern as this sprint's — budget time for a first-real-model-load surprise the way this sprint hit the tflite/onnx one.
- Consider resolving the "hey jarminei" model gap (via a decision from you) before Sprint 2.12's integration sprint, since that's the first point a real end-to-end wake-to-speech demo becomes possible — no need to resolve it earlier than that.

### Wake Phrase Decision (2026-07-17)

User confirmed proceeding with the recommended stand-in: `VoiceConfig.wake_phrases` and `config/defaults.yaml` now default to `["hey_jarvis"]` (openWakeWord's shipped pretrained model) instead of `"hey jarminei"`. Verified against the real, downloaded `hey_jarvis` model — loads and runs correctly (no false positive on silence). Tracked as [backlog/technical_debt.md](../backlog/technical_debt.md) item 5: training and shipping a custom "hey jarminei" model is offline ML work outside any coding sprint's scope, targeted before public release polish, not blocking Sprint 2.12.

### Post-Sprint Fix (2026-07-17, during Sprint 2.12)

**Real bug found by Sprint 2.12's Communication Pipeline Integration testing, not by any test in this file**: `_listen_loop()` called `mic.read_frame()` unconditionally on every iteration, with no check of the microphone's current mode. None of this sprint's own tests caught it because none of them ran the listen loop concurrently with an active voice session — every test here either kept the mic in `PASSIVE_LISTENING` throughout, or (for the `MicrophoneError`/engine-failure tests) never switched modes at all. Once Sprint 2.5's `VoiceSessionManager.begin_session()` puts the mic in `ACTIVE_CAPTURE`, this thread kept right on competing with `VoiceSessionManager`'s own utterance-capture thread for the same underlying frame stream — silently stealing frames intended for real conversation audio, with no coordination between the two. This is exactly the "mocked/isolated tests systematically miss integration bugs that only a real end-to-end run catches" lesson from Sprint 1.8, recurring here at the thread level instead of the config-reload level.

Fixed in `_listen_loop()`: it now checks `mic.current_mode()` each iteration and pauses (re-checking every `_MODE_POLL_SECONDS` = 0.1s) while the mode isn't `PASSIVE_LISTENING`, resuming automatically once a session ends and the mic returns to passive listening. `_last_processed_at` is still updated during the pause, so `health_check()` correctly treats "deliberately idle because a session is active" as healthy, not as the stuck-and-failing state that field's staleness check exists to catch. 3 new regression tests added to `tests/unit/voice/test_wake_word.py` (pause while `ACTIVE_CAPTURE`, resume after returning to `PASSIVE_LISTENING`, `health_check()` stays `True` throughout the pause) — 11/11 in this file passing, no flakiness across 4 repeated runs. Tracked as [backlog/technical_debt.md](../backlog/technical_debt.md) item 10. Full detail on how this was discovered (via a real, non-mocked integration test wiring `WakeWordDetector` and `VoiceSessionManager` against the same fake microphone) is in `sprint_2_12.md`'s own Sprint Completion Report.
