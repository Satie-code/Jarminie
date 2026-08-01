"""Unit tests for decision.intent_detector.

Uses only a local, in-file fake LanguageModelClient — no real Ollama call
is made (real-model classification-accuracy verification is explicitly
deferred to Sprint 3.14, per this sprint's own Testing Checklist). This
is the same "fake at the ML boundary" convention used for Whisper/Coqui/
openWakeWord throughout Level 2.
"""

from datetime import UTC, datetime

import pytest

from config.schema import ModelConfig
from decision.intent_detector import IntentDetector
from decision.llm_client import LlmError
from decision.models import IntentCategory
from voice.context_manager import ConversationContext
from voice.conversation_store import ConversationTurn


class FakeLanguageModelClient:
    """Deliberately implements ONLY the LanguageModelClient Protocol (no
    is_reachable) — proves IntentDetector.start() tolerates a minimal
    client that satisfies nothing beyond the shared contract."""

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, float, list[str] | None]] = []

    def generate(
        self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
    ) -> str:
        self.calls.append((prompt, timeout_seconds, stop))
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


class FakeReachabilityAwareClient(FakeLanguageModelClient):
    """Adds the optional is_reachable() capability OllamaClient exposes,
    to exercise IntentDetector.start()'s degraded-start path."""

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


@pytest.mark.parametrize(
    ("response_text", "expected_category", "expected_confidence"),
    [
        ("CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9", IntentCategory.INFORMATIONAL, 0.9),
        ("CATEGORY: action_request\nCONFIDENCE: 1", IntentCategory.ACTION_REQUEST, 1.0),
        ("CATEGORY: Memory_Recall\nCONFIDENCE: 0.75", IntentCategory.MEMORY_RECALL, 0.75),
        ("CATEGORY: EMOTIONAL_SUPPORT\nCONFIDENCE: 0.6", IntentCategory.EMOTIONAL_SUPPORT, 0.6),
        ("CATEGORY: EMERGENCY\nCONFIDENCE: 0.99", IntentCategory.EMERGENCY, 0.99),
        ("CATEGORY: casual_conversation\nCONFIDENCE: 0.5", IntentCategory.CASUAL_CONVERSATION, 0.5),
    ],
)
def test_detect_classifies_labeled_responses_correctly(
    model_config, context, response_text, expected_category, expected_confidence
):
    client = FakeLanguageModelClient(response=response_text)
    detector = IntentDetector(client, model_config)

    intent = detector.detect("some transcript", context)

    assert intent.category is expected_category
    assert intent.confidence == pytest.approx(expected_confidence)
    assert intent.raw_transcript == "some transcript"


def test_detect_degrades_to_unknown_on_llm_error(model_config, context):
    client = FakeLanguageModelClient(error=LlmError("connection failed"))
    detector = IntentDetector(client, model_config)

    intent = detector.detect("hello", context)

    assert intent.category is IntentCategory.UNKNOWN
    assert intent.confidence == 0.0


def test_detect_degrades_to_unknown_on_a_simulated_timeout(model_config, context):
    """From IntentDetector's perspective a timeout is indistinguishable
    from any other LlmError — OllamaClient is responsible for wrapping a
    raw timeout into LlmError (see test_llm_client.py); this confirms the
    detector's own degrade path handles it identically."""
    client = FakeLanguageModelClient(error=LlmError("Ollama generate() timed out"))
    detector = IntentDetector(client, model_config)

    intent = detector.detect("hello", context)

    assert intent.category is IntentCategory.UNKNOWN
    assert intent.confidence == 0.0


def test_detect_never_raises_for_an_empty_transcript(model_config, context):
    client = FakeLanguageModelClient(response="should never be reached")
    detector = IntentDetector(client, model_config)

    intent = detector.detect("", context)

    assert intent.category is IntentCategory.UNKNOWN
    assert intent.confidence == 0.0
    assert client.calls == []


def test_detect_never_raises_for_a_whitespace_only_transcript(model_config, context):
    client = FakeLanguageModelClient(response="should never be reached")
    detector = IntentDetector(client, model_config)

    intent = detector.detect("   ", context)

    assert intent.category is IntentCategory.UNKNOWN
    assert client.calls == []


def test_detect_degrades_to_unknown_on_a_response_missing_category(model_config, context):
    client = FakeLanguageModelClient(response="I'm not sure what you mean.")
    detector = IntentDetector(client, model_config)

    intent = detector.detect("hello", context)

    assert intent.category is IntentCategory.UNKNOWN
    assert intent.confidence == 0.0


def test_detect_degrades_to_unknown_on_an_unrecognized_category_name(model_config, context):
    client = FakeLanguageModelClient(response="CATEGORY: BANANA\nCONFIDENCE: 0.8")
    detector = IntentDetector(client, model_config)

    intent = detector.detect("hello", context)

    assert intent.category is IntentCategory.UNKNOWN


def test_detect_defaults_confidence_to_zero_on_unparseable_confidence(model_config, context):
    client = FakeLanguageModelClient(response="CATEGORY: INFORMATIONAL\nCONFIDENCE: not-a-number")
    detector = IntentDetector(client, model_config)

    intent = detector.detect("hello", context)

    assert intent.category is IntentCategory.INFORMATIONAL
    assert intent.confidence == 0.0


@pytest.mark.parametrize(
    ("raw_confidence", "expected"),
    [("5", 1.0), ("-3", 0.0), ("1.5", 1.0)],
)
def test_detect_clamps_confidence_into_the_zero_to_one_range(
    model_config, context, raw_confidence, expected
):
    response = f"CATEGORY: INFORMATIONAL\nCONFIDENCE: {raw_confidence}"
    client = FakeLanguageModelClient(response=response)
    detector = IntentDetector(client, model_config)

    intent = detector.detect("hello", context)

    assert intent.confidence == pytest.approx(expected)


def test_detect_passes_the_configured_timeout(model_config, context):
    client = FakeLanguageModelClient(response="CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.5")
    detector = IntentDetector(client, model_config)

    detector.detect("hello", context)

    assert client.calls[0][1] == model_config.ollama_timeout_seconds


def test_detect_passes_a_real_stop_sequence(model_config, context):
    """0.4.3 latency fix: a real, measured finding (see decision/
    llm_client.py's LanguageModelClient docstring) — without a stop
    sequence, a real model reliably keeps generating well past the
    requested two-line format. Confirms detect() actually asks Ollama to
    stop, not just hopes the prompt's own wording is obeyed."""
    client = FakeLanguageModelClient(response="CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.5")
    detector = IntentDetector(client, model_config)

    detector.detect("hello", context)

    assert client.calls[0][2] == ["\n\n"]


def test_health_check_false_before_start(model_config):
    detector = IntentDetector(FakeLanguageModelClient(), model_config)

    assert detector.health_check() is False


def test_start_is_healthy_when_client_has_no_reachability_capability(model_config):
    detector = IntentDetector(FakeLanguageModelClient(), model_config)

    detector.start()

    assert detector.health_check() is True


def test_start_is_healthy_when_client_reports_reachable(model_config):
    detector = IntentDetector(FakeReachabilityAwareClient(reachable=True), model_config)

    detector.start()

    assert detector.health_check() is True


def test_start_is_degraded_when_client_reports_unreachable(model_config):
    detector = IntentDetector(FakeReachabilityAwareClient(reachable=False), model_config)

    detector.start()

    assert detector.health_check() is False


def test_health_check_recovers_after_a_successful_detect_following_a_degraded_start(
    model_config, context
):
    client = FakeReachabilityAwareClient(
        reachable=False, response="CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.5"
    )
    detector = IntentDetector(client, model_config)
    detector.start()
    assert detector.health_check() is False

    detector.detect("hello", context)

    assert detector.health_check() is True


def test_health_check_goes_false_after_a_detect_failure(model_config, context):
    client = FakeReachabilityAwareClient(reachable=True, error=LlmError("boom"))
    detector = IntentDetector(client, model_config)
    detector.start()
    assert detector.health_check() is True

    detector.detect("hello", context)

    assert detector.health_check() is False


def test_stop_does_not_raise(model_config):
    detector = IntentDetector(FakeLanguageModelClient(), model_config)
    detector.start()

    detector.stop()
