"""Microphone Manager — the sole hardware-facing abstraction over the
system microphone.

Owns device open/close and the PASSIVE_LISTENING / ACTIVE_CAPTURE / MUTED
mode gate that enforces the Microphone Rule from 02_System_Architecture.md:
before wake word, only passive listening is permitted — no conversation
recording, no memory creation, no analysis. This module owns the mechanism
(how audio is captured, which mode is currently allowed); it deliberately
does not decide *when* to switch modes — that policy belongs to Quiet Mode
Controller (Sprint 2.6). See docs/sprint_book/sprint_2_1.md.

Mode changes never reopen or close the underlying audio stream (opening a
PortAudio stream is comparatively expensive); MUTED is a logical gate on
read_frame(), not a hardware pause, so switching modes stays cheap.
"""

import threading
from enum import Enum
from typing import Protocol

import sounddevice as sd

from config.schema import VoiceConfig
from core.logging_setup import get_logger
from voice.errors import MicrophoneError

logger = get_logger(__name__)

_FRAME_DURATION_MS = 30
"""Chunk size for each read_frame() call, in milliseconds. 30ms is a
standard framing duration for speech/wake-word processing. Expressed as a
duration rather than a fixed sample count so it scales automatically with
whatever mic_sample_rate_hz is configured."""


class MicrophoneMode(Enum):
    """Which kind of audio access is currently permitted."""

    PASSIVE_LISTENING = "passive_listening"
    ACTIVE_CAPTURE = "active_capture"
    MUTED = "muted"


class AudioBackend(Protocol):
    """Hardware-facing audio capture contract. Interface-first per
    03_Engineering_Standards.md, so the concrete audio library can be
    swapped without touching MicrophoneManager."""

    def open(self, device_index: int | None, sample_rate_hz: int) -> None: ...

    def read(self, num_frames: int) -> bytes: ...

    def close(self) -> None: ...


class SoundDeviceAudioBackend:
    """AudioBackend implementation backed by sounddevice's blocking
    RawInputStream (no callback — read() blocks until num_frames samples
    are available, which suits MicrophoneManager's synchronous read_frame()
    contract)."""

    def __init__(self) -> None:
        self._stream: sd.RawInputStream | None = None

    def open(self, device_index: int | None, sample_rate_hz: int) -> None:
        self._stream = sd.RawInputStream(
            samplerate=sample_rate_hz,
            device=device_index,
            channels=1,
            dtype="int16",
        )
        self._stream.start()

    def read(self, num_frames: int) -> bytes:
        if self._stream is None:
            raise MicrophoneError("Audio stream is not open.")
        data, overflowed = self._stream.read(num_frames)
        if overflowed:
            logger.warning("Microphone input buffer overflowed; some audio was dropped.")
        return bytes(data)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class MicrophoneManager:
    """Owns the microphone device and the passive/active/muted mode gate.

    Constructor DI per 03_Engineering_Standards.md: receives its VoiceConfig
    slice and an AudioBackend instance rather than constructing either
    itself.
    """

    def __init__(self, voice_config: VoiceConfig, backend: AudioBackend) -> None:
        self._voice_config = voice_config
        self._backend = backend
        self._mode = MicrophoneMode.MUTED
        self._is_open = False
        self._healthy = False
        self._lock = threading.Lock()
        self._frame_size_samples = max(
            1, (voice_config.mic_sample_rate_hz * _FRAME_DURATION_MS) // 1000
        )

    def start(self) -> None:
        """Open the configured device and enter PASSIVE_LISTENING mode."""
        self._backend.open(
            self._voice_config.mic_device_index, self._voice_config.mic_sample_rate_hz
        )
        self._is_open = True
        self._healthy = True
        self._mode = MicrophoneMode.PASSIVE_LISTENING
        logger.info("Microphone opened in PASSIVE_LISTENING mode.")

    def stop(self) -> None:
        """Close the device. Safe to call even if start() partially failed."""
        self._backend.close()
        self._is_open = False
        self._mode = MicrophoneMode.MUTED
        logger.info("Microphone closed.")

    def health_check(self) -> bool:
        """Report the last known health state. Does not perform new I/O —
        matches the established "Core owns how, a caller owns when" pattern
        (see core/manager.py); a failed read_frame() call is what actually
        flips this to False."""
        return self._is_open and self._healthy

    def read_frame(self) -> bytes:
        """Return the next audio frame. Raises MicrophoneError while MUTED,
        before start(), or if the backend read itself fails."""
        if not self._is_open:
            raise MicrophoneError("Cannot read a frame before start() or after stop().")
        if self._mode is MicrophoneMode.MUTED:
            raise MicrophoneError("Cannot read a frame while the microphone is MUTED.")
        with self._lock:
            try:
                return self._backend.read(self._frame_size_samples)
            except MicrophoneError:
                self._healthy = False
                raise
            except Exception as exc:
                self._healthy = False
                logger.exception("Microphone read failed.")
                raise MicrophoneError("Failed to read an audio frame.") from exc

    def set_mode(self, mode: MicrophoneMode) -> None:
        """Switch the mode gate. This is a mechanism-only operation — it
        does not itself decide whether the transition is appropriate for
        the conversation state; that policy belongs to Quiet Mode
        Controller (Sprint 2.6). Raises MicrophoneError if the device
        isn't currently open."""
        if not self._is_open:
            raise MicrophoneError("Cannot set microphone mode before start() or after stop().")
        with self._lock:
            self._mode = mode
        logger.info("Microphone mode changed to %s.", mode.value)

    def current_mode(self) -> MicrophoneMode:
        return self._mode
