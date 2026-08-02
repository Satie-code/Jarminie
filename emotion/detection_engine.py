"""Emotion Detection Engine (Sprint 5.1 — Level 5 Part A).

A **pure aggregator-plus-rule-evaluator, not a reasoning engine** — the
same distinction voice/context_manager.py's ContextManager draws for
itself. Deliberately rule-based, not a second LLM call: decision/
context_analyzer.py's ContextAnalyzer already makes a real Ollama call to
produce SentimentHint per turn, and that module's own docstring reserves
richer emotional framing for this Level ("Phase 5.1") specifically — this
engine treats SentimentHint as its primary, richest input rather than
duplicating a second, competing LLM classification pass. If a future
sprint finds the rule set genuinely insufficient, the correct fix is
deepening ContextAnalyzer's own SENTIMENT: prompt output, not adding a
parallel classifier here.

Never raises for any input, including an empty transcript, a None
ContextAnalysis (Decision Engine pipeline failure), or an empty
conversation history — degrades to EmotionLabel.UNKNOWN at
confidence=0.0, the identical fail-safe contract IntentDetector.detect()/
ContextAnalyzer.analyze() already established.

No live caller yet — voice/pipeline.py is not touched until Sprint 5.14
(Presentation Layer Integration), per this sprint's own Integration
Considerations. See docs/sprint_book/sprint_5_1.md.
"""

from collections import Counter
from datetime import UTC, datetime

from config.schema import EmotionConfig
from core.logging_setup import get_logger
from decision.context_analyzer import ContextAnalysis, SentimentHint
from emotion.models import EmotionEstimate, EmotionLabel, EmotionSignals
from voice.context_manager import ConversationContext
from voice.speech_to_text import TranscriptionResult

logger = get_logger(__name__)

_SENTIMENT_TO_LABEL: dict[SentimentHint, EmotionLabel] = {
    SentimentHint.STRESSED: EmotionLabel.STRESSED,
    SentimentHint.FRUSTRATED: EmotionLabel.FRUSTRATED,
    SentimentHint.TIRED: EmotionLabel.TIRED,
    SentimentHint.POSITIVE: EmotionLabel.HAPPY,
}
"""SentimentHint.NEUTRAL has no entry — a neutral sentiment carries no
primary signal of its own, falling through to the lexical-marker path
below rather than being mapped to any specific label."""

_HIGH_AROUSAL_LABELS: frozenset[EmotionLabel] = frozenset(
    {EmotionLabel.STRESSED, EmotionLabel.FRUSTRATED, EmotionLabel.EXCITED, EmotionLabel.CURIOUS}
)
_LOW_AROUSAL_LABELS: frozenset[EmotionLabel] = frozenset(
    {EmotionLabel.TIRED, EmotionLabel.CALM, EmotionLabel.CONFUSED}
)
"""Used only to break a tie among multiple equally-matched lexical
markers, and only when sentiment_hint is NEUTRAL (see estimate()) — never
an independent detector of their own."""


class EmotionDetectionEngine:
    """Constructor DI per 03_Engineering_Standards.md: receives only the
    EmotionConfig it depends on. Holds no external resource (no model
    load, no network, no file handle) — health_check() is trivially True
    once started, the same shape ContextManager/PersonaManager already
    have for stateless-dependency modules."""

    def __init__(self, emotion_config: EmotionConfig) -> None:
        self._config = emotion_config
        self._started = False

    def start(self) -> None:
        self._started = True
        logger.info("Emotion Detection Engine started.")

    def stop(self) -> None:
        self._started = False
        logger.info("Emotion Detection Engine stopped.")

    def health_check(self) -> bool:
        return self._started

    def collect_signals(
        self,
        transcription: TranscriptionResult,
        context_analysis: ContextAnalysis | None,
        context: ConversationContext,
    ) -> EmotionSignals:
        """Assemble raw behavioral signals for one turn. Pure and
        deterministic — never raises, never performs I/O."""
        collected_at = datetime.now(UTC)

        speaking_rate_wpm: float | None = None
        stripped_text = transcription.text.strip()
        if transcription.duration_ms > 0 and stripped_text:
            word_count = len(stripped_text.split())
            minutes = transcription.duration_ms / 60000.0
            if minutes > 0:
                speaking_rate_wpm = word_count / minutes

        pause_before_turn_seconds = 0.0
        if context.recent_turns:
            elapsed = (collected_at - context.last_activity_at).total_seconds()
            pause_before_turn_seconds = max(0.0, elapsed)

        sentiment_hint = (
            context_analysis.sentiment_hint
            if context_analysis is not None
            else SentimentHint.NEUTRAL
        )

        return EmotionSignals(
            speaking_rate_wpm=speaking_rate_wpm,
            pause_before_turn_seconds=pause_before_turn_seconds,
            sentiment_hint=sentiment_hint,
            matched_lexical_markers=_match_lexical_markers(transcription.text, self._config),
            no_speech_probability=transcription.no_speech_probability,
            collected_at=collected_at,
        )

    def estimate(self, signals: EmotionSignals) -> EmotionEstimate:
        """Turn EmotionSignals into a behavioral EmotionEstimate. Never
        raises. An honest "no read" (UNKNOWN/0.0) is always preferred
        over a forced guess — see this module's own docstring."""
        estimated_at = datetime.now(UTC)
        config = self._config

        sentiment_label = _SENTIMENT_TO_LABEL.get(signals.sentiment_hint)
        if sentiment_label is not None:
            label = sentiment_label
            confidence = config.sentiment_hint_base_confidence
            if sentiment_label in signals.matched_lexical_markers:
                confidence = min(1.0, confidence + config.lexical_marker_agreement_bonus)
        elif signals.matched_lexical_markers:
            label = _resolve_lexical_tie(signals.matched_lexical_markers, signals, config)
            confidence = config.lexical_only_base_confidence
            if _numeric_signals_support(label, signals, config):
                confidence = min(1.0, confidence + config.numeric_tie_break_bonus)
        else:
            label = EmotionLabel.UNKNOWN
            confidence = 0.0

        if confidence < config.min_estimate_confidence:
            label = EmotionLabel.UNKNOWN
            confidence = 0.0

        return EmotionEstimate(
            label=label, confidence=confidence, signals=signals, estimated_at=estimated_at
        )


def _match_lexical_markers(text: str, config: EmotionConfig) -> list[EmotionLabel]:
    """Case-insensitive substring matching against EmotionConfig.
    lexical_markers — the identical, deliberately crude technique
    PersonaManager.detect_context_heuristic()/MemoryConfig.
    short_term_salience_triggers already use. No NLU."""
    if not text:
        return []
    lowered = text.lower()
    matched: list[EmotionLabel] = []
    for label in EmotionLabel:
        if label is EmotionLabel.UNKNOWN:
            continue
        for keyword in config.lexical_markers.get(label.value, []):
            if keyword and keyword.lower() in lowered:
                matched.append(label)
    return matched


def _resolve_lexical_tie(
    matched: list[EmotionLabel], signals: EmotionSignals, config: EmotionConfig
) -> EmotionLabel:
    """Pick one EmotionLabel among possibly-several matched lexical
    markers. Most-frequently-matched label wins; a tie is broken first by
    numeric signals (fast speech -> a high-arousal candidate, a long
    pause -> a low-arousal candidate), then, deterministically, by
    EmotionLabel declaration order."""
    counts = Counter(matched)
    max_count = max(counts.values())
    top_candidates = [label for label in EmotionLabel if counts.get(label, 0) == max_count]

    if len(top_candidates) == 1:
        return top_candidates[0]

    fast_speech = (
        signals.speaking_rate_wpm is not None
        and signals.speaking_rate_wpm > config.speaking_rate_baseline_wpm
    )
    long_pause = signals.pause_before_turn_seconds > config.long_pause_threshold_seconds

    if fast_speech:
        for label in top_candidates:
            if label in _HIGH_AROUSAL_LABELS:
                return label
    if long_pause:
        for label in top_candidates:
            if label in _LOW_AROUSAL_LABELS:
                return label
    return top_candidates[0]


def _numeric_signals_support(
    label: EmotionLabel, signals: EmotionSignals, config: EmotionConfig
) -> bool:
    """Whether speaking rate / pause length corroborate a lexically-
    derived label — used only to nudge confidence, never to select a
    label on their own (see estimate())."""
    fast_speech = (
        signals.speaking_rate_wpm is not None
        and signals.speaking_rate_wpm > config.speaking_rate_baseline_wpm
    )
    long_pause = signals.pause_before_turn_seconds > config.long_pause_threshold_seconds
    if fast_speech and label in _HIGH_AROUSAL_LABELS:
        return True
    return bool(long_pause and label in _LOW_AROUSAL_LABELS)
