"""Unit tests for emotion.detection_engine.

No real Ollama/Whisper call is made — ContextAnalysis/TranscriptionResult
are constructed directly as plain fixtures, matching
test_context_analyzer.py's own established convention.
"""

from datetime import UTC, datetime, timedelta

import pytest

from config.schema import EmotionConfig
from decision.context_analyzer import ContextAnalysis, SentimentHint
from emotion.detection_engine import EmotionDetectionEngine
from emotion.models import EmotionLabel, EmotionSignals
from voice.context_manager import ConversationContext
from voice.conversation_store import ConversationTurn
from voice.speech_to_text import TranscriptionResult


@pytest.fixture
def emotion_config() -> EmotionConfig:
    return EmotionConfig()


@pytest.fixture
def engine(emotion_config: EmotionConfig) -> EmotionDetectionEngine:
    engine = EmotionDetectionEngine(emotion_config)
    engine.start()
    return engine


def _transcription(text: str = "hello there", duration_ms: int = 2000) -> TranscriptionResult:
    return TranscriptionResult(
        text=text, average_confidence=0.9, duration_ms=duration_ms, no_speech_probability=0.05
    )


def _context_analysis(sentiment: SentimentHint = SentimentHint.NEUTRAL) -> ContextAnalysis:
    return ContextAnalysis(
        primary_topic="general",
        mentioned_entities=[],
        references_past_memory=False,
        suggested_persona=None,
        sentiment_hint=sentiment,
        analyzed_at=datetime.now(UTC),
    )


def _context(recent_turns: list[ConversationTurn] | None = None) -> ConversationContext:
    now = datetime.now(UTC)
    return ConversationContext(
        session_id="session-1",
        active_persona_name="jarvis",
        recent_turns=recent_turns or [],
        session_started_at=now,
        last_activity_at=now,
    )


def _turn(timestamp: datetime) -> ConversationTurn:
    return ConversationTurn(
        session_id="session-1",
        persona_name="jarvis",
        timestamp=timestamp,
        user_text="hi",
        response_text="hello",
    )


class TestLifecycle:
    def test_health_check_false_before_start(self, emotion_config: EmotionConfig) -> None:
        engine = EmotionDetectionEngine(emotion_config)
        assert engine.health_check() is False

    def test_health_check_true_after_start(self, engine: EmotionDetectionEngine) -> None:
        assert engine.health_check() is True

    def test_health_check_false_after_stop(self, engine: EmotionDetectionEngine) -> None:
        engine.stop()
        assert engine.health_check() is False


class TestCollectSignals:
    def test_speaking_rate_computed_for_normal_input(self, engine: EmotionDetectionEngine) -> None:
        # 4 words in 2000ms (1/30 min) -> 120 wpm
        transcription = _transcription(text="this is four words", duration_ms=2000)
        signals = engine.collect_signals(transcription, None, _context())
        assert signals.speaking_rate_wpm == pytest.approx(120.0, rel=0.01)

    def test_speaking_rate_none_for_zero_duration(self, engine: EmotionDetectionEngine) -> None:
        transcription = _transcription(text="hello", duration_ms=0)
        signals = engine.collect_signals(transcription, None, _context())
        assert signals.speaking_rate_wpm is None

    def test_speaking_rate_none_for_empty_text(self, engine: EmotionDetectionEngine) -> None:
        transcription = _transcription(text="   ", duration_ms=2000)
        signals = engine.collect_signals(transcription, None, _context())
        assert signals.speaking_rate_wpm is None

    def test_pause_zero_when_no_recent_turns(self, engine: EmotionDetectionEngine) -> None:
        signals = engine.collect_signals(_transcription(), None, _context(recent_turns=[]))
        assert signals.pause_before_turn_seconds == 0.0

    def test_pause_reflects_elapsed_time_since_last_turn(
        self, engine: EmotionDetectionEngine
    ) -> None:
        last_activity = datetime.now(UTC) - timedelta(seconds=30)
        context = ConversationContext(
            session_id="session-1",
            active_persona_name="jarvis",
            recent_turns=[_turn(last_activity)],
            session_started_at=last_activity,
            last_activity_at=last_activity,
        )
        signals = engine.collect_signals(_transcription(), None, context)
        assert signals.pause_before_turn_seconds >= 29.0

    def test_sentiment_hint_passthrough_from_context_analysis(
        self, engine: EmotionDetectionEngine
    ) -> None:
        signals = engine.collect_signals(
            _transcription(), _context_analysis(SentimentHint.STRESSED), _context()
        )
        assert signals.sentiment_hint == SentimentHint.STRESSED

    def test_sentiment_hint_neutral_when_context_analysis_is_none(
        self, engine: EmotionDetectionEngine
    ) -> None:
        signals = engine.collect_signals(_transcription(), None, _context())
        assert signals.sentiment_hint == SentimentHint.NEUTRAL

    def test_matched_lexical_markers_found(self, engine: EmotionDetectionEngine) -> None:
        transcription = _transcription(text="I am so tired and exhausted today")
        signals = engine.collect_signals(transcription, None, _context())
        assert EmotionLabel.TIRED in signals.matched_lexical_markers

    def test_no_speech_probability_passthrough(self, engine: EmotionDetectionEngine) -> None:
        transcription = _transcription()
        transcription.no_speech_probability = 0.42
        signals = engine.collect_signals(transcription, None, _context())
        assert signals.no_speech_probability == 0.42

    def test_never_raises_on_empty_everything(self, engine: EmotionDetectionEngine) -> None:
        transcription = TranscriptionResult(
            text="", average_confidence=0.0, duration_ms=0, no_speech_probability=1.0
        )
        signals = engine.collect_signals(transcription, None, _context(recent_turns=[]))
        assert signals.matched_lexical_markers == []
        assert signals.speaking_rate_wpm is None


class TestEstimate:
    def _signals(self, **overrides) -> EmotionSignals:
        defaults = dict(
            speaking_rate_wpm=150.0,
            pause_before_turn_seconds=1.0,
            sentiment_hint=SentimentHint.NEUTRAL,
            matched_lexical_markers=[],
            no_speech_probability=0.05,
            collected_at=datetime.now(UTC),
        )
        defaults.update(overrides)
        return EmotionSignals(**defaults)

    @pytest.mark.parametrize(
        ("sentiment", "expected_label"),
        [
            (SentimentHint.STRESSED, EmotionLabel.STRESSED),
            (SentimentHint.FRUSTRATED, EmotionLabel.FRUSTRATED),
            (SentimentHint.TIRED, EmotionLabel.TIRED),
            (SentimentHint.POSITIVE, EmotionLabel.HAPPY),
        ],
    )
    def test_sentiment_hint_drives_label(
        self, engine: EmotionDetectionEngine, sentiment: SentimentHint, expected_label: EmotionLabel
    ) -> None:
        estimate = engine.estimate(self._signals(sentiment_hint=sentiment))
        assert estimate.label is expected_label
        assert estimate.confidence > 0.0

    def test_sentiment_and_lexical_agreement_boosts_confidence(
        self, engine: EmotionDetectionEngine
    ) -> None:
        without_agreement = engine.estimate(self._signals(sentiment_hint=SentimentHint.STRESSED))
        with_agreement = engine.estimate(
            self._signals(
                sentiment_hint=SentimentHint.STRESSED,
                matched_lexical_markers=[EmotionLabel.STRESSED],
            )
        )
        assert with_agreement.confidence > without_agreement.confidence

    @pytest.mark.parametrize(
        ("markers", "expected_label"),
        [
            ([EmotionLabel.CALM], EmotionLabel.CALM),
            ([EmotionLabel.EXCITED], EmotionLabel.EXCITED),
            ([EmotionLabel.CONFUSED], EmotionLabel.CONFUSED),
            ([EmotionLabel.CURIOUS], EmotionLabel.CURIOUS),
            ([EmotionLabel.FOCUSED], EmotionLabel.FOCUSED),
        ],
    )
    def test_lexical_only_path_reaches_unmapped_labels(
        self,
        engine: EmotionDetectionEngine,
        markers: list[EmotionLabel],
        expected_label: EmotionLabel,
    ) -> None:
        estimate = engine.estimate(
            self._signals(sentiment_hint=SentimentHint.NEUTRAL, matched_lexical_markers=markers)
        )
        assert estimate.label is expected_label

    def test_unknown_when_no_signal_points_anywhere(self, engine: EmotionDetectionEngine) -> None:
        estimate = engine.estimate(self._signals(sentiment_hint=SentimentHint.NEUTRAL))
        assert estimate.label is EmotionLabel.UNKNOWN
        assert estimate.confidence == 0.0

    def test_min_confidence_floor_discounts_to_unknown(self) -> None:
        # A very high floor makes even a normally-confident estimate fall back.
        strict_config = EmotionConfig(min_estimate_confidence=0.99)
        engine = EmotionDetectionEngine(strict_config)
        estimate = engine.estimate(self._signals(sentiment_hint=SentimentHint.STRESSED))
        assert estimate.label is EmotionLabel.UNKNOWN
        assert estimate.confidence == 0.0

    def test_fast_speech_breaks_tie_toward_high_arousal(
        self, engine: EmotionDetectionEngine
    ) -> None:
        # CALM (low-arousal) and EXCITED (high-arousal) tied at one match each.
        estimate = engine.estimate(
            self._signals(
                sentiment_hint=SentimentHint.NEUTRAL,
                matched_lexical_markers=[EmotionLabel.CALM, EmotionLabel.EXCITED],
                speaking_rate_wpm=220.0,
            )
        )
        assert estimate.label is EmotionLabel.EXCITED

    def test_long_pause_breaks_tie_toward_low_arousal(self, engine: EmotionDetectionEngine) -> None:
        estimate = engine.estimate(
            self._signals(
                sentiment_hint=SentimentHint.NEUTRAL,
                matched_lexical_markers=[EmotionLabel.CALM, EmotionLabel.EXCITED],
                speaking_rate_wpm=100.0,
                pause_before_turn_seconds=10.0,
            )
        )
        assert estimate.label is EmotionLabel.CALM

    def test_never_raises_for_degenerate_signals(self, engine: EmotionDetectionEngine) -> None:
        estimate = engine.estimate(
            self._signals(
                speaking_rate_wpm=None,
                matched_lexical_markers=[],
                pause_before_turn_seconds=0.0,
            )
        )
        assert estimate.label is EmotionLabel.UNKNOWN

    def test_estimate_always_carries_its_own_signals(self, engine: EmotionDetectionEngine) -> None:
        signals = self._signals(sentiment_hint=SentimentHint.STRESSED)
        estimate = engine.estimate(signals)
        assert estimate.signals is signals
