"""Unit tests for reasoning.reasoning_engine.

Uses only a local, in-file fake LanguageModelClient — no real Ollama call
is made, the same convention as test_planning_engine.py/
test_intent_detector.py/test_context_analyzer.py. Parsing behavior
(_extract_conclusion/_parse_alternatives/_parse_confidence) is exercised
only through the public method contracts, never by importing the
underscore-prefixed helpers directly — matching test_planning_engine.py's
own established convention.
"""

from datetime import UTC, datetime

import pytest

from config.schema import ModelConfig, ReasoningConfig
from context.context_model import WorkingContext
from decision.llm_client import LlmError
from reasoning.reasoning_engine import ReasoningEngine
from voice.context_manager import ConversationContext
from voice.conversation_store import ConversationTurn


class FakeLanguageModelClient:
    """Implements ONLY the LanguageModelClient Protocol (no is_reachable)
    — same convention as every other real caller's own fake in this
    codebase."""

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


@pytest.fixture
def model_config() -> ModelConfig:
    return ModelConfig(ollama_timeout_seconds=5.0)


@pytest.fixture
def reasoning_config() -> ReasoningConfig:
    return ReasoningConfig(max_alternatives=2, reasoning_timeout_seconds=30.0)


def _working_context_with_conversation() -> WorkingContext:
    conversation = ConversationContext(
        session_id="s1",
        active_persona_name="jarvis",
        recent_turns=[
            ConversationTurn(
                session_id="s1",
                persona_name="jarvis",
                timestamp=datetime.now(UTC),
                user_text="Hi",
                response_text="Hello",
            )
        ],
        session_started_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
    )
    return WorkingContext(
        built_at=datetime.now(UTC),
        conversation=conversation,
        recent_memories=["memory-1"],
        recent_applications=[],
        upcoming_scheduled_items=["item-1", "item-2"],
        resource_status=None,
    )


_WHY_RESPONSE = "CONCLUSION: Because consistent practice builds real skill.\n"
_WHAT_IF_RESPONSE = "CONCLUSION: The deadline would likely be missed.\n"
_ALTERNATIVES_RESPONSE = (
    "CONCLUSION: Two real alternatives exist.\n"
    "ALTERNATIVE: Do it now | Faster, but skips validation\n"
    "ALTERNATIVE: Do it later | Safer, but delays the result\n"
)
_CONFIDENCE_RESPONSE = "CONCLUSION: The plan should succeed.\nCONFIDENCE: 0.8\n"


# --- explain_why ----------------------------------------------------------------------


def test_explain_why_returns_a_trace_with_why_question_type(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response=_WHY_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.explain_why("Practice daily")

    assert trace.question_type == "why"
    assert trace.subject == "Practice daily"
    assert trace.conclusion == "Because consistent practice builds real skill."
    assert trace.alternatives == []


def test_explain_why_succeeds_with_no_working_context(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response=_WHY_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.explain_why("Practice daily", working_context=None)

    assert trace.conclusion


def test_explain_why_prompt_contains_the_subject(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response=_WHY_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    engine.explain_why("Learn to juggle")

    assert "Learn to juggle" in fake.calls[0][0]


def test_explain_why_prompt_includes_context_summary_when_given(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response=_WHY_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    engine.explain_why("Practice daily", working_context=_working_context_with_conversation())

    assert "Current context" in fake.calls[0][0]
    assert "recent turn" in fake.calls[0][0]


# --- what_if ----------------------------------------------------------------------------


def test_what_if_returns_a_trace_with_what_if_question_type(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response=_WHAT_IF_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.what_if("I skip this task")

    assert trace.question_type == "what_if"
    assert trace.subject == "I skip this task"
    assert trace.conclusion == "The deadline would likely be missed."


def test_what_if_succeeds_with_no_working_context(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response=_WHAT_IF_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.what_if("I skip this task", working_context=None)

    assert trace.conclusion


# --- alternatives -------------------------------------------------------------------------


def test_alternatives_returns_a_trace_with_alternatives_question_type(
    model_config, reasoning_config
):
    fake = FakeLanguageModelClient(response=_ALTERNATIVES_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.alternatives("Rewrite the module")

    assert trace.question_type == "alternatives"
    assert trace.conclusion == "Two real alternatives exist."
    assert len(trace.alternatives) == 2
    assert trace.alternatives[0].description == "Do it now"
    assert trace.alternatives[0].estimated_trade_off == "Faster, but skips validation"


def test_alternatives_succeeds_with_no_working_context(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response=_ALTERNATIVES_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.alternatives("Rewrite the module", working_context=None)

    assert trace.alternatives


def test_alternatives_never_exceeds_the_configured_max(model_config, reasoning_config):
    response = (
        "CONCLUSION: Several alternatives exist.\n"
        "ALTERNATIVE: One | trade-off one\n"
        "ALTERNATIVE: Two | trade-off two\n"
        "ALTERNATIVE: Three | trade-off three\n"  # reasoning_config.max_alternatives=2
    )
    fake = FakeLanguageModelClient(response=response)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.alternatives("Something with many options")

    assert len(trace.alternatives) == reasoning_config.max_alternatives


def test_alternatives_truncation_logs_a_warning(model_config, reasoning_config, caplog):
    response = (
        "CONCLUSION: Several alternatives exist.\n"
        "ALTERNATIVE: One | trade-off one\n"
        "ALTERNATIVE: Two | trade-off two\n"
        "ALTERNATIVE: Three | trade-off three\n"
    )
    fake = FakeLanguageModelClient(response=response)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    with caplog.at_level("WARNING"):
        engine.alternatives("Something with many options")

    assert "truncated" in caplog.text.lower()


# --- estimate_confidence -----------------------------------------------------------------


def test_estimate_confidence_returns_a_trace_with_confidence_question_type(
    model_config, reasoning_config
):
    fake = FakeLanguageModelClient(response=_CONFIDENCE_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.estimate_confidence("The plan will work")

    assert trace.question_type == "confidence"
    assert trace.conclusion == "The plan should succeed."
    assert trace.confidence == pytest.approx(0.8)


def test_estimate_confidence_succeeds_with_no_working_context(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response=_CONFIDENCE_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.estimate_confidence("The plan will work", working_context=None)

    assert 0.0 <= trace.confidence <= 1.0


def test_estimate_confidence_clamps_an_out_of_range_value(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response="CONCLUSION: Very sure.\nCONFIDENCE: 4.2\n")
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.estimate_confidence("Something")

    assert trace.confidence == 1.0


def test_estimate_confidence_clamps_a_negative_value(model_config, reasoning_config):
    fake = FakeLanguageModelClient(response="CONCLUSION: Not sure.\nCONFIDENCE: -0.3\n")
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    trace = engine.estimate_confidence("Something")

    assert trace.confidence == 0.0


def test_estimate_confidence_defaults_to_half_when_unparseable(
    model_config, reasoning_config, caplog
):
    fake = FakeLanguageModelClient(response="CONCLUSION: I am not sure how confident I am.\n")
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    with caplog.at_level("WARNING"):
        trace = engine.estimate_confidence("Something")

    assert trace.confidence == 0.5
    assert "confidence" in caplog.text.lower()


# --- failure propagation / call shape ----------------------------------------------------


@pytest.mark.parametrize(
    "method_name", ["explain_why", "what_if", "alternatives", "estimate_confidence"]
)
def test_all_four_methods_propagate_llm_error(model_config, reasoning_config, method_name):
    fake = FakeLanguageModelClient(error=LlmError("ollama unreachable"))
    engine = ReasoningEngine(fake, model_config, reasoning_config)
    method = getattr(engine, method_name)

    with pytest.raises(LlmError):
        method("Something")


def test_explain_why_uses_the_dedicated_reasoning_timeout_not_model_config(
    model_config, reasoning_config
):
    fake = FakeLanguageModelClient(response=_WHY_RESPONSE)
    engine = ReasoningEngine(fake, model_config, reasoning_config)

    engine.explain_why("Something")

    assert fake.calls[0][1] == reasoning_config.reasoning_timeout_seconds
    assert fake.calls[0][1] != model_config.ollama_timeout_seconds
