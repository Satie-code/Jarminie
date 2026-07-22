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

import logging
from unittest.mock import MagicMock

import pytest

from decision.authority import EngineSelection
from device_control.action_engine import ActionResult, ActionStatus
from personas.persona_manager import SwitchReason
from security.confirmation_service import ConfirmationOutcome
from voice.pipeline import CallbackRelay, CommunicationPipeline
from voice.session_manager import SessionEndReason
from workflow.workflow_executor import WorkflowRunResult


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
    context_analysis.mentioned_entities = []
    context_analyzer = MagicMock()
    context_analyzer.analyze.return_value = context_analysis

    memory_retrieval_engine = MagicMock()
    memory_retrieval_engine.retrieve.return_value = []

    priority_level = MagicMock(name="priority_level")
    priority_queue_manager = MagicMock()
    priority_queue_manager.classify.return_value = priority_level

    decision_trace = MagicMock(name="decision_trace")
    decision_trace.context_analysis = context_analysis
    decision_trace.selected_engine = EngineSelection.CONVERSATIONAL_RESPONSE
    authority_evaluator = MagicMock()
    authority_evaluator.evaluate.return_value = decision_trace

    short_term_memory = MagicMock()
    short_term_memory.promote_from_turn.return_value = None

    confidence_scorer = MagicMock()
    confidence_scorer.detect_override_phrase.return_value = False

    memory_lifecycle_manager = MagicMock()

    action_registry = MagicMock()
    action_registry.dispatch.return_value = ActionResult(
        request=MagicMock(), status=ActionStatus.SUCCEEDED, completed_at=MagicMock()
    )

    workflow_store = MagicMock()
    workflow_store.list_all.return_value = []

    workflow_executor = MagicMock()

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
        "action_registry": action_registry,
        "workflow_store": workflow_store,
        "workflow_executor": workflow_executor,
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
        action_registry=collaborators["action_registry"],
        workflow_store=collaborators["workflow_store"],
        workflow_executor=collaborators["workflow_executor"],
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


def test_decision_pipeline_failure_degrades_gracefully_without_ending_the_session(
    pipeline, collaborators, caplog
):
    """Sprint 3.13 hardening (scenario f): an unexpected exception
    anywhere in the Decision Engine pipeline no longer ends the whole
    session (as it did before this sprint, when it fell through to the
    outer catch below) — it degrades to decision_trace=None and the turn
    still completes with a spoken, Level-2-quality reply, exactly the
    case Persona.compose_reply()'s decision_trace: DecisionTrace | None
    signature (Sprint 3.12) was designed to tolerate."""
    collaborators["intent_detector"].detect.side_effect = RuntimeError("ollama exploded")

    with caplog.at_level(logging.WARNING):
        pipeline._handle_turn_complete("hello there", "session-1")  # must not raise

    collaborators["session_manager"].end_session.assert_not_called()
    collaborators["persona_manager"].select_from_context.assert_called_once_with(
        None, "hello there"
    )
    collaborators["persona_manager"].compose_reply_safely.assert_called_once_with(
        "hello there", collaborators["context"], None
    )
    collaborators["session_manager"].speak_reply.assert_called_once_with("a reply", "p340")
    assert any("Decision Engine pipeline failed" in r.message for r in caplog.records)


# --- DEVICE_CONTROL / WORKFLOW routing (Sprint 4.11) -------------------------


def test_device_control_turn_dispatches_launch_application_and_speaks_confirmation(
    pipeline, collaborators
):
    collaborators["decision_trace"].selected_engine = EngineSelection.DEVICE_CONTROL
    collaborators["context_analysis"].mentioned_entities = ["notepad"]

    pipeline._handle_turn_complete("open notepad", "session-1")

    request = collaborators["action_registry"].dispatch.call_args[0][0]
    assert request.action_type.value == "launch_application"
    assert request.parameters == {"operation": "launch", "executable_path": "notepad.exe"}
    assert request.context.requested_by == "voice_turn"
    assert request.context.persona_name == "jarvis"
    assert request.context.session_id == "session-1"
    assert request.context.decision_trace is collaborators["decision_trace"]

    collaborators["persona_manager"].compose_reply_safely.assert_not_called()
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "Done — I've opened notepad.exe.", "p340"
    )
    turn = collaborators["conversation_store"].record_turn.call_args[0][0]
    assert turn.response_text == "Done — I've opened notepad.exe."


def test_device_control_turn_passes_through_an_extension_already_present(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.DEVICE_CONTROL
    collaborators["context_analysis"].mentioned_entities = ["chrome.exe"]

    pipeline._handle_turn_complete("open chrome.exe", "session-1")

    request = collaborators["action_registry"].dispatch.call_args[0][0]
    assert request.parameters["executable_path"] == "chrome.exe"


def test_device_control_turn_with_no_entity_reports_it_could_not_tell(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.DEVICE_CONTROL
    collaborators["context_analysis"].mentioned_entities = []

    pipeline._handle_turn_complete("open it", "session-1")

    collaborators["action_registry"].dispatch.assert_not_called()
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "I couldn't tell what application to open.", "p340"
    )


def test_device_control_turn_reports_a_denied_result(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.DEVICE_CONTROL
    collaborators["context_analysis"].mentioned_entities = ["cmd"]
    collaborators["action_registry"].dispatch.return_value = ActionResult(
        request=MagicMock(),
        status=ActionStatus.DENIED,
        completed_at=MagicMock(),
        error_message="Application not on allowlist",
    )

    pipeline._handle_turn_complete("open cmd", "session-1")

    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "I'm not able to do that: Application not on allowlist", "p340"
    )


def test_device_control_turn_reports_a_failed_result(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.DEVICE_CONTROL
    collaborators["context_analysis"].mentioned_entities = ["nonexistent"]
    collaborators["action_registry"].dispatch.return_value = ActionResult(
        request=MagicMock(),
        status=ActionStatus.FAILED,
        completed_at=MagicMock(),
        error_message="No such file or directory",
    )

    pipeline._handle_turn_complete("open nonexistent", "session-1")

    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "That didn't work: No such file or directory", "p340"
    )


def test_workflow_turn_resolves_by_name_and_runs_it(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.WORKFLOW
    collaborators["context_analysis"].mentioned_entities = ["Morning Routine"]
    stored = MagicMock()
    stored.name = "Morning Routine"
    stored.workflow_id = "wf-1"
    collaborators["workflow_store"].list_all.return_value = [stored]
    run_result = WorkflowRunResult(
        workflow_id="wf-1",
        run_id="run-1",
        step_results=[MagicMock()],
        aborted_early=False,
        whole_workflow_confirmation=None,
        started_at=MagicMock(),
        completed_at=MagicMock(),
    )
    collaborators["workflow_executor"].run.return_value = run_result

    pipeline._handle_turn_complete("run my morning routine", "session-1")

    workflow_id, context = collaborators["workflow_executor"].run.call_args[0]
    assert workflow_id == "wf-1"
    assert context.requested_by == "voice_turn"
    assert context.session_id == "session-1"
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "Done — I've run the 'Morning Routine' workflow.", "p340"
    )


def test_workflow_turn_name_lookup_is_case_insensitive(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.WORKFLOW
    collaborators["context_analysis"].mentioned_entities = ["morning routine"]
    stored = MagicMock()
    stored.name = "Morning Routine"
    stored.workflow_id = "wf-1"
    collaborators["workflow_store"].list_all.return_value = [stored]
    collaborators["workflow_executor"].run.return_value = WorkflowRunResult(
        workflow_id="wf-1",
        run_id="run-1",
        step_results=[MagicMock()],
        aborted_early=False,
        whole_workflow_confirmation=None,
        started_at=MagicMock(),
        completed_at=MagicMock(),
    )

    pipeline._handle_turn_complete("run my morning routine", "session-1")

    collaborators["workflow_executor"].run.assert_called_once()
    assert collaborators["workflow_executor"].run.call_args[0][0] == "wf-1"


def test_workflow_turn_not_found_reports_it_and_never_calls_run(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.WORKFLOW
    collaborators["context_analysis"].mentioned_entities = ["nonexistent workflow"]
    collaborators["workflow_store"].list_all.return_value = []

    pipeline._handle_turn_complete("run the nonexistent workflow", "session-1")

    collaborators["workflow_executor"].run.assert_not_called()
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "I couldn't find a workflow named 'nonexistent workflow'.", "p340"
    )


def test_workflow_turn_declined_confirmation_reports_it(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.WORKFLOW
    collaborators["context_analysis"].mentioned_entities = ["Big Cleanup"]
    stored = MagicMock()
    stored.name = "Big Cleanup"
    stored.workflow_id = "wf-2"
    collaborators["workflow_store"].list_all.return_value = [stored]
    collaborators["workflow_executor"].run.return_value = WorkflowRunResult(
        workflow_id="wf-2",
        run_id="run-2",
        step_results=[],
        aborted_early=True,
        whole_workflow_confirmation=ConfirmationOutcome.DECLINED,
        started_at=MagicMock(),
        completed_at=MagicMock(),
    )

    pipeline._handle_turn_complete("run the big cleanup workflow", "session-1")

    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "I didn't run the 'Big Cleanup' workflow since it wasn't confirmed.", "p340"
    )


def test_workflow_turn_partial_run_reports_it(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.WORKFLOW
    collaborators["context_analysis"].mentioned_entities = ["Big Cleanup"]
    stored = MagicMock()
    stored.name = "Big Cleanup"
    stored.workflow_id = "wf-2"
    collaborators["workflow_store"].list_all.return_value = [stored]
    collaborators["workflow_executor"].run.return_value = WorkflowRunResult(
        workflow_id="wf-2",
        run_id="run-2",
        step_results=[MagicMock(), MagicMock()],
        aborted_early=True,
        whole_workflow_confirmation=None,
        started_at=MagicMock(),
        completed_at=MagicMock(),
    )

    pipeline._handle_turn_complete("run the big cleanup workflow", "session-1")

    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "I ran part of the 'Big Cleanup' workflow, but a step failed partway through.", "p340"
    )
