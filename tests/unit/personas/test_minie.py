"""Unit tests for personas.minie, plus a shared parametrized contract test
proving JarvisPersona and MiniePersona are interchangeable everywhere a
Persona is expected — this sprint's own Acceptance Criteria ("the concrete
proof that Persona's abstraction is sound").
"""

import pytest

from config.schema import VoiceConfig
from decision.authority import AuthorityLevel
from memory.models import MemoryRecord, MemoryType
from memory.retrieval_engine import RetrievedMemory
from personas.base import Persona
from personas.jarvis import JarvisPersona
from personas.minie import MiniePersona


def test_voice_id_reflects_a_non_default_configured_value():
    persona = MiniePersona(VoiceConfig(minie_voice_id="p111"))

    assert persona.voice_id == "p111"


def test_voice_id_reflects_the_default_configured_value():
    persona = MiniePersona(VoiceConfig())

    assert persona.voice_id == VoiceConfig().minie_voice_id


def test_name_is_minie():
    persona = MiniePersona(VoiceConfig())

    assert persona.name == "minie"


def test_compose_reply_handles_a_normal_transcript(conversation_context_factory):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("i'm feeling a bit tired", context, None)

    assert "i'm feeling a bit tired" in reply


def test_compose_reply_handles_an_empty_transcript(conversation_context_factory):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("", context, None)

    assert reply


def test_compose_reply_handles_a_whitespace_only_transcript(conversation_context_factory):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("   ", context, None)

    assert reply


def test_compose_reply_handles_a_very_long_transcript(conversation_context_factory):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()
    long_transcript = "word " * 5000

    reply = persona.compose_reply(long_transcript, context, None)

    assert reply


def test_describe_returns_a_non_empty_persona_identifying_string():
    persona = MiniePersona(VoiceConfig())

    description = persona.describe()

    assert description
    assert "minie" in description.lower()


def test_minie_reply_tone_is_textually_distinct_from_jarvis(conversation_context_factory):
    context = conversation_context_factory()

    jarvis_reply = JarvisPersona(VoiceConfig()).compose_reply("hello", context, None)
    minie_reply = MiniePersona(VoiceConfig()).compose_reply("hello", context, None)

    assert jarvis_reply != minie_reply


_PERSONA_CLASSES = [JarvisPersona, MiniePersona]


@pytest.mark.parametrize("persona_cls", _PERSONA_CLASSES, ids=["jarvis", "minie"])
def test_persona_contract_shape_is_identical_across_implementations(
    persona_cls, conversation_context_factory
):
    """Runs the same assertions against both concrete personas — the
    proof that Persona's abstraction is sound and that PersonaManager
    (2.11) can depend on Persona alone, never a concrete type."""
    persona = persona_cls(VoiceConfig())
    context = conversation_context_factory()

    assert isinstance(persona, Persona)
    assert isinstance(persona.name, str) and persona.name
    assert isinstance(persona.voice_id, str) and persona.voice_id
    assert isinstance(persona.describe(), str) and persona.describe()
    assert isinstance(persona.compose_reply("hello there", context, None), str)
    assert persona.compose_reply("", context, None)  # never raises, never empty


# --- decision_trace-informed replies (Sprint 3.12) ---------------------------


def test_compose_reply_with_none_trace_matches_the_level_2_placeholder(
    conversation_context_factory,
):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("i'm feeling tired", context, None)

    assert reply == (
        'Got it — you said: "i\'m feeling tired". I\'m here if you need anything else.'
    )


def test_compose_reply_measurably_differs_when_a_matching_memory_exists(
    conversation_context_factory, decision_trace_factory
):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()
    placeholder = persona.compose_reply("how am i doing", context, None)
    memory = RetrievedMemory(
        record=MemoryRecord(memory_type=MemoryType.MINIE, content="you mentioned feeling tired"),
        similarity_score=0.8,
        confidence_score=60.0,
        combined_rank_score=0.7,
        retrieval_reason="80% similar - Monthly-review confidence (60/100)",
    )
    trace = decision_trace_factory(retrieved_memories=[memory])

    reply = persona.compose_reply("how am i doing", context, trace)

    assert reply != placeholder
    assert "you mentioned feeling tired" in reply


def test_compose_reply_uses_recommend_prefix_for_recommend_authority(
    conversation_context_factory, decision_trace_factory
):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()
    trace = decision_trace_factory(authority_level=AuthorityLevel.RECOMMEND)

    reply = persona.compose_reply("what should i do", context, trace)

    assert reply.startswith("Here's what I'd gently suggest: ")


def test_compose_reply_uses_emergency_assist_prefix(
    conversation_context_factory, decision_trace_factory
):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()
    trace = decision_trace_factory(authority_level=AuthorityLevel.EMERGENCY_ASSIST)

    reply = persona.compose_reply("help", context, trace)

    assert reply.startswith("I can help with this directly: ")
