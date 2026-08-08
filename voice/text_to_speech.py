"""Text-to-Speech Engine — generates spoken responses for a given
(text, voice_id) pair.

Owns synthesis and playback only. voice_id is an opaque string this
module never interprets by persona name — CoquiTextToSpeech has zero
knowledge that Jarvis/Minie exist; that mapping lives entirely in
config/schema.py's VoiceConfig.jarvis_voice_id/minie_voice_id, read by the
Persona classes (Sprint 2.9/2.10), not here. See
docs/sprint_book/sprint_2_4.md.

Sensitive-data logging: spoken text is conversation content, never logged
above DEBUG, and even at DEBUG only via extra={"sensitive": True}
(Sprint 1.3's SensitiveDataFilter), same discipline as Sprint 2.3.

**`on_audio_ready` (Sprint 5.14, additive — defaults to `None`, every
existing caller's exact prior behavior preserved)**: a real gap found
while wiring `presentation/lip_sync.py`'s `LipSyncDriver.
drive_from_audio()` (Sprint 5.11) — that class needs the real
synthesized PCM buffer and sample rate to sample amplitude from, but
`speak()` bundles synthesis and blocking playback together with no
return value, and this module's own docstring deliberately keeps it
that way ("synthesis and playback only... zero knowledge that Jarvis/
Minie exist"). Rather than restructure `speak()` into separate
synthesize()/play() calls (a real API change every existing caller
would have to adopt), `on_audio_ready`, when given, is invoked with the
freshly-synthesized `(audio_bytes, sample_rate_hz)` immediately before
playback starts — letting a caller (Sprint 5.14's `CommunicationPipeline`)
spawn `LipSyncDriver`'s own non-blocking background thread so it runs
*alongside* `self._output.play()`'s blocking call, without this module
ever needing to know lip sync exists. Any exception from the callback
is caught and logged, never allowed to break real audio playback (Fail
Gracefully) — a presentation-layer failure must not silence JARMINEI.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from config.schema import ModelConfig
from core.logging_setup import get_logger
from core.module_registry import ServiceState
from core.runtime_manager import RuntimeManager
from voice.errors import TextToSpeechError

logger = get_logger(__name__)


class AudioOutput(Protocol):
    """Playback contract. Interface-first per 03_Engineering_Standards.md,
    mirrors AudioBackend (Sprint 2.1) on the output side."""

    def play(self, audio: bytes, sample_rate_hz: int) -> None: ...


class SoundDeviceAudioOutput:
    """AudioOutput implementation backed by sounddevice's blocking
    play/wait — audio is float32 PCM, matching Coqui's raw output dtype."""

    def play(self, audio: bytes, sample_rate_hz: int) -> None:
        import numpy as np
        import sounddevice as sd

        samples = np.frombuffer(audio, dtype=np.float32)
        sd.play(samples, samplerate=sample_rate_hz)
        sd.wait()


class TextToSpeech(Protocol):
    """Speech synthesis contract. Interface-first — Persona classes
    (Sprint 2.9+) depend on this, never the concrete Coqui type."""

    def speak(
        self,
        text: str,
        voice_id: str,
        on_audio_ready: Callable[[bytes, int], None] | None = None,
    ) -> None: ...


class CoquiTextToSpeech:
    """TextToSpeech implementation wrapping Coqui TTS.

    Loads its model once at start() (not per call to speak()). voice_id
    must be one of the loaded model's real speaker identifiers — resolving
    a friendly persona name (e.g. "jarvis") to a real speaker ID is
    config's job (VoiceConfig.jarvis_voice_id/minie_voice_id), not this
    module's, per this sprint's Engineering Rationale.
    """

    def __init__(self, model_config: ModelConfig, output: AudioOutput) -> None:
        self._model_name = model_config.tts_model
        self._output = output
        self._tts = None
        self._known_speakers: list[str] = []
        self._healthy = False
        # Runtime Phase 5 (Runtime Refactor Sprint) — LazyModule Protocol
        # additions (core/module_registry.py). See voice/speech_to_text.py's
        # WhisperSpeechToText for the identical reasoning, mirrored here.
        self._active = False
        self._last_used_at: datetime | None = None
        self._idle_timeout_seconds: float | None = None

    def start(self) -> None:
        """Load the configured Coqui model. Safe to call again without an
        intervening stop() (does not reload) — including after a previous
        failed attempt, since self._tts stays None until load actually
        succeeds, so the guard below correctly retries rather than
        skipping."""
        if self._tts is not None:
            return
        from TTS.api import TTS

        try:
            self._tts = TTS(model_name=self._model_name)
        except Exception as exc:
            raise TextToSpeechError(
                f"Failed to load Coqui TTS model {self._model_name!r}: {exc}"
            ) from exc
        self._known_speakers = list(self._tts.speakers or [])
        self._healthy = True
        logger.info(
            "Coqui TTS model loaded: %s (%d speakers).",
            self._model_name,
            len(self._known_speakers),
        )

    def stop(self) -> None:
        self._tts = None
        self._known_speakers = []
        self._healthy = False
        logger.info("Coqui TTS model released.")

    def health_check(self) -> bool:
        """Sprint 2.13 hardening (scenario c): a crashed speak() call
        leaves the loaded model object itself untouched, so checking only
        "is _tts set" would keep reporting healthy after a real synthesis
        or playback failure. _healthy tracks the outcome of the most
        recent speak() call — same flag pattern as WhisperSpeechToText
        (scenario b) and MicrophoneManager."""
        return self._tts is not None and self._healthy

    def state(self) -> ServiceState:
        """LazyModule Protocol (Runtime Phase 5). NOT_LOADED before
        start()/after stop(); ACTIVE while a real speak() call is in
        flight (never a valid eviction target for Runtime Phase 9); READY
        once loaded and idle."""
        if self._tts is None:
            return ServiceState.NOT_LOADED
        if self._active:
            return ServiceState.ACTIVE
        return ServiceState.READY

    def last_used_at(self) -> datetime | None:
        """LazyModule Protocol (Runtime Phase 5) — Runtime Phase 9's own
        idle-timeout sweep is the real reader; None until the first real
        speak() call."""
        return self._last_used_at

    def mark_idle_timeout(self, seconds: float) -> None:
        """LazyModule Protocol (Runtime Phase 5) — stored for Runtime
        Phase 9's idle-timeout sweep to read; nothing in this class acts
        on it yet."""
        self._idle_timeout_seconds = seconds

    def speak(
        self,
        text: str,
        voice_id: str,
        on_audio_ready: Callable[[bytes, int], None] | None = None,
    ) -> None:
        """Synthesize text with the given voice_id and play it, blocking
        until playback completes. Raises TextToSpeechError on an
        unrecognized voice_id or any synthesis/playback failure — never a
        silent no-op (the Persona system must never think the wrong voice
        spoke). on_audio_ready (Sprint 5.14) is called with the real
        synthesized buffer immediately before playback starts — see this
        module's own docstring."""
        if self._tts is None:
            raise TextToSpeechError("Cannot speak before start().")
        if self._known_speakers and voice_id not in self._known_speakers:
            raise TextToSpeechError(f"Unrecognized voice_id: {voice_id!r}")

        self._active = True
        self._last_used_at = datetime.now(UTC)
        logger.debug(
            "Synthesizing speech for voice_id=%s: %s", voice_id, text, extra={"sensitive": True}
        )
        try:
            samples = self._tts.tts(text=text, speaker=voice_id)
        except Exception as exc:
            self._healthy = False
            self._active = False
            logger.exception("Coqui TTS synthesis failed.")
            raise TextToSpeechError("Failed to synthesize speech.") from exc

        import numpy as np

        audio_bytes = np.asarray(samples, dtype=np.float32).tobytes()
        sample_rate_hz = self._tts.synthesizer.output_sample_rate

        if on_audio_ready is not None:
            try:
                on_audio_ready(audio_bytes, sample_rate_hz)
            except Exception:
                logger.exception("on_audio_ready callback failed; continuing with playback.")

        try:
            self._output.play(audio_bytes, sample_rate_hz)
        except Exception as exc:
            self._healthy = False
            self._active = False
            logger.exception("Audio playback failed.")
            raise TextToSpeechError("Failed to play synthesized speech.") from exc
        self._healthy = True
        self._active = False


class LazyTextToSpeech:
    """TextToSpeech implementation that defers to a real, already-
    registered LazyModule (CoquiTextToSpeech in production), calling
    RuntimeManager.ensure_started() before every speak() so the real
    model load happens on first genuine use — or whenever a background
    warm-up thread gets to it first (Runtime Phase 4) — rather than at
    CoreManager startup time.

    See voice/speech_to_text.py's LazySpeechToText for the identical
    reasoning, mirrored here for TTS. Owns no resource of its own — not a
    ManagedModule; real_tts is main.py's own CoquiTextToSpeech instance,
    the one actually registered with CoreManager/RuntimeManager under
    service_name.
    """

    def __init__(
        self, real_tts: TextToSpeech, service_name: str, runtime_manager: RuntimeManager
    ) -> None:
        self._real_tts = real_tts
        self._service_name = service_name
        self._runtime_manager = runtime_manager

    def speak(
        self,
        text: str,
        voice_id: str,
        on_audio_ready: Callable[[bytes, int], None] | None = None,
    ) -> None:
        self._runtime_manager.ensure_started(self._service_name)
        self._real_tts.speak(text, voice_id, on_audio_ready)
