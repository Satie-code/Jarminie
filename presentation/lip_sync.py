"""LipSyncDriver (Sprint 5.11 — Level 5 Part A).

Closes a gap Sprint 5.8 named explicitly: `VTubeStudioAvatarRenderer.
set_mouth_open()` was built with no real caller, deferred to "Sprint
5.11's Voice Personality/TTS integration" per that sprint's own
Integration Considerations. `drive_from_audio()` is that caller: a
lightweight RMS-amplitude sampler run against the same synthesized
audio buffer `SoundDeviceAudioOutput.play()` (Sprint 2.4) already plays
— never re-synthesizing audio, never touching `CoquiTextToSpeech`
itself, and never touching `voice/text_to_speech.py` at all.

**Runs on its own background thread**, mirroring `VoiceSessionManager.
begin_session()`'s own established pattern (Sprint 2.5, `voice/
session_manager.py`) exactly: `drive_from_audio()` spawns a daemon
thread and returns immediately, non-blocking, so it can run *alongside*
`TextToSpeech.speak()`'s own blocking playback call rather than before
or after it.

**Lip-sync timing is an approximation, not a hard real-time guarantee**
— this class has no access to `SoundDeviceAudioOutput`'s own actual
playback clock (that class's own Sprint 2.4 docstring gives it no
observable timing API), so `drive_from_audio()` times itself against
the audio buffer's own real, decoded sample count divided by
sample_rate_hz, sleeping approximately one sampling window at a time,
rather than genuine playback position. Disclosed here plainly rather
than presented as more precise than it is — a real, later fix (Future
Considerations) would need `AudioOutput` itself to expose playback-
position callbacks, out of this sprint's own scope.

**A real correction made to this sprint's own spec text**: the Sprint
Book's own Expected Functions describe total playback duration as
`len(audio) / sample_rate_hz` — but `audio` is float32 PCM bytes (4
bytes per sample, matching `CoquiTextToSpeech.speak()`'s own
`np.asarray(samples, dtype=np.float32).tobytes()`), so a literal
`len(audio)` (byte count) divided by sample_rate_hz would compute a
duration 4x too short. This implementation instead decodes the buffer
via `np.frombuffer(audio, dtype=np.float32)` (the same decoding
`SoundDeviceAudioOutput.play()` itself already uses) and derives timing
from the real sample count — correct, not a silent deviation from the
spec's own intent, only from its literal (and inaccurate) formula.

Always ends with a final `set_mouth_open(0.0)` call, even on an
exception partway through — a `try`/`finally`, the same defensive-
cleanup shape `VoiceConfirmationService`'s own speak-then-listen
wrapping already established at Sprint 4.12.
"""

import threading
import time

import numpy as np

from config.schema import PresentationConfig
from core.logging_setup import get_logger
from presentation.avatar_renderer import AvatarRenderer
from presentation.presentation_state import clamp

logger = get_logger(__name__)


class LipSyncDriver:
    """Constructor DI per 03_Engineering_Standards.md: receives
    PresentationConfig only. Holds no reference to any renderer at
    construction — drive_from_audio() takes the target AvatarRenderer as
    a method parameter, so this class stays reusable by whichever
    renderer wants lip-sync in the future, not hardcoded to Minie
    specifically (Jarvis has no mouth to sync; this class has no
    persona awareness of its own either way)."""

    def __init__(self, presentation_config: PresentationConfig) -> None:
        self._config = presentation_config
        self._thread: threading.Thread | None = None

    def drive_from_audio(
        self, audio: bytes, sample_rate_hz: int, avatar_renderer: AvatarRenderer
    ) -> None:
        """Spawns a background thread (see this module's own docstring)
        and returns immediately — never raises, including if starting
        the thread itself somehow fails."""
        try:
            thread = threading.Thread(
                target=self._run,
                args=(audio, sample_rate_hz, avatar_renderer),
                name="lip-sync-driver",
                daemon=True,
            )
            thread.start()
            self._thread = thread
        except Exception:
            logger.exception("LipSyncDriver.drive_from_audio() failed to start its own thread.")

    def _run(self, audio: bytes, sample_rate_hz: int, avatar_renderer: AvatarRenderer) -> None:
        """The thread's own target. A single set_mouth_open(0.0) call in
        the finally block naturally covers both the "empty/malformed
        audio" case (the try body's loop never runs) and the normal
        "guaranteed final call" case (after N real amplitude-mapped
        calls) — one mechanism, not two separate code paths."""
        try:
            window_seconds = self._config.lip_sync_sample_window_ms / 1000.0
            for value in self._compute_mouth_open_values(audio, sample_rate_hz):
                avatar_renderer.set_mouth_open(value)
                time.sleep(window_seconds)
        except Exception:
            logger.exception("LipSyncDriver playback loop failed; ending lip-sync early.")
        finally:
            try:
                avatar_renderer.set_mouth_open(0.0)
            except Exception:
                logger.exception("Final set_mouth_open(0.0) cleanup call failed.")

    def _compute_mouth_open_values(self, audio: bytes, sample_rate_hz: int) -> list[float]:
        """RMS amplitude per lip_sync_sample_window_ms window, mapped to
        0.0-1.0 (float32 PCM samples are themselves bounded to roughly
        [-1.0, 1.0], so RMS — always <= the maximum absolute sample
        value — is already naturally in range; clamp() is defensive,
        not a rescale). Returns [] for empty/malformed audio, the signal
        _run()'s own single finally-block call degrades to."""
        if not audio or sample_rate_hz <= 0:
            return []
        try:
            samples = np.frombuffer(audio, dtype=np.float32)
        except ValueError:
            logger.warning("LipSyncDriver received a malformed audio buffer; treating as silent.")
            return []
        if samples.size == 0:
            return []

        window_size = max(1, int(sample_rate_hz * self._config.lip_sync_sample_window_ms / 1000.0))
        values: list[float] = []
        for start in range(0, samples.size, window_size):
            window = samples[start : start + window_size]
            rms = float(np.sqrt(np.mean(np.square(window))))
            values.append(clamp(rms, 0.0, 1.0))
        return values
