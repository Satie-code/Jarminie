"""Wake Word Detector — continuous, low-overhead scanning of microphone
frames for the configured wake phrase(s).

start()/stop() map onto continuous passive listening, not a "detection"
state: passive listening *is* the running state (this is what Quiet Mode
looks like at this layer, per 02_System_Architecture.md's Quiet Mode
description — "remains dormant until: wake phrase"). Wake-phrase detection
is a plain callback fired to whoever is listening (Quiet Mode Controller,
from Sprint 2.6 onward), not a lifecycle transition — see
docs/sprint_book/sprint_2_2.md's Engineering Rationale, which also resolves
the ManagedModule-fit risk flagged since Sprint 1.5.
"""

import threading
import time
from collections.abc import Callable
from typing import Protocol

from config.schema import VoiceConfig
from core.logging_setup import get_logger
from voice.errors import MicrophoneError, WakeWordError
from voice.microphone import MicrophoneManager, MicrophoneMode

logger = get_logger(__name__)

_HEALTH_STALENESS_SECONDS = 5.0
"""health_check() reports unhealthy if no frame has been *successfully*
processed within this many seconds — catches a loop that's alive but
stuck failing repeatedly, not just a dead thread."""

_THREAD_JOIN_TIMEOUT_SECONDS = 5.0


class WakeWordEngine(Protocol):
    """Wake-phrase detection contract. Interface-first per
    03_Engineering_Standards.md, so openwakeword can be replaced later
    without touching WakeWordDetector."""

    def process(self, frame: bytes) -> str | None: ...


class OpenWakeWordEngine:
    """WakeWordEngine implementation wrapping the openwakeword package.

    Loads its model(s) at construction time (this class is not itself a
    ManagedModule — only WakeWordDetector is, per this sprint's design) —
    a failure here surfaces immediately as a WakeWordError rather than
    silently deferring to first use.

    Explicitly requests the "onnx" inference backend rather than
    openwakeword's own default ("tflite") — confirmed during
    implementation that tflite-runtime has no readily available Windows
    wheel (the project's only target platform, per 01_Project_Vision.md),
    while onnxruntime is already a transitive dependency of openwakeword
    itself, so no new dependency is introduced by this choice.
    """

    def __init__(self, voice_config: VoiceConfig) -> None:
        import numpy as np
        from openwakeword.model import Model

        self._np = np
        self._sensitivity = voice_config.wake_word_sensitivity
        try:
            self._model = Model(
                wakeword_models=list(voice_config.wake_phrases),
                inference_framework="onnx",
            )
        except Exception as exc:
            raise WakeWordError(
                f"Failed to load openWakeWord model(s) for phrases "
                f"{voice_config.wake_phrases}: {exc}"
            ) from exc

    def process(self, frame: bytes) -> str | None:
        audio = self._np.frombuffer(frame, dtype=self._np.int16)
        predictions = self._model.predict(audio)
        for phrase, score in predictions.items():
            if score >= self._sensitivity:
                return phrase
        return None


class WakeWordDetector:
    """Continuously scans passive-mode microphone frames for a configured
    wake phrase and fires on_detected(phrase) when one matches.

    Constructor DI: receives the MicrophoneManager and WakeWordEngine it
    depends on, plus a callback, rather than constructing any of them
    itself (03_Engineering_Standards.md's Dependency Injection rule).
    """

    def __init__(
        self,
        mic: MicrophoneManager,
        engine: WakeWordEngine,
        on_detected: Callable[[str], None],
    ) -> None:
        self._mic = mic
        self._engine = engine
        self._on_detected = on_detected
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_processed_at: float | None = None

    def start(self) -> None:
        """Launch the background listening thread. Requires the
        microphone to already be in PASSIVE_LISTENING mode — this is the
        only mode wake-word scanning is permitted to run in (Microphone
        Rule)."""
        if self._mic.current_mode() is not MicrophoneMode.PASSIVE_LISTENING:
            raise WakeWordError(
                "WakeWordDetector requires the microphone to be in "
                "PASSIVE_LISTENING mode before start()."
            )
        self._stop_event.clear()
        self._last_processed_at = time.monotonic()
        self._thread = threading.Thread(
            target=self._listen_loop, name="wake-word-listener", daemon=True
        )
        self._thread.start()
        logger.info("Wake word detector started.")

    def stop(self) -> None:
        """Signal the listening thread to exit and join it."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
            if self._thread.is_alive():
                logger.error("Wake word listener thread did not stop within timeout.")
            self._thread = None
        logger.info("Wake word detector stopped.")

    def health_check(self) -> bool:
        """Thread alive AND a frame was successfully processed recently."""
        if self._thread is None or not self._thread.is_alive():
            return False
        if self._last_processed_at is None:
            return False
        return (time.monotonic() - self._last_processed_at) <= _HEALTH_STALENESS_SECONDS

    def _listen_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                frame = self._mic.read_frame()
                phrase = self._engine.process(frame)
                self._last_processed_at = time.monotonic()
                if phrase is not None:
                    self._on_detected(phrase)
            except MicrophoneError:
                # A device-level failure — MicrophoneManager is already
                # unhealthy at this point (Sprint 2.1). Ending the thread
                # (rather than spinning on a broken microphone) is what
                # makes health_check() reflect this via "thread not alive",
                # in addition to the staleness check.
                logger.exception("Microphone read failed inside wake word listen loop.")
                break
            except Exception:
                # Engine/processing hiccup on a single frame must not end
                # passive listening (see this sprint's own Risks) — logged
                # and the loop continues; _last_processed_at is deliberately
                # NOT updated, so a repeatedly-failing engine eventually
                # goes stale in health_check() even though the thread is
                # still alive and trying.
                logger.exception("Unexpected error inside wake word listen loop.")
