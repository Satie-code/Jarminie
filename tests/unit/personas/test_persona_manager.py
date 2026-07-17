"""Unit tests for personas.persona_manager.

Uses real JarvisPersona/MiniePersona instances (both are simple, hardware-
free value-and-template objects — no need for fakes) throughout.
"""

import pytest

from config.schema import VoiceConfig
from personas.jarvis import JarvisPersona
from personas.minie import MiniePersona
from personas.persona_manager import PersonaManager, SwitchReason


@pytest.fixture
def voice_config():
    return VoiceConfig()


@pytest.fixture
def manager(voice_config):
    persona_manager = PersonaManager(
        JarvisPersona(voice_config), MiniePersona(voice_config), voice_config
    )
    persona_manager.start()
    return persona_manager


def test_starts_with_jarvis_active_by_default(manager):
    assert manager.active_persona().name == "jarvis"


def test_health_check_true_after_start(manager):
    assert manager.health_check() is True


def test_health_check_false_before_start(voice_config):
    persona_manager = PersonaManager(
        JarvisPersona(voice_config), MiniePersona(voice_config), voice_config
    )

    assert persona_manager.health_check() is False


def test_select_explicit_switches_active_persona_and_voice(manager, voice_config):
    switched = manager.select("minie", SwitchReason.EXPLICIT_SELECTION)

    assert switched is True
    assert manager.active_persona().name == "minie"
    assert manager.active_persona().voice_id == voice_config.minie_voice_id


def test_select_equal_priority_reselection_succeeds(manager):
    manager.select("minie", SwitchReason.EXPLICIT_SELECTION)

    switched = manager.select("jarvis", SwitchReason.EXPLICIT_SELECTION)

    assert switched is True
    assert manager.active_persona().name == "jarvis"


def test_select_higher_priority_overrides_lower(manager):
    manager.select("minie", SwitchReason.CONTEXT_DETECTION)

    switched = manager.select("jarvis", SwitchReason.EXPLICIT_SELECTION)

    assert switched is True
    assert manager.active_persona().name == "jarvis"


def test_select_lower_priority_refused_and_logged(manager, caplog):
    manager.select("minie", SwitchReason.EXPLICIT_SELECTION)

    with caplog.at_level("INFO"):
        switched = manager.select("jarvis", SwitchReason.CONTEXT_DETECTION)

    assert switched is False
    assert manager.active_persona().name == "minie"
    assert "refused" in caplog.text.lower()


def test_context_detection_cannot_override_explicit_selection(manager):
    """This sprint's core Acceptance Criterion: a CONTEXT_DETECTION match
    must never displace a persona made active via EXPLICIT_SELECTION."""
    manager.select("jarvis", SwitchReason.EXPLICIT_SELECTION)

    switched = manager.select("minie", SwitchReason.CONTEXT_DETECTION)

    assert switched is False
    assert manager.active_persona().name == "jarvis"


def test_select_unknown_persona_name_is_refused(manager):
    switched = manager.select("nonexistent", SwitchReason.EXPLICIT_SELECTION)

    assert switched is False
    assert manager.active_persona().name == "jarvis"


def test_resume_previous_restores_prior_persona_after_interruption(manager):
    manager.select("minie", SwitchReason.EXPLICIT_SELECTION)

    # No real emergency trigger exists yet in Level 2 (Sprint 3.10) — this
    # sprint's own Acceptance Criteria call for verifying resume_previous()
    # "with a fake higher-priority interruption," so CRITICAL_EMERGENCY is
    # used here purely as a priority-ordering stand-in.
    manager.select("jarvis", SwitchReason.CRITICAL_EMERGENCY)
    assert manager.active_persona().name == "jarvis"

    manager.resume_previous()

    assert manager.active_persona().name == "minie"


def test_resume_previous_is_a_no_op_when_nothing_to_resume(manager):
    manager.resume_previous()

    assert manager.active_persona().name == "jarvis"


def test_resume_previous_only_restores_one_level(manager):
    manager.select("minie", SwitchReason.EXPLICIT_SELECTION)
    manager.select("jarvis", SwitchReason.CRITICAL_EMERGENCY)
    manager.resume_previous()
    assert manager.active_persona().name == "minie"

    manager.resume_previous()  # nothing left recorded to resume

    assert manager.active_persona().name == "minie"


def test_detect_explicit_selection_matches_case_insensitively(manager):
    assert manager.detect_explicit_selection("Hey, can you Talk To Minie please?") == "minie"
    assert manager.detect_explicit_selection("switch to JARVIS now") == "jarvis"


def test_detect_explicit_selection_returns_none_for_unrelated_text(manager):
    assert manager.detect_explicit_selection("what's the weather like today") is None


def test_detect_explicit_selection_matches_common_minie_mishearings(manager):
    """Post-release fix: real end-to-end testing showed Whisper
    transcribing "talk to minie" as "talk to my knee"."""
    assert manager.detect_explicit_selection("talk to my knee please") == "minie"
    assert manager.detect_explicit_selection("switch to minnie") == "minie"


def test_detect_context_heuristic_matches_minie_keywords(manager):
    assert manager.detect_context_heuristic("I'm feeling really stressed today") == "minie"


def test_detect_context_heuristic_matches_jarvis_keywords(manager):
    assert manager.detect_context_heuristic("can you check the project deadline") == "jarvis"


def test_detect_context_heuristic_returns_none_otherwise(manager):
    assert manager.detect_context_heuristic("the sky is blue") is None


def test_health_check_false_when_zero_flags_active(manager):
    manager._active_flags["jarvis"] = False  # deliberately corrupt internal state

    assert manager.health_check() is False


def test_health_check_false_when_two_flags_active(manager):
    manager._active_flags["minie"] = True  # deliberately corrupt internal state

    assert manager.health_check() is False


def test_exactly_one_persona_active_across_a_sequence_of_operations(manager):
    """No code path can leave zero or two active — checked after each step
    of a realistic sequence of selects/refusals/resumes."""
    steps = [
        lambda: manager.select("minie", SwitchReason.CONTEXT_DETECTION),
        lambda: manager.select("jarvis", SwitchReason.EXPLICIT_SELECTION),
        lambda: manager.select("minie", SwitchReason.CONTEXT_DETECTION),  # refused
        lambda: manager.select("jarvis", SwitchReason.CRITICAL_EMERGENCY),
        manager.resume_previous,
        manager.resume_previous,  # no-op
    ]
    for step in steps:
        step()
        assert manager.health_check() is True


def test_compose_reply_safely_returns_the_real_reply(manager, conversation_context_factory):
    context = conversation_context_factory()

    reply = manager.compose_reply_safely("hello there", context)

    assert "hello there" in reply


def test_compose_reply_safely_falls_back_when_the_persona_raises(
    manager, conversation_context_factory
):
    """Sprint 2.13 hardening (scenario e): a bug in Persona.compose_reply()
    must never propagate out and abort the caller's turn."""

    class _BrokenPersona:
        name = "jarvis"
        voice_id = "p340"

        def compose_reply(self, transcript, context):
            raise RuntimeError("persona logic exploded")

        def describe(self):
            return "Broken — for testing"

    manager._personas["jarvis"] = _BrokenPersona()
    context = conversation_context_factory()

    reply = manager.compose_reply_safely("hello there", context)

    assert reply  # a non-empty fallback, not a raised exception
    assert "hello there" not in reply
