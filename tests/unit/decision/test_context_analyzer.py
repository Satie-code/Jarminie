"""Unit tests for decision.context_analyzer.

Uses only a local, in-file fake LanguageModelClient — no real Ollama
call is made (real-model verification is deferred to Sprint 3.14, per
this sprint's own Testing Checklist), same convention as
test_intent_detector.py (Sprint 3.7).
"""

from datetime import UTC, datetime

import pytest

from config.schema import ModelConfig
from decision.context_analyzer import ContextAnalyzer, SentimentHint
from decision.llm_client import LlmError
from decision.models import Intent, IntentCategory
from voice.context_manager import ConversationContext
from voice.conversation_store import ConversationTurn


class FakeLanguageModelClient:
    """Implements ONLY the LanguageModelClient Protocol (no
    is_reachable) — same convention as Sprint 3.7's fake."""

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, float]] = []

    def generate(self, prompt: str, timeout_seconds: float) -> str:
        self.calls.append((prompt, timeout_seconds))
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


class FakeReachabilityAwareClient(FakeLanguageModelClient):
    def __init__(self, reachable: bool, **kwargs) -> None:
        super().__init__(**kwargs)
        self._reachable = reachable

    def is_reachable(self) -> bool:
        return self._reachable


@pytest.fixture
def model_config() -> ModelConfig:
    return ModelConfig(ollama_timeout_seconds=5.0)


@pytest.fixture
def context() -> ConversationContext:
    now = datetime.now(UTC)
    return ConversationContext(
        session_id="session-1",
        active_persona_name="jarvis",
        recent_turns=[
            ConversationTurn(
                session_id="session-1",
                persona_name="jarvis",
                timestamp=now,
                user_text="what's the weather",
                response_text="It's sunny.",
            )
        ],
        session_started_at=now,
        last_activity_at=now,
    )


def make_intent(
    transcript: str = "some transcript",
    category: IntentCategory = IntentCategory.INFORMATIONAL,
) -> Intent:
    return Intent(
        category=category, confidence=0.8, raw_transcript=transcript, detected_at=datetime.now(UTC)
    )


def test_analyze_extracts_topic_and_entities(model_config, context):
    response = (
        "TOPIC: weather in Paris\n"
        "ENTITIES: Paris, tomorrow\n"
        "REFERENCES_PAST: NO\n"
        "PERSONA: NONE\n"
        "SENTIMENT: NEUTRAL"
    )
    client = FakeLanguageModelClient(response=response)
    analyzer = ContextAnalyzer(client, model_config)

    result = analyzer.analyze(make_intent("What's the weather like in Paris tomorrow?"), context)

    assert result.primary_topic == "weather in Paris"
    assert result.mentioned_entities == ["Paris", "tomorrow"]
    assert result.references_past_memory is False
    assert result.suggested_persona is None
    assert result.sentiment_hint is SentimentHint.NEUTRAL


def test_analyze_treats_entities_none_as_empty_list(model_config, context):
    response = (
        "TOPIC: greeting\nENTITIES: NONE\nREFERENCES_PAST: NO\nPERSONA: NONE\nSENTIMENT: POSITIVE"
    )
    client = FakeLanguageModelClient(response=response)
    analyzer = ContextAnalyzer(client, model_config)

    result = analyzer.analyze(make_intent("hello there"), context)

    assert result.mentioned_entities == []
    assert result.sentiment_hint is SentimentHint.POSITIVE


@pytest.mark.parametrize(
    ("transcript", "persona_line", "expected"),
    [
        (
            "Can you help me fix this bug in my code before the deadline?",
            "PERSONA: JARVIS",
            "jarvis",
        ),
        ("I've been feeling really overwhelmed and tired lately.", "PERSONA: MINIE", "minie"),
        ("What time is it?", "PERSONA: NONE", None),
    ],
)
def test_analyze_suggested_persona_matches_technical_vs_casual_fixtures(
    model_config, context, transcript, persona_line, expected
):
    response = (
        f"TOPIC: something\nENTITIES: NONE\nREFERENCES_PAST: NO\n{persona_line}\nSENTIMENT: NEUTRAL"
    )
    client = FakeLanguageModelClient(response=response)
    analyzer = ContextAnalyzer(client, model_config)

    result = analyzer.analyze(make_intent(transcript), context)

    assert result.suggested_persona == expected


@pytest.mark.parametrize(
    ("references_past_line", "expected"),
    [("REFERENCES_PAST: YES", True), ("REFERENCES_PAST: NO", False)],
)
def test_analyze_references_past_memory_detection(
    model_config, context, references_past_line, expected
):
    response = (
        f"TOPIC: something\nENTITIES: NONE\n{references_past_line}\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    client = FakeLanguageModelClient(response=response)
    analyzer = ContextAnalyzer(client, model_config)

    result = analyzer.analyze(make_intent("do you remember what I told you?"), context)

    assert result.references_past_memory is expected


def test_analyze_degrades_to_neutral_default_on_llm_error(model_config, context):
    client = FakeLanguageModelClient(error=LlmError("connection failed"))
    analyzer = ContextAnalyzer(client, model_config)

    result = analyzer.analyze(make_intent("hello"), context)

    assert result.primary_topic == ""
    assert result.mentioned_entities == []
    assert result.references_past_memory is False
    assert result.suggested_persona is None
    assert result.sentiment_hint is SentimentHint.NEUTRAL


def test_analyze_degrades_to_neutral_default_on_a_simulated_timeout(model_config, context):
    """Indistinguishable from any other LlmError at this level — OllamaClient
    (Sprint 3.7) is responsible for wrapping a raw timeout into LlmError."""
    client = FakeLanguageModelClient(error=LlmError("Ollama generate() timed out"))
    analyzer = ContextAnalyzer(client, model_config)

    result = analyzer.analyze(make_intent("hello"), context)

    assert result.sentiment_hint is SentimentHint.NEUTRAL
    assert result.suggested_persona is None


def test_analyze_degrades_to_neutral_default_on_an_unparseable_response(model_config, context):
    client = FakeLanguageModelClient(response="I'm not sure what you mean.")
    analyzer = ContextAnalyzer(client, model_config)

    result = analyzer.analyze(make_intent("hello"), context)

    assert result.primary_topic == ""
    assert result.mentioned_entities == []
    assert result.suggested_persona is None
    assert result.sentiment_hint is SentimentHint.NEUTRAL


def test_analyze_degrades_to_neutral_default_on_an_unrecognized_persona_or_sentiment(
    model_config, context
):
    response = (
        "TOPIC: something\nENTITIES: NONE\nREFERENCES_PAST: NO\nPERSONA: BANANA\nSENTIMENT: ANGRY"
    )
    client = FakeLanguageModelClient(response=response)
    analyzer = ContextAnalyzer(client, model_config)

    result = analyzer.analyze(make_intent("hello"), context)

    assert result.suggested_persona is None
    assert result.sentiment_hint is SentimentHint.NEUTRAL


def test_analyze_never_raises_for_an_empty_transcript(model_config, context):
    client = FakeLanguageModelClient(response="should never be reached")
    analyzer = ContextAnalyzer(client, model_config)

    result = analyzer.analyze(make_intent(""), context)

    assert result.primary_topic == ""
    assert client.calls == []


def test_analyze_never_raises_for_a_whitespace_only_transcript(model_config, context):
    client = FakeLanguageModelClient(response="should never be reached")
    analyzer = ContextAnalyzer(client, model_config)

    analyzer.analyze(make_intent("   "), context)

    assert client.calls == []


def test_analyze_passes_the_configured_timeout(model_config, context):
    response = "TOPIC: x\nENTITIES: NONE\nREFERENCES_PAST: NO\nPERSONA: NONE\nSENTIMENT: NEUTRAL"
    client = FakeLanguageModelClient(response=response)
    analyzer = ContextAnalyzer(client, model_config)

    analyzer.analyze(make_intent("hello"), context)

    assert client.calls[0][1] == model_config.ollama_timeout_seconds


def test_health_check_false_before_start(model_config):
    analyzer = ContextAnalyzer(FakeLanguageModelClient(), model_config)

    assert analyzer.health_check() is False


def test_start_is_healthy_when_client_has_no_reachability_capability(model_config):
    analyzer = ContextAnalyzer(FakeLanguageModelClient(), model_config)

    analyzer.start()

    assert analyzer.health_check() is True


def test_start_is_degraded_when_client_reports_unreachable(model_config):
    analyzer = ContextAnalyzer(FakeReachabilityAwareClient(reachable=False), model_config)

    analyzer.start()

    assert analyzer.health_check() is False


def test_health_check_recovers_after_a_successful_analyze_following_a_degraded_start(
    model_config, context
):
    response = "TOPIC: x\nENTITIES: NONE\nREFERENCES_PAST: NO\nPERSONA: NONE\nSENTIMENT: NEUTRAL"
    client = FakeReachabilityAwareClient(reachable=False, response=response)
    analyzer = ContextAnalyzer(client, model_config)
    analyzer.start()
    assert analyzer.health_check() is False

    analyzer.analyze(make_intent("hello"), context)

    assert analyzer.health_check() is True


def test_health_check_goes_false_after_an_analyze_failure(model_config, context):
    client = FakeReachabilityAwareClient(reachable=True, error=LlmError("boom"))
    analyzer = ContextAnalyzer(client, model_config)
    analyzer.start()
    assert analyzer.health_check() is True

    analyzer.analyze(make_intent("hello"), context)

    assert analyzer.health_check() is False


def test_stop_does_not_raise(model_config):
    analyzer = ContextAnalyzer(FakeLanguageModelClient(), model_config)
    analyzer.start()

    analyzer.stop()


def test_no_clinical_or_diagnostic_language_in_sentiment_hint_values():
    """Acceptance criterion: no value in SentimentHint uses clinical/
    diagnostic language (Level 5 Emotion Engine boundary, see this
    module's docstring)."""
    disallowed = {"depressed", "depression", "anxiety disorder", "diagnosis", "clinical"}
    for member in SentimentHint:
        assert member.value.lower() not in disallowed
