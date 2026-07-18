"""Unit tests for voice.pipeline.

Uses MagicMock for CommunicationPipeline's collaborators — this file
tests the pipeline's own wiring/orchestration logic (call sequencing,
argument passing, exception containment), not any real collaborator's
behavior, which is already covered by each module's own test file. See
tests/integration/test_communication_pipeline.py for the real,
non-mocked end-to-end exercise, and
tests/integration/test_decision_engine_integration.py for the Sprint
3.12 Decision Engine wiring specifically.
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
    persona_manager.compose_reply_safely.return_value = "a reply"

    context = MagicMock()
    context.active_persona_name = "jarvis"
    context_manager = MagicMock()
    context_manager.current_context.return_value = context

    intent = MagicMock(name="intent")
    intent_detector = MagicMock()
    intent_detector.detect.return_value = intent

    context_analysis = MagicMock(name="context_analysis")
    context_analysis.primary_topic = "some topic"
    context_analysis.suggested_persona = None
    context_analyzer = MagicMock()
    context_analyzer.analyze.return_value = context_analysis

    memory_retrieval_engine = MagicMock()
    memory_retrieval_engine.retrieve.return_value = []

    priority_level = MagicMock(name="priority_level")
    priority_queue_manager = MagicMock()
    priority_queue_manager.classify.return_value = priority_level

    decision_trace = MagicMock(name="decision_trace")
    decision_trace.context_analysis = context_analysis
    authority_evaluator = MagicMock()
    authority_evaluator.evaluate.return_value = decision_trace

    short_term_memory = MagicMock()
    short_term_memory.promote_from_turn.return_value = None

    confidence_scorer = MagicMock()
    confidence_scorer.detect_override_phrase.return_value = False

    memory_lifecycle_manager = MagicMock()

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
        "intent_detector": intent_detector,
        "context_analyzer": context_analyzer,
        "memory_retrieval_engine": memory_retrieval_engine,
        "priority_queue_manager": priority_queue_manager,
        "authority_evaluator": authority_evaluator,
        "short_term_memory": short_term_memory,
        "confidence_scorer": confidence_scorer,
        "memory_lifecycle_manager": memory_lifecycle_manager,
        "persona": persona,
        "context": context,
        "intent": intent,
        "context_analysis": context_analysis,
        "priority_level": priority_level,
        "decision_trace": decision_trace,
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
        intent_detector=collaborators["intent_detector"],
        context_analyzer=collaborators["context_analyzer"],
        memory_retrieval_engine=collaborators["memory_retrieval_engine"],
        priority_queue_manager=collaborators["priority_queue_manager"],
        authority_evaluator=collaborators["authority_evaluator"],
        short_term_memory=collaborators["short_term_memory"],
        confidence_scorer=collaborators["confidence_scorer"],
        memory_lifecycle_manager=collaborators["memory_lifecycle_manager"],
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


# --- Decision Engine pipeline sequencing (Sprint 3.12) -----------------------


def test_run_decision_pipeline_calls_every_stage_in_order_with_the_right_arguments(
    pipeline, collaborators
):
    context = collaborators["context"]

    trace = pipeline._run_decision_pipeline("hello there", context, "session-1")

    collaborators["intent_detector"].detect.assert_called_once_with("hello there", context)
    collaborators["context_analyzer"].analyze.assert_called_once_with(
        collaborators["intent"], context
    )
    collaborators["memory_retrieval_engine"].retrieve.assert_called_once_with(
        "some topic", "jarvis", "session-1"
    )
    collaborators["priority_queue_manager"].classify.assert_called_once_with(
        collaborators["intent"]
    )
    collaborators["authority_evaluator"].evaluate.assert_called_once_with(
        collaborators["intent"],
        collaborators["context_analysis"],
        [],
        collaborators["priority_level"],
    )
    assert trace is collaborators["decision_trace"]


def test_handle_turn_complete_happy_path(pipeline, collaborators):
    pipeline._handle_turn_complete("hello there", "session-1")

    collaborators["persona_manager"].detect_explicit_selection.assert_called_once_with(
        "hello there"
    )
    collaborators["context_manager"].current_context.assert_called_once_with(
        "session-1", "jarvis"
    )
    collaborators["persona_manager"].compose_reply_safely.assert_called_once_with(
        "hello there", collaborators["context"], collaborators["decision_trace"]
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
    collaborators["persona_manager"].select_from_context.assert_not_called()


def test_handle_turn_complete_falls_back_to_select_from_context(pipeline, collaborators):
    collaborators["persona_manager"].detect_explicit_selection.return_value = None

    pipeline._handle_turn_complete("i'm feeling tired", "session-1")

    collaborators["persona_manager"].select_from_context.assert_called_once_with(
        collaborators["context_analysis"], "i'm feeling tired"
    )
    collaborators["persona_manager"].select.assert_not_called()


# --- Memory promotion / user override (Sprint 3.12) --------------------------


def test_handle_turn_complete_promotes_the_turn_to_short_term_memory(pipeline, collaborators):
    pipeline._handle_turn_complete("remind me to call mom", "session-1")

    collaborators["short_term_memory"].promote_from_turn.assert_called_once()
    turn = collaborators["short_term_memory"].promote_from_turn.call_args[0][0]
    assert turn.user_text == "remind me to call mom"


def test_handle_turn_complete_applies_override_when_promoted_and_phrase_detected(
    pipeline, collaborators
):
    collaborators["short_term_memory"].promote_from_turn.return_value = "record-123"
    collaborators["confidence_scorer"].detect_override_phrase.return_value = True

    pipeline._handle_turn_complete("this is important", "session-1")

    collaborators["confidence_scorer"].detect_override_phrase.assert_called_once_with(
        "this is important"
    )
    collaborators["memory_lifecycle_manager"].apply_user_override.assert_called_once_with(
        "record-123"
    )


def test_handle_turn_complete_skips_override_when_nothing_was_promoted(pipeline, collaborators):
    collaborators["short_term_memory"].promote_from_turn.return_value = None
    collaborators["confidence_scorer"].detect_override_phrase.return_value = True

    pipeline._handle_turn_complete("this is important", "session-1")

    collaborators["memory_lifecycle_manager"].apply_user_override.assert_not_called()


def test_handle_turn_complete_skips_override_when_phrase_not_detected(pipeline, collaborators):
    collaborators["short_term_memory"].promote_from_turn.return_value = "record-123"
    collaborators["confidence_scorer"].detect_override_phrase.return_value = False

    pipeline._handle_turn_complete("just a normal thing", "session-1")

    collaborators["memory_lifecycle_manager"].apply_user_override.assert_not_called()


# --- Exception containment (Sprint 2.13, still applies with the new steps) --


def test_handle_turn_complete_contains_an_unexpected_failure_and_ends_the_session(
    pipeline, collaborators
):
    """Sprint 2.13 hardening: a real gap this sprint found — before this
    fix, an unexpected exception anywhere in this method (this test
    forces one from record_turn) silently killed the session's own
    background thread instead of ending the session gracefully. Sprint
    3.12 adds several new steps inside the same try/except, so this
    still-forced failure confirms the containment still holds."""
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


def test_handle_turn_complete_contains_a_decision_pipeline_failure(pipeline, collaborators):
    """New failure surface Sprint 3.12 introduces: an unexpected exception
    anywhere in the Decision Engine pipeline itself must degrade the same
    way as every other unexpected failure in this method (hardening the
    specific, graceful degrade of an individual stage is Sprint 3.13's
    job — this only confirms the outer containment still catches it)."""
    collaborators["intent_detector"].detect.side_effect = RuntimeError("ollama exploded")

    pipeline._handle_turn_complete("hello there", "session-1")  # must not raise

    collaborators["session_manager"].end_session.assert_called_once_with(SessionEndReason.ERROR)
