"""Unit tests for personas.jarvis and personas.base's ABC enforcement."""

from dataclasses import replace

import pytest

from config.schema import EmotionConfig, VoiceConfig
from decision.authority import AuthorityLevel
from emotion.state_manager import EmotionalState
from memory.models import MemoryRecord, MemoryType
from memory.retrieval_engine import RetrievedMemory
from personas.base import Persona, ToneVariant
from personas.jarvis import JarvisPersona, _select_tone_variant


def test_persona_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Persona()


def test_voice_id_reflects_a_non_default_configured_value():
    persona = JarvisPersona(VoiceConfig(jarvis_voice_id="p999"))

    assert persona.voice_id == "p999"


def test_voice_id_reflects_the_default_configured_value():
    persona = JarvisPersona(VoiceConfig())

    assert persona.voice_id == VoiceConfig().jarvis_voice_id


def test_name_is_jarvis():
    persona = JarvisPersona(VoiceConfig())

    assert persona.name == "jarvis"


def test_compose_reply_handles_a_normal_transcript(conversation_context_factory):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("what's the weather today", context, None)

    assert "what's the weather today" in reply


def test_compose_reply_handles_an_empty_transcript(conversation_context_factory):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("", context, None)

    assert reply


def test_compose_reply_handles_a_whitespace_only_transcript(conversation_context_factory):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("   ", context, None)

    assert reply


def test_compose_reply_handles_a_very_long_transcript(conversation_context_factory):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    long_transcript = "word " * 5000

    reply = persona.compose_reply(long_transcript, context, None)

    assert reply


def test_describe_returns_a_non_empty_persona_identifying_string():
    persona = JarvisPersona(VoiceConfig())

    description = persona.describe()

    assert description
    assert "jarvis" in description.lower()


# --- decision_trace-informed replies (Sprint 3.12) ---------------------------


def test_compose_reply_with_none_trace_matches_the_level_2_placeholder(
    conversation_context_factory,
):
    """decision_trace=None must fall back to exactly the prior Level 2
    templated acknowledgement — the Fail Gracefully path for when the
    Decision Engine pipeline itself is unavailable."""
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("fix the bug", context, None)

    assert reply == 'Understood. You said: "fix the bug".'


def test_compose_reply_with_a_trace_but_no_memories_omits_a_memory_clause(
    conversation_context_factory, decision_trace_factory
):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    trace = decision_trace_factory(authority_level=AuthorityLevel.INFORM, retrieved_memories=[])

    reply = persona.compose_reply("fix the bug", context, trace)

    assert reply == 'Understood. You said: "fix the bug".'


def test_compose_reply_measurably_differs_when_a_matching_memory_exists(
    conversation_context_factory, decision_trace_factory
):
    """Acceptance criterion (sprint_3_12.md): a reply must measurably
    differ from the Level 2 placeholder when a matching stored memory
    exists — proving the wiring is real, not just present."""
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    memory = RetrievedMemory(
        record=MemoryRecord(memory_type=MemoryType.JARVIS, content="the deadline is Friday"),
        similarity_score=0.8,
        confidence_score=70.0,
        combined_rank_score=0.76,
        retrieval_reason="80% similar - Long-term confidence (70/100)",
    )
    trace = decision_trace_factory(retrieved_memories=[memory])

    reply = persona.compose_reply("fix the bug", context, trace)

    assert reply != 'Understood. You said: "fix the bug".'
    assert "the deadline is Friday" in reply


def test_compose_reply_uses_recommend_prefix_for_recommend_authority(
    conversation_context_factory, decision_trace_factory
):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    trace = decision_trace_factory(authority_level=AuthorityLevel.RECOMMEND)

    reply = persona.compose_reply("fix the bug", context, trace)

    assert reply.startswith("Here's my recommendation: ")


def test_compose_reply_uses_emergency_assist_prefix(
    conversation_context_factory, decision_trace_factory
):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    trace = decision_trace_factory(authority_level=AuthorityLevel.EMERGENCY_ASSIST)

    reply = persona.compose_reply("help", context, trace)

    assert reply.startswith("I'm authorized to assist directly: ")


def test_compose_reply_empty_transcript_ignores_decision_trace(
    conversation_context_factory, decision_trace_factory
):
    """Even with a real trace present, an empty transcript must still
    return the standard empty-transcript reply — never raises, never
    fabricates a reply to nothing."""
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    trace = decision_trace_factory(authority_level=AuthorityLevel.RECOMMEND)

    reply = persona.compose_reply("", context, trace)

    assert reply == "I didn't catch anything that time. Could you repeat that?"


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
    low_mood = replace(EmotionalState(), mood=-60.0)

    assert _select_tone_variant(low_mood, _DEFAULT_EMOTION_CONFIG) is ToneVariant.ENCOURAGING


def test_select_tone_variant_is_encouraging_for_low_comfort():
    low_comfort = replace(EmotionalState(), comfort=10.0)

    assert _select_tone_variant(low_comfort, _DEFAULT_EMOTION_CONFIG) is ToneVariant.ENCOURAGING


def test_select_tone_variant_prefers_concise_when_stress_and_low_mood_both_present():
    """High stress is checked first — matches this sprint's own "concise
    phrasing when stress is high" framing taking precedence."""
    both = replace(EmotionalState(), stress=95.0, mood=-80.0)

    assert _select_tone_variant(both, _DEFAULT_EMOTION_CONFIG) is ToneVariant.CONCISE


def test_select_tone_variant_thresholds_are_genuinely_config_driven():
    """Proves the thresholds are real config reads, not hardcoded —
    03_Engineering_Standards.md's "no hardcoded... thresholds" rule. A
    mildly-elevated stress reading that stays NEUTRAL under the default
    config selects CONCISE once config lowers the threshold below it."""
    mild_stress = replace(EmotionalState(), stress=60.0)
    lower_threshold_config = replace(_DEFAULT_EMOTION_CONFIG, tone_high_stress_threshold=50.0)

    assert _select_tone_variant(mild_stress, _DEFAULT_EMOTION_CONFIG) is ToneVariant.NEUTRAL
    assert _select_tone_variant(mild_stress, lower_threshold_config) is ToneVariant.CONCISE


def test_compose_reply_emotional_state_none_matches_pre_sprint_5_4_output(
    conversation_context_factory,
):
    """Regression safety (Acceptance Criteria): emotional_state=None must
    behave identically to calling compose_reply() without the parameter
    at all."""
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()

    with_default = persona.compose_reply("fix the bug", context, None)
    with_explicit_none = persona.compose_reply("fix the bug", context, None, None)

    assert with_default == with_explicit_none == 'Understood. You said: "fix the bug".'


def test_compose_reply_high_stress_produces_a_shorter_reply(conversation_context_factory):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    high_stress = replace(EmotionalState(), stress=90.0)

    reply = persona.compose_reply("fix the bug", context, None, high_stress)

    assert reply == 'Understood: "fix the bug".'


def test_compose_reply_low_comfort_produces_an_encouraging_reply(conversation_context_factory):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    low_comfort = replace(EmotionalState(), comfort=10.0)

    reply = persona.compose_reply("fix the bug", context, None, low_comfort)

    assert reply == 'I hear you. You said: "fix the bug" — let\'s work through it together.'


def test_compose_reply_tone_variant_composes_with_authority_prefix(
    conversation_context_factory, decision_trace_factory
):
    """Tone variant and authority-driven prefix are orthogonal — both
    apply together, neither one silently overridden by the other."""
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    trace = decision_trace_factory(authority_level=AuthorityLevel.RECOMMEND)
    high_stress = replace(EmotionalState(), stress=90.0)

    reply = persona.compose_reply("fix the bug", context, trace, high_stress)

    assert reply == 'Here\'s my recommendation: Understood: "fix the bug".'


def test_compose_reply_never_raises_with_an_emotional_state_and_no_trace(
    conversation_context_factory,
):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("", context, None, EmotionalState())

    assert reply == "I didn't catch anything that time. Could you repeat that?"
