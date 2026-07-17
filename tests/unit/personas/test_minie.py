"""Unit tests for personas.minie, plus a shared parametrized contract test
proving JarvisPersona and MiniePersona are interchangeable everywhere a
Persona is expected — this sprint's own Acceptance Criteria ("the concrete
proof that Persona's abstraction is sound").
"""

import pytest

from config.schema import VoiceConfig
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

    reply = persona.compose_reply("i'm feeling a bit tired", context)

    assert "i'm feeling a bit tired" in reply


def test_compose_reply_handles_an_empty_transcript(conversation_context_factory):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("", context)

    assert reply


def test_compose_reply_handles_a_whitespace_only_transcript(conversation_context_factory):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("   ", context)

    assert reply


def test_compose_reply_handles_a_very_long_transcript(conversation_context_factory):
    persona = MiniePersona(VoiceConfig())
    context = conversation_context_factory()
    long_transcript = "word " * 5000

    reply = persona.compose_reply(long_transcript, context)

    assert reply


def test_describe_returns_a_non_empty_persona_identifying_string():
    persona = MiniePersona(VoiceConfig())

    description = persona.describe()

    assert description
    assert "minie" in description.lower()


def test_minie_reply_tone_is_textually_distinct_from_jarvis(conversation_context_factory):
    context = conversation_context_factory()

    jarvis_reply = JarvisPersona(VoiceConfig()).compose_reply("hello", context)
    minie_reply = MiniePersona(VoiceConfig()).compose_reply("hello", context)

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
    assert isinstance(persona.compose_reply("hello there", context), str)
    assert persona.compose_reply("", context)  # never raises, never empty
