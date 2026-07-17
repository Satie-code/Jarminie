"""Unit tests for voice.pipeline.

Uses MagicMock for CommunicationPipeline's collaborators — this file
tests the pipeline's own wiring/orchestration logic (call sequencing,
argument passing, exception containment), not any real collaborator's
behavior, which is already covered by each module's own test file. See
tests/integration/test_communication_pipeline.py for the real,
non-mocked end-to-end exercise.
"""

from unittest.mock import MagicMock

import pytest

from personas.persona_manager import SwitchReason
from voice.pipeline import CallbackRelay, CommunicationPipeline
from voice.session_manager import SessionEndReason


@pytest.fixture
def collaborators():
    persona = MagicMock()
    persona.name = "jarvis"
    persona.voice_id = "p340"

    persona_manager = MagicMock()
    persona_manager.active_persona.return_value = persona
    persona_manager.detect_explicit_selection.return_value = None
    persona_manager.detect_context_heuristic.return_value = None
    persona_manager.compose_reply_safely.return_value = "a reply"

    context = MagicMock()
    context_manager = MagicMock()
    context_manager.current_context.return_value = context

    return {
        "mic": MagicMock(),
        "wake_word_detector": MagicMock(),
        "session_manager": MagicMock(),
        "quiet_mode_controller": MagicMock(),
        "conversation_store": MagicMock(),
        "context_manager": context_manager,
        "persona_manager": persona_manager,
        "turn_complete_relay": CallbackRelay(),
        "session_ended_relay": CallbackRelay(),
        "persona": persona,
        "context": context,
    }


@pytest.fixture
def pipeline(collaborators):
    return CommunicationPipeline(
        mic=collaborators["mic"],
        wake_word_detector=collaborators["wake_word_detector"],
        session_manager=collaborators["session_manager"],
        quiet_mode_controller=collaborators["quiet_mode_controller"],
        conversation_store=collaborators["conversation_store"],
        context_manager=collaborators["context_manager"],
        persona_manager=collaborators["persona_manager"],
        turn_complete_relay=collaborators["turn_complete_relay"],
        session_ended_relay=collaborators["session_ended_relay"],
    )


def test_health_check_false_before_start(pipeline):
    assert pipeline.health_check() is False


def test_start_wires_both_relays_to_their_real_targets(pipeline, collaborators):
    pipeline.start()

    assert collaborators["turn_complete_relay"].target == pipeline._handle_turn_complete
    assert (
        collaborators["session_ended_relay"].target
        == collaborators["quiet_mode_controller"]._on_session_ended
    )
    assert pipeline.health_check() is True


def test_stop_disconnects_both_relays(pipeline, collaborators):
    pipeline.start()

    pipeline.stop()

    assert collaborators["turn_complete_relay"].target is None
    assert collaborators["session_ended_relay"].target is None
    assert pipeline.health_check() is False


def test_handle_turn_complete_happy_path(pipeline, collaborators):
    pipeline._handle_turn_complete("hello there", "session-1")

    collaborators["persona_manager"].detect_explicit_selection.assert_called_once_with(
        "hello there"
    )
    collaborators["context_manager"].current_context.assert_called_once_with(
        "session-1", "jarvis"
    )
    collaborators["persona_manager"].compose_reply_safely.assert_called_once_with(
        "hello there", collaborators["context"]
    )
    collaborators["conversation_store"].record_turn.assert_called_once()
    turn = collaborators["conversation_store"].record_turn.call_args[0][0]
    assert turn.session_id == "session-1"
    assert turn.persona_name == "jarvis"
    assert turn.user_text == "hello there"
    assert turn.response_text == "a reply"
    collaborators["session_manager"].speak_reply.assert_called_once_with("a reply", "p340")


def test_handle_turn_complete_selects_on_an_explicit_match(pipeline, collaborators):
    collaborators["persona_manager"].detect_explicit_selection.return_value = "minie"

    pipeline._handle_turn_complete("talk to minie", "session-1")

    collaborators["persona_manager"].select.assert_called_once_with(
        "minie", SwitchReason.EXPLICIT_SELECTION
    )
    collaborators["persona_manager"].detect_context_heuristic.assert_not_called()


def test_handle_turn_complete_falls_back_to_the_context_heuristic(pipeline, collaborators):
    collaborators["persona_manager"].detect_explicit_selection.return_value = None
    collaborators["persona_manager"].detect_context_heuristic.return_value = "minie"

    pipeline._handle_turn_complete("i'm feeling tired", "session-1")

    collaborators["persona_manager"].select.assert_called_once_with(
        "minie", SwitchReason.CONTEXT_DETECTION
    )


def test_handle_turn_complete_no_match_does_not_call_select(pipeline, collaborators):
    pipeline._handle_turn_complete("what time is it", "session-1")

    collaborators["persona_manager"].select.assert_not_called()


def test_handle_turn_complete_contains_an_unexpected_failure_and_ends_the_session(
    pipeline, collaborators
):
    """Sprint 2.13 hardening: a real gap this sprint found — before this
    fix, an unexpected exception anywhere in this method (this test
    forces one from record_turn) silently killed the session's own
    background thread instead of ending the session gracefully."""
    collaborators["conversation_store"].record_turn.side_effect = RuntimeError("disk exploded")

    pipeline._handle_turn_complete("hello there", "session-1")  # must not raise

    collaborators["session_manager"].end_session.assert_called_once_with(SessionEndReason.ERROR)


def test_handle_turn_complete_contains_an_unexpected_speak_reply_failure(pipeline, collaborators):
    """Distinct from VoiceSessionManager's own internal TextToSpeechError
    handling — this is the outer defense-in-depth catch for anything
    unexpected escaping speak_reply() itself."""
    collaborators["session_manager"].speak_reply.side_effect = RuntimeError("unexpected tts bug")

    pipeline._handle_turn_complete("hello there", "session-1")  # must not raise

    collaborators["session_manager"].end_session.assert_called_once_with(SessionEndReason.ERROR)
