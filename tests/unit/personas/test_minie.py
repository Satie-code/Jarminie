"""Unit tests for personas.minie, plus a shared parametrized contract test
proving JarvisPersona and MiniePersona are interchangeable everywhere a
Persona is expected — this sprint's own Acceptance Criteria ("the concrete
proof that Persona's abstraction is sound").
"""

from dataclasses import replace

import pytest

from config.schema import EmotionConfig, VoiceConfig
from decision.authority import AuthorityLevel
from emotion.state_manager import EmotionalState
from memory.models import MemoryRecord, MemoryType
from memory.retrieval_engine import RetrievedMemory
from personas.base import Persona, ToneVariant
from personas.jarvis import JarvisPersona
from personas.jarvis import _select_tone_variant as _jarvis_select_tone_variant
from personas.minie import MiniePersona, _select_tone_variant


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


# --- tone-variant selection (Sprint 5.4) --------------------------------------

_DEFAULT_EMOTION_CONFIG = EmotionConfig()


def test_select_tone_variant_is_neutral_when_emotional_state_is_none():
    assert _select_tone_variant(None, _DEFAULT_EMOTION_CONFIG) is ToneVariant.NEUTRAL


def test_select_tone_variant_is_neutral_for_a_default_neutral_state():
    assert _select_tone_variant(EmotionalState(), _DEFAULT_EMOTION_CONFIG) is ToneVariant.NEUTRAL


def test_select_tone_variant_is_concise_for_high_stress():
    high_stress = replace(EmotionalState(), stress=90.0)

    assert _select_tone_variant(high_stress, _DEFAULT_EMOTION_CONFIG) is ToneVariant.CONCISE


def test_select_tone_variant_is_encouraging_for_low_mood():
    low_mood = replace(EmotionalState(), mood=-30.0)

    assert _select_tone_variant(low_mood, _DEFAULT_EMOTION_CONFIG) is ToneVariant.ENCOURAGING


def test_select_tone_variant_is_encouraging_for_low_comfort():
    low_comfort = replace(EmotionalState(), comfort=25.0)

    assert _select_tone_variant(low_comfort, _DEFAULT_EMOTION_CONFIG) is ToneVariant.ENCOURAGING


def test_minie_leans_into_encouraging_more_readily_than_jarvis():
    """Sprint 5.4: Minie's own thresholds are looser than Jarvis's — the
    same mildly-low reading selects ENCOURAGING for Minie but stays
    NEUTRAL for Jarvis, matching Minie's "primary beneficiary" framing."""
    mildly_low_comfort = replace(EmotionalState(), comfort=37.0)

    assert (
        _jarvis_select_tone_variant(mildly_low_comfort, _DEFAULT_EMOTION_CONFIG)
        is ToneVariant.NEUTRAL
    )
    assert (
        _select_tone_variant(mildly_low_comfort, _DEFAULT_EMOTION_CONFIG)
        is ToneVariant.ENCOURAGING
    )


def test_select_tone_variant_thresholds_are_genuinely_config_driven():
    """Same proof as test_jarvis.py's own equivalent — Minie's thresholds
    are real config reads too, not hardcoded."""
    mild_comfort_dip = replace(EmotionalState(), comfort=45.0)
    looser_threshold_config = replace(
        _DEFAULT_EMOTION_CONFIG, minie_tone_low_comfort_threshold=48.0
    )

    assert (
        _select_tone_variant(mild_comfort_dip, _DEFAULT_EMOTION_CONFIG) is ToneVariant.NEUTRAL
    )
    assert (
        _select_tone_variant(mild_comfort_dip, looser_threshold_config)
        is ToneVariant.ENCOURAGING
    )


def test_compose_reply_emotional_state_none_matches_pre_sprint_5_4_output(
    conversation_context_factory,
):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()

    with_default = persona.compose_reply("i'm feeling tired", context, None)
    with_explicit_none = persona.compose_reply("i'm feeling tired", context, None, None)

    assert (
        with_default
        == with_explicit_none
        == 'Got it — you said: "i\'m feeling tired". I\'m here if you need anything else.'
    )


def test_compose_reply_high_stress_produces_a_shorter_reply(conversation_context_factory):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()
    high_stress = replace(EmotionalState(), stress=90.0)

    reply = persona.compose_reply("i'm feeling tired", context, None, high_stress)

    assert reply == 'Got it: "i\'m feeling tired". Let\'s keep this simple for now.'


def test_compose_reply_low_mood_produces_an_encouraging_reply(conversation_context_factory):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()
    low_mood = replace(EmotionalState(), mood=-40.0)

    reply = persona.compose_reply("i'm feeling tired", context, None, low_mood)

    assert reply == (
        'That sounds like a lot. You said: "i\'m feeling tired" — I\'m right here with you.'
    )


def test_compose_reply_never_raises_with_an_emotional_state_and_no_trace(
    conversation_context_factory,
):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("", context, None, EmotionalState())

    assert reply == "Hmm, I didn't quite catch that. Mind saying it again?"


def test_compose_reply_never_raises_across_every_tone_variant_and_authority_level(
    conversation_context_factory, decision_trace_factory
):
    """Adversarial sweep (Acceptance Criteria): compose_reply() never
    raises regardless of emotional_state being None or populated, across
    both personas and every AuthorityLevel."""
    context = conversation_context_factory()
    states = [
        None,
        EmotionalState(),
        replace(EmotionalState(), stress=95.0),
        replace(EmotionalState(), mood=-90.0),
        replace(EmotionalState(), comfort=5.0),
    ]
    for persona_cls in (JarvisPersona, MiniePersona):
        persona = persona_cls(VoiceConfig())
        for authority_level in AuthorityLevel:
            trace = decision_trace_factory(authority_level=authority_level)
            for state in states:
                for trace_value in (None, trace):
                    reply = persona.compose_reply("test input", context, trace_value, state)
                    assert isinstance(reply, str) and reply
