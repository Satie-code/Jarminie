"""Unit tests for personas.jarvis and personas.base's ABC enforcement."""

import pytest

from config.schema import VoiceConfig
from personas.base import Persona
from personas.jarvis import JarvisPersona


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

    reply = persona.compose_reply("what's the weather today", context)

    assert "what's the weather today" in reply


def test_compose_reply_handles_an_empty_transcript(conversation_context_factory):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("", context)

    assert reply


def test_compose_reply_handles_a_whitespace_only_transcript(conversation_context_factory):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()

    reply = persona.compose_reply("   ", context)

    assert reply


def test_compose_reply_handles_a_very_long_transcript(conversation_context_factory):
    persona = JarvisPersona(VoiceConfig())
    context = conversation_context_factory()
    long_transcript = "word " * 5000

    reply = persona.compose_reply(long_transcript, context)

    assert reply


def test_describe_returns_a_non_empty_persona_identifying_string():
    persona = JarvisPersona(VoiceConfig())

    description = persona.describe()

    assert description
    assert "jarvis" in description.lower()
