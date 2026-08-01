"""Unit tests for decision.response_generator.

Uses only a local, in-file fake LanguageModelClient — no real Ollama
call is made, same convention as test_intent_detector.py/
test_context_analyzer.py/test_summarizer.py. Real-model verification is
a separately-gated, opt-in concern (this project's established
precedent, e.g. tests/system/test_level3_real_model_verification.py),
not this file's job.
"""

from datetime import UTC, datetime

import pytest

from config.schema import ModelConfig
from decision.authority import AuthorityLevel, DecisionTrace, EngineSelection
from decision.context_analyzer import ContextAnalysis, SentimentHint
from decision.llm_client import LlmError
from decision.models import Intent, IntentCategory
from decision.priority_queue import PriorityLevel
from decision.response_generator import ResponseGenerator
from memory.models import MemoryRecord, MemoryType
from memory.retrieval_engine import RetrievedMemory
from voice.context_manager import ConversationContext
from voice.conversation_store import ConversationTurn


class FakeLanguageModelClient:
    """Implements ONLY the LanguageModelClient Protocol (no
    is_reachable) — same convention as every other real caller's own
    fake in this codebase."""

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


def make_context_analysis(**overrides) -> ContextAnalysis:
    defaults = dict(
        primary_topic="",
        mentioned_entities=[],
        references_past_memory=False,
        suggested_persona=None,
        sentiment_hint=SentimentHint.NEUTRAL,
        analyzed_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return ContextAnalysis(**defaults)


def make_retrieved_memory(content: str) -> RetrievedMemory:
    record = MemoryRecord(memory_type=MemoryType.SHARED, content=content)
    return RetrievedMemory(
        record=record,
        similarity_score=0.9,
        confidence_score=50.0,
        combined_rank_score=0.8,
        retrieval_reason="test retrieval",
    )


def make_decision_trace(**overrides) -> DecisionTrace:
    defaults = dict(
        intent=make_intent(),
        context_analysis=make_context_analysis(),
        retrieved_memories=[],
        priority_level=PriorityLevel.GENERAL_SUGGESTION,
        authority_level=AuthorityLevel.INFORM,
        selected_engine=EngineSelection.CONVERSATIONAL_RESPONSE,
        reasoning_text="test reasoning",
        decided_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return DecisionTrace(**defaults)


# --- happy path -----------------------------------------------------------------------


def test_generate_returns_the_real_llm_response(model_config, context):
    fake = FakeLanguageModelClient(response="Paris is the capital of France.")
    generator = ResponseGenerator(fake, model_config)

    reply = generator.generate("what's the capital of France?", context, None, "jarvis")

    assert reply == "Paris is the capital of France."


def test_generate_strips_surrounding_whitespace_from_the_llm_response(model_config, context):
    fake = FakeLanguageModelClient(response="  Paris.  \n")
    generator = ResponseGenerator(fake, model_config)

    reply = generator.generate("what's the capital of France?", context, None, "jarvis")

    assert reply == "Paris."


def test_generate_uses_ollama_timeout_seconds_from_model_config(context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, ModelConfig(ollama_timeout_seconds=42.0))

    generator.generate("hello", context, None, "jarvis")

    assert fake.calls[0][1] == 42.0


def test_generate_does_not_pass_a_stop_sequence(model_config, context):
    """Deliberately unlike IntentDetector/ContextAnalyzer (0.4.3's own
    fix, decision/llm_client.py's LanguageModelClient docstring): a
    conversational reply is meant to be free-form natural language, not
    a fixed line format — a blank-line stop condition risks truncating
    a legitimate multi-sentence/paragraph answer, so this class passes
    no stop sequence at all (the LanguageModelClient default, None)."""
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    generator.generate("hello", context, None, "jarvis")

    assert fake.calls[0][2] is None


# --- prompt grounding: transcript / recent turns ---------------------------------------


def test_prompt_contains_the_transcript(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    generator.generate("what's the capital of France?", context, None, "jarvis")

    assert "what's the capital of France?" in fake.calls[0][0]


def test_prompt_contains_recent_turns(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    generator.generate("and tomorrow?", context, None, "jarvis")

    prompt = fake.calls[0][0]
    assert "what's the weather" in prompt
    assert "It's sunny." in prompt


def test_prompt_with_no_recent_turns_still_contains_the_transcript(model_config):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)
    now = datetime.now(UTC)
    empty_context = ConversationContext(
        session_id="session-1",
        active_persona_name="jarvis",
        recent_turns=[],
        session_started_at=now,
        last_activity_at=now,
    )

    generator.generate("a lonely question", empty_context, None, "jarvis")

    prompt = fake.calls[0][0]
    assert "a lonely question" in prompt
    assert "no prior turns" in prompt.lower()


# --- prompt grounding: persona tone -----------------------------------------------------


def test_prompt_uses_jarvis_tone(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    generator.generate("hello", context, None, "jarvis")

    assert "professional" in fake.calls[0][0].lower()


def test_prompt_uses_minie_tone(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    generator.generate("hello", context, None, "minie")

    assert "warm" in fake.calls[0][0].lower()


def test_prompt_falls_back_to_a_default_tone_for_an_unrecognized_persona_name(
    model_config, context
):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    generator.generate("hello", context, None, "someone_else")  # must not raise

    assert "helpful" in fake.calls[0][0].lower()


# --- prompt grounding: decision_trace (memories / authority) ---------------------------


def test_prompt_includes_retrieved_memory_content_when_present(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)
    trace = make_decision_trace(
        retrieved_memories=[make_retrieved_memory("The user's dog is named Max.")]
    )

    generator.generate("tell me about my dog", context, trace, "jarvis")

    assert "The user's dog is named Max." in fake.calls[0][0]


def test_prompt_omits_memory_block_when_no_memories_retrieved(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)
    trace = make_decision_trace(retrieved_memories=[])

    generator.generate("hello", context, trace, "jarvis")

    assert "Relevant things you remember" not in fake.calls[0][0]


@pytest.mark.parametrize(
    ("authority_level", "expected_phrase"),
    [
        (AuthorityLevel.INFORM, "plainly"),
        (AuthorityLevel.RECOMMEND, "recommendation"),
        (AuthorityLevel.EMERGENCY_ASSIST, "authorized"),
    ],
)
def test_prompt_includes_authority_guidance(
    model_config, context, authority_level, expected_phrase
):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)
    trace = make_decision_trace(authority_level=authority_level)

    generator.generate("help me with this", context, trace, "jarvis")

    assert expected_phrase in fake.calls[0][0].lower()


def test_prompt_tolerates_a_missing_decision_trace(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    reply = generator.generate("hello", context, None, "jarvis")  # must not raise

    assert reply == "ok"
    assert "Relevant things you remember" not in fake.calls[0][0]


# --- prompt instructs answer-or-clarify, never fabricate --------------------------------


def test_prompt_instructs_asking_a_clarifying_question_when_ambiguous(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    generator.generate("do that thing", context, None, "jarvis")

    assert "clarifying question" in fake.calls[0][0].lower()


def test_prompt_instructs_never_inventing_facts(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    generator.generate("hello", context, None, "jarvis")

    assert "never invent" in fake.calls[0][0].lower()


def test_prompt_instructs_conciseness_for_a_spoken_reply(model_config, context):
    fake = FakeLanguageModelClient(response="ok")
    generator = ResponseGenerator(fake, model_config)

    generator.generate("hello", context, None, "jarvis")

    assert "concisely" in fake.calls[0][0].lower()


# --- failure propagation (no safe default of its own — see this module's docstring) -----


def test_generate_propagates_llm_error(model_config, context):
    fake = FakeLanguageModelClient(error=LlmError("ollama unreachable"))
    generator = ResponseGenerator(fake, model_config)

    with pytest.raises(LlmError):
        generator.generate("hello", context, None, "jarvis")
