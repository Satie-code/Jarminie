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
from typing import Protocol

from config.schema import ModelConfig
from core.logging_setup import get_logger
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
        self._model = None

    def start(self) -> None:
        """Load the configured Whisper model. Safe to call again without
        an intervening stop() — does not reload."""
        if self._model is not None:
            return
        import whisper

        try:
            self._model = whisper.load_model(self._model_name)
        except Exception as exc:
            raise SpeechToTextError(
                f"Failed to load Whisper model {self._model_name!r}: {exc}"
            ) from exc
        logger.info("Whisper model loaded: %s", self._model_name)

    def stop(self) -> None:
        self._model = None
        logger.info("Whisper model released.")

    def health_check(self) -> bool:
        return self._model is not None

    def transcribe(self, audio: bytes) -> TranscriptionResult:
        """Transcribe a complete utterance buffer (int16 PCM bytes).

        Raises SpeechToTextError on any failure — never a bare/unlabeled
        exception (Fail Gracefully Rule) — so the caller (Voice Session
        Manager, Sprint 2.5) can catch one clear type.
        """
        if self._model is None:
            raise SpeechToTextError("Cannot transcribe before start().")

        import numpy as np

        started_at = time.monotonic()
        try:
            samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
            result = self._model.transcribe(samples)
        except Exception as exc:
            logger.exception("Whisper transcription failed.")
            raise SpeechToTextError("Failed to transcribe audio.") from exc
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
