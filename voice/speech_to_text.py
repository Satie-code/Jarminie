"""Speech-to-Text Engine — converts a captured utterance buffer into text.

Owns transcription only: given a bounded chunk of audio bytes, return text.
Deciding *when* an utterance is complete (silence detection, turn
boundaries) belongs to Voice Session Manager (Sprint 2.5), not here
(Single Responsibility). See docs/sprint_book/sprint_2_3.md.

Sensitive-data logging: transcribed text is spoken conversation content,
the most sensitive category 03_Engineering_Standards.md's Logging
Strategy warns against. It is never logged above DEBUG, and even at DEBUG
only via extra={"sensitive": True} (Sprint 1.3's SensitiveDataFilter),
which redacts the message content at the handler level regardless of what
was passed in.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from config.schema import ModelConfig
from core.logging_setup import get_logger
from core.module_registry import ServiceState
from core.runtime_manager import RuntimeManager
from voice.errors import SpeechToTextError

logger = get_logger(__name__)


@dataclass
class TranscriptionResult:
    """Result of transcribing one utterance.

    average_confidence is Whisper's own decode confidence (derived from
    its segment-level avg_logprob), a model output — unrelated to the
    project's Dynamic Memory confidence score from Part 2 (Level 3's
    Dynamic Memory Formula). Must not be conflated with it in later
    sprints.

    no_speech_probability is Whisper's own average per-segment
    no_speech_prob. text is already forced empty by transcribe() whenever
    this exceeds ModelConfig.whisper_no_speech_threshold, so callers don't
    need to re-check it themselves — exposed mainly for observability/logging.
    """

    text: str
    average_confidence: float
    duration_ms: int
    no_speech_probability: float = 0.0


class SpeechToText(Protocol):
    """Transcription contract. Interface-first per
    03_Engineering_Standards.md, so Whisper can be replaced by a future
    engine without touching callers."""

    def transcribe(self, audio: bytes) -> TranscriptionResult: ...


class WhisperSpeechToText:
    """SpeechToText implementation wrapping openai-whisper.

    Loads its model once at start(), not per call to transcribe() — the
    whisper/torch import itself is deliberately lazy (inside start(), not
    at module level) so importing this module for its Protocol/dataclass
    doesn't pay that cost when a caller only needs a fake for testing.
    """

    def __init__(self, model_config: ModelConfig) -> None:
        self._model_name = model_config.whisper_model
        self._no_speech_threshold = model_config.whisper_no_speech_threshold
        self._initial_prompt = model_config.whisper_initial_prompt
        self._model = None
        self._healthy = False
        # Runtime Phase 5 (Runtime Refactor Sprint) — LazyModule Protocol
        # additions (core/module_registry.py). _active distinguishes a
        # genuinely in-flight transcribe() call from merely-loaded-and-
        # idle, so a future idle-unload/resource-pressure sweep (Runtime
        # Phase 9) never evicts this service mid-request. _last_used_at/
        # _idle_timeout_seconds are read/written by that same future
        # phase; nothing in this one reads them yet.
        self._active = False
        self._last_used_at: datetime | None = None
        self._idle_timeout_seconds: float | None = None

    def start(self) -> None:
        """Load the configured Whisper model. Safe to call again without
        an intervening stop() (does not reload) — including after a
        previous failed attempt, since self._model stays None until load
        actually succeeds, so the guard below correctly retries rather
        than skipping."""
        if self._model is not None:
            return
        import whisper

        try:
            self._model = whisper.load_model(self._model_name)
        except Exception as exc:
            raise SpeechToTextError(
                f"Failed to load Whisper model {self._model_name!r}: {exc}"
            ) from exc
        self._healthy = True
        logger.info("Whisper model loaded: %s", self._model_name)

    def stop(self) -> None:
        self._model = None
        self._healthy = False
        logger.info("Whisper model released.")

    def health_check(self) -> bool:
        """Sprint 2.13 hardening (scenario b): a crashed transcribe() call
        leaves self._model itself untouched (the loaded model object is
        still there), so checking only "is _model set" would keep
        reporting healthy even after a real inference failure. _healthy
        tracks the outcome of the most recent transcribe() call — set
        False on a crash, restored True on the next successful one — the
        same flag pattern already used by MicrophoneManager."""
        return self._model is not None and self._healthy

    def state(self) -> ServiceState:
        """LazyModule Protocol (Runtime Phase 5). NOT_LOADED before
        start()/after stop() — never reported as "unhealthy" just for
        being unloaded; that's a distinct, expected state, not a failure.
        ACTIVE while a real transcribe() call is in flight (never a valid
        eviction target for Runtime Phase 9); READY once loaded and idle."""
        if self._model is None:
            return ServiceState.NOT_LOADED
        if self._active:
            return ServiceState.ACTIVE
        return ServiceState.READY

    def last_used_at(self) -> datetime | None:
        """LazyModule Protocol (Runtime Phase 5) — Runtime Phase 9's own
        idle-timeout sweep is the real reader; None until the first real
        transcribe() call."""
        return self._last_used_at

    def mark_idle_timeout(self, seconds: float) -> None:
        """LazyModule Protocol (Runtime Phase 5) — stored for Runtime
        Phase 9's idle-timeout sweep to read; nothing in this class acts
        on it yet."""
        self._idle_timeout_seconds = seconds

    def transcribe(self, audio: bytes) -> TranscriptionResult:
        """Transcribe a complete utterance buffer (int16 PCM bytes).

        Raises SpeechToTextError on any failure — never a bare/unlabeled
        exception (Fail Gracefully Rule) — so the caller (Voice Session
        Manager, Sprint 2.5) can catch one clear type.
        """
        if self._model is None:
            raise SpeechToTextError("Cannot transcribe before start().")

        import numpy as np

        self._active = True
        self._last_used_at = datetime.now(UTC)
        started_at = time.monotonic()
        try:
            samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
            result = self._model.transcribe(samples, initial_prompt=self._initial_prompt or None)
        except Exception as exc:
            self._healthy = False
            self._active = False
            logger.exception("Whisper transcription failed.")
            raise SpeechToTextError("Failed to transcribe audio.") from exc
        self._healthy = True
        self._active = False
        duration_ms = int((time.monotonic() - started_at) * 1000)

        segments = result.get("segments", [])
        text = result.get("text", "").strip()
        confidence = _average_confidence(segments)
        no_speech_probability = _average_no_speech_probability(segments)

        if no_speech_probability >= self._no_speech_threshold:
            # Whisper's own no-speech skip logic can be overridden internally
            # when a hallucinated segment's avg_logprob looks confident (see
            # docs/sprint_book/sprint_2_3.md's Post-Sprint Fix) — real ambient
            # noise can otherwise produce fluent but fabricated text. Applying
            # the threshold here, unconditionally, is what actually prevents
            # a hallucination from reaching the caller as real "speech."
            if text:
                logger.debug(
                    "Suppressing likely-hallucinated transcript (no_speech_probability=%.2f): %s",
                    no_speech_probability,
                    text,
                    extra={"sensitive": True},
                )
            text = ""

        logger.info(
            "Transcription completed in %d ms (confidence=%.2f, no_speech_probability=%.2f).",
            duration_ms,
            confidence,
            no_speech_probability,
        )
        logger.debug("Transcribed text: %s", text, extra={"sensitive": True})

        return TranscriptionResult(
            text=text,
            average_confidence=confidence,
            duration_ms=duration_ms,
            no_speech_probability=no_speech_probability,
        )


class LazySpeechToText:
    """SpeechToText implementation that defers to a real, already-
    registered LazyModule (WhisperSpeechToText in production), calling
    RuntimeManager.ensure_started() before every transcribe() so the real
    model load happens on first genuine use — or whenever a background
    warm-up thread gets to it first (Runtime Phase 4) — rather than at
    CoreManager startup time.

    voice/session_manager.py's own transcribe() call site (Sprint 2.5)
    needs zero changes: this class satisfies the identical SpeechToText
    Protocol WhisperSpeechToText does, so VoiceSessionManager can't tell
    the difference — "no subsystem should directly decide when it
    loads" (Runtime Refactor Sprint, founding requirement), kept true by
    having that decision live entirely inside RuntimeManager, never in
    VoiceSessionManager itself.

    Owns no resource of its own — not a ManagedModule, the same "plain
    wrapper" convention already established for e.g. memory/event_memory.py
    (Sprint 3.3). real_stt is main.py's own WhisperSpeechToText instance,
    the one actually registered with CoreManager/RuntimeManager under
    service_name; this class only ever forwards to it.
    """

    def __init__(
        self, real_stt: SpeechToText, service_name: str, runtime_manager: RuntimeManager
    ) -> None:
        self._real_stt = real_stt
        self._service_name = service_name
        self._runtime_manager = runtime_manager

    def transcribe(self, audio: bytes) -> TranscriptionResult:
        self._runtime_manager.ensure_started(self._service_name)
        return self._real_stt.transcribe(audio)


def _average_confidence(segments: list[dict]) -> float:
    """Convert Whisper's per-segment avg_logprob (a negative log-probability,
    closer to 0 = more confident) into a 0-1-ish confidence value."""
    if not segments:
        return 0.0
    import math

    avg_logprob = sum(seg.get("avg_logprob", 0.0) for seg in segments) / len(segments)
    return math.exp(avg_logprob)


def _average_no_speech_probability(segments: list[dict]) -> float:
    """Average Whisper's per-segment no_speech_prob. No segments at all is
    itself already a no-speech result, so it's treated as full confidence
    (1.0) rather than 0.0 — the absence of any segment is not ambiguous."""
    if not segments:
        return 1.0
    return sum(seg.get("no_speech_prob", 0.0) for seg in segments) / len(segments)
