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
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from config.schema import MemoryConfig, SchedulerConfig
from decision.authority import EngineSelection
from decision.llm_client import LlmError
from decision.priority_queue import PriorityLevel
from device_control.action_engine import ActionResult, ActionStatus
from emotion.state_manager import EmotionalState
from internet.search_provider import SearchResult
from internet.source_validator import Citation
from internet.summarizer import ResearchSummary
from personas.persona_manager import SwitchReason
from presentation.adaptive_workspace import WorkspaceProfile
from scheduler.scheduler_model import ItemType, ScheduledItem
from security.confirmation_service import ConfirmationOutcome
from voice.pipeline import CallbackRelay, CommunicationPipeline
from voice.quiet_mode import ActivationReason, OperatingMode
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

    response_generator = MagicMock()
    response_generator.generate.return_value = "a reply"

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

    quiet_mode_controller = MagicMock()
    quiet_mode_controller.current_mode.return_value = OperatingMode.DORMANT

    priority_queue_manager.peek_next.return_value = None
    priority_queue_manager.pop_next.return_value = None

    context.last_activity_at = datetime.now(UTC)

    # Sprint 5.14 collaborators. A real EmotionalState (not a MagicMock)
    # for apply_estimate()/current_state() — _score_significance()
    # (memory/emotional_memory.py) does real dataclass-field arithmetic
    # on whatever this returns, which a MagicMock cannot support. Its
    # neutral defaults score 0.0 significance, below any real
    # emotional_moment_recall_threshold, so record_significant_moment()
    # is not called unless a test explicitly configures a displaced
    # state. voice_personality_modulator.shape_pacing() and
    # companion_experience_engine's two check_for_*() methods are
    # explicitly configured to their real "no-op" defaults (identity
    # passthrough / None) so every existing reply-text assertion in this
    # file keeps holding exactly as it did before Sprint 5.14 — a
    # default MagicMock return value for either would otherwise corrupt
    # every test's own spoken reply text.
    emotion_detection_engine = MagicMock()
    emotional_state_manager = MagicMock()
    emotional_state_manager.apply_estimate.return_value = EmotionalState()
    emotional_state_manager.current_state.return_value = EmotionalState()
    emotional_memory = MagicMock()
    presentation_controller = MagicMock()
    presentation_controller.last_state_for.return_value = None
    presentation_controller.mounted_persona_name = "jarvis"
    adaptive_workspace_controller = MagicMock()
    adaptive_workspace_controller.select_profile.return_value = WorkspaceProfile.GENERAL
    gesture_engine = MagicMock()
    gesture_engine.trigger_event.return_value = None
    voice_personality_modulator = MagicMock()
    voice_personality_modulator.shape_pacing.side_effect = lambda text, warmth: text
    lip_sync_driver = MagicMock()
    companion_experience_engine = MagicMock()
    companion_experience_engine.check_for_greeting.return_value = None
    companion_experience_engine.check_for_celebration.return_value = None
    jarvis_renderer = MagicMock()
    avatar_renderer = MagicMock()

    return {
        "mic": MagicMock(),
        "wake_word_detector": MagicMock(),
        "session_manager": MagicMock(),
        "quiet_mode_controller": quiet_mode_controller,
        "conversation_store": MagicMock(),
        "context_manager": context_manager,
        "persona_manager": persona_manager,
        "turn_complete_relay": CallbackRelay(),
        "session_ended_relay": CallbackRelay(),
        "intent_detector": intent_detector,
        "context_analyzer": context_analyzer,
        "response_generator": response_generator,
        "memory_retrieval_engine": memory_retrieval_engine,
        "priority_queue_manager": priority_queue_manager,
        "authority_evaluator": authority_evaluator,
        "short_term_memory": short_term_memory,
        "confidence_scorer": confidence_scorer,
        "memory_lifecycle_manager": memory_lifecycle_manager,
        "action_registry": action_registry,
        "workflow_store": workflow_store,
        "workflow_executor": workflow_executor,
        "task_scheduler": MagicMock(),
        "calendar_store": MagicMock(),
        "reminder_engine": MagicMock(),
        "research_engine": MagicMock(),
        "source_validator": MagicMock(),
        "summarizer": MagicMock(),
        "action_audit_log": MagicMock(),
        "scheduler_config": SchedulerConfig(),
        "memory_config": MemoryConfig(),
        "emotion_detection_engine": emotion_detection_engine,
        "emotional_state_manager": emotional_state_manager,
        "emotional_memory": emotional_memory,
        "presentation_controller": presentation_controller,
        "adaptive_workspace_controller": adaptive_workspace_controller,
        "gesture_engine": gesture_engine,
        "voice_personality_modulator": voice_personality_modulator,
        "lip_sync_driver": lip_sync_driver,
        "companion_experience_engine": companion_experience_engine,
        "jarvis_renderer": jarvis_renderer,
        "avatar_renderer": avatar_renderer,
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
        response_generator=collaborators["response_generator"],
        memory_retrieval_engine=collaborators["memory_retrieval_engine"],
        priority_queue_manager=collaborators["priority_queue_manager"],
        authority_evaluator=collaborators["authority_evaluator"],
        short_term_memory=collaborators["short_term_memory"],
        confidence_scorer=collaborators["confidence_scorer"],
        memory_lifecycle_manager=collaborators["memory_lifecycle_manager"],
        action_registry=collaborators["action_registry"],
        workflow_store=collaborators["workflow_store"],
        workflow_executor=collaborators["workflow_executor"],
        task_scheduler=collaborators["task_scheduler"],
        calendar_store=collaborators["calendar_store"],
        reminder_engine=collaborators["reminder_engine"],
        research_engine=collaborators["research_engine"],
        source_validator=collaborators["source_validator"],
        summarizer=collaborators["summarizer"],
        action_audit_log=collaborators["action_audit_log"],
        scheduler_config=collaborators["scheduler_config"],
        memory_config=collaborators["memory_config"],
        emotion_detection_engine=collaborators["emotion_detection_engine"],
        emotional_state_manager=collaborators["emotional_state_manager"],
        emotional_memory=collaborators["emotional_memory"],
        presentation_controller=collaborators["presentation_controller"],
        adaptive_workspace_controller=collaborators["adaptive_workspace_controller"],
        gesture_engine=collaborators["gesture_engine"],
        voice_personality_modulator=collaborators["voice_personality_modulator"],
        lip_sync_driver=collaborators["lip_sync_driver"],
        companion_experience_engine=collaborators["companion_experience_engine"],
        jarvis_renderer=collaborators["jarvis_renderer"],
        avatar_renderer=collaborators["avatar_renderer"],
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


# --- TaskScheduler job registration (Sprint 4.18) -----------------------------


def test_start_registers_reminder_engine(pipeline, collaborators):
    pipeline.start()

    collaborators["reminder_engine"].register.assert_called_once()


def test_start_registers_every_maintenance_job(pipeline, collaborators):
    pipeline.start()

    add_job = collaborators["task_scheduler"].add_job
    registered_job_ids = {call.kwargs["job_id"] for call in add_job.call_args_list}
    assert registered_job_ids == {
        "memory_lifecycle_cleanup_pass",
        "memory_lifecycle_monthly_review",
        "conversation_store_purge",
        "action_audit_log_purge",
        "proactive_reminder_announcement",
    }


def test_start_registers_maintenance_jobs_with_the_configured_interval(pipeline, collaborators):
    pipeline.start()

    add_job = collaborators["task_scheduler"].add_job
    interval_for_job_id = {call.kwargs["job_id"]: call.args[1] for call in add_job.call_args_list}
    scheduler_config = collaborators["scheduler_config"]
    assert interval_for_job_id["memory_lifecycle_cleanup_pass"] == (
        scheduler_config.maintenance_interval_seconds
    )
    assert interval_for_job_id["conversation_store_purge"] == (
        scheduler_config.maintenance_interval_seconds
    )
    assert interval_for_job_id["proactive_reminder_announcement"] == (
        scheduler_config.poll_interval_seconds
    )


def test_start_registers_maintenance_jobs_with_the_real_bound_methods(pipeline, collaborators):
    pipeline.start()

    add_job = collaborators["task_scheduler"].add_job
    func_for_job_id = {call.kwargs["job_id"]: call.args[0] for call in add_job.call_args_list}
    assert func_for_job_id["memory_lifecycle_cleanup_pass"] == (
        collaborators["memory_lifecycle_manager"].run_cleanup_pass
    )
    assert func_for_job_id["memory_lifecycle_monthly_review"] == (
        collaborators["memory_lifecycle_manager"].run_monthly_review
    )
    assert func_for_job_id["conversation_store_purge"] == (
        collaborators["conversation_store"].purge_older_than
    )
    assert func_for_job_id["action_audit_log_purge"] == (
        collaborators["action_audit_log"].purge_older_than
    )
    assert func_for_job_id["proactive_reminder_announcement"] == (
        pipeline._check_and_announce_due_reminder
    )


def test_stop_removes_every_job_and_unregisters_reminder_engine(pipeline, collaborators):
    pipeline.start()

    pipeline.stop()

    remove_job = collaborators["task_scheduler"].remove_job
    removed_job_ids = {call.args[0] for call in remove_job.call_args_list}
    assert removed_job_ids == {
        "memory_lifecycle_cleanup_pass",
        "memory_lifecycle_monthly_review",
        "conversation_store_purge",
        "action_audit_log_purge",
        "proactive_reminder_announcement",
    }
    collaborators["reminder_engine"].unregister.assert_called_once()


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
    collaborators["context_manager"].current_context.assert_called_once_with("session-1", "jarvis")
    collaborators["response_generator"].generate.assert_called_once_with(
        "hello there", collaborators["context"], collaborators["decision_trace"], "jarvis"
    )
    collaborators["persona_manager"].compose_reply_safely.assert_not_called()
    collaborators["conversation_store"].record_turn.assert_called_once()
    turn = collaborators["conversation_store"].record_turn.call_args[0][0]
    assert turn.session_id == "session-1"
    assert turn.persona_name == "jarvis"
    assert turn.user_text == "hello there"
    assert turn.response_text == "a reply"
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "a reply", "p340", on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted
    )


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


# --- Conversational Response Generation (0.4.2) -------------------------------
#
# Replaces Sprint 3.12's "compose_reply() IS the pipeline's Response
# Generation stage" placeholder with a real LLM call (see
# decision/response_generator.py and docs/changelog/0.4.2-conversational-
# response-generation.md). PersonaManager.compose_reply_safely() (the old
# templated acknowledgement) is now reached only via
# _compose_conversational_reply()'s own two named degrade cases.


def test_conversational_turn_calls_response_generator_with_persona_name(pipeline, collaborators):
    pipeline._handle_turn_complete("what's the capital of France", "session-1")

    collaborators["response_generator"].generate.assert_called_once_with(
        "what's the capital of France",
        collaborators["context"],
        collaborators["decision_trace"],
        "jarvis",
    )
    collaborators["persona_manager"].compose_reply_safely.assert_not_called()
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "a reply", "p340", on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted
    )


def test_conversational_turn_skips_the_llm_call_for_an_empty_transcript(pipeline, collaborators):
    pipeline._handle_turn_complete("   ", "session-1")

    collaborators["response_generator"].generate.assert_not_called()
    collaborators["persona_manager"].compose_reply_safely.assert_called_once_with(
        "   ", collaborators["context"], collaborators["decision_trace"]
    )


def test_conversational_turn_falls_back_to_the_template_on_llm_error(pipeline, collaborators):
    collaborators["response_generator"].generate.side_effect = LlmError("ollama unreachable")

    pipeline._handle_turn_complete("what's the capital of France", "session-1")

    collaborators["persona_manager"].compose_reply_safely.assert_called_once_with(
        "what's the capital of France", collaborators["context"], collaborators["decision_trace"]
    )
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "a reply", "p340", on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted
    )


def test_conversational_turn_llm_error_does_not_end_the_session(pipeline, collaborators):
    collaborators["response_generator"].generate.side_effect = LlmError("timeout")

    pipeline._handle_turn_complete("what's the capital of France", "session-1")

    collaborators["session_manager"].end_session.assert_not_called()


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
    # decision_trace=None still reaches ResponseGenerator (it tolerates a
    # missing trace, generating without trace-derived grounding) — the
    # templated fallback is reserved for an actual LlmError, not merely a
    # missing DecisionTrace. See _compose_conversational_reply()'s own
    # docstring.
    collaborators["response_generator"].generate.assert_called_once_with(
        "hello there", collaborators["context"], None, "jarvis"
    )
    collaborators["persona_manager"].compose_reply_safely.assert_not_called()
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "a reply", "p340", on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted
    )
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
    collaborators["response_generator"].generate.assert_not_called()
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "Done — I've opened notepad.exe.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
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
        "I couldn't tell what application to open.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
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
        "I'm not able to do that: Application not on allowlist",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
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
        "That didn't work: No such file or directory",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
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
        "Done — I've run the 'Morning Routine' workflow.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
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
        "I couldn't find a workflow named 'nonexistent workflow'.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
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
        "I didn't run the 'Big Cleanup' workflow since it wasn't confirmed.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
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
        "I ran part of the 'Big Cleanup' workflow, but a step failed partway through.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
    )


# --- SCHEDULER routing (Sprint 4.18) ------------------------------------------


def test_scheduler_turn_creates_a_reminder_with_a_resolvable_time(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.SCHEDULER
    collaborators["decision_trace"].intent = collaborators["intent"]
    collaborators["intent"].raw_transcript = "remind me to call mom in 20 minutes"
    collaborators["context_analysis"].primary_topic = "call mom"

    pipeline._handle_turn_complete("remind me to call mom in 20 minutes", "session-1")

    collaborators["calendar_store"].save.assert_called_once()
    saved_item = collaborators["calendar_store"].save.call_args[0][0]
    assert saved_item.title == "call mom"
    assert saved_item.item_type == ItemType.EVENT
    reply_text = collaborators["session_manager"].speak_reply.call_args[0][0]
    assert reply_text.startswith("Done — I'll remind you about call mom at")


def test_scheduler_turn_falls_back_to_raw_transcript_when_no_topic(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.SCHEDULER
    collaborators["decision_trace"].intent = collaborators["intent"]
    collaborators["intent"].raw_transcript = "remind me to call mom in 20 minutes"
    collaborators["context_analysis"].primary_topic = ""

    pipeline._handle_turn_complete("remind me to call mom in 20 minutes", "session-1")

    saved_item = collaborators["calendar_store"].save.call_args[0][0]
    assert saved_item.title == "remind me to call mom in 20 minutes"


def test_scheduler_turn_with_no_resolvable_time_reports_it_and_never_saves(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.SCHEDULER
    collaborators["decision_trace"].intent = collaborators["intent"]
    collaborators["intent"].raw_transcript = "remind me to call mom tomorrow"

    pipeline._handle_turn_complete("remind me to call mom tomorrow", "session-1")

    collaborators["calendar_store"].save.assert_not_called()
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "I couldn't tell when to remind you.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
    )


def test_scheduler_turn_calendar_store_save_failure_degrades_to_an_honest_reply(
    pipeline, collaborators
):
    """Sprint 4.19 hardening, scenario (e): a real SQLite failure inside
    calendar_store.save() must not fall through to _handle_turn_complete()'s
    outer catch (which would speak no reply at all and end the session),
    and must not be silently swallowed into a false "Done" claim either —
    a narrow catch right here degrades to an honest spoken reply while the
    session continues normally."""
    collaborators["decision_trace"].selected_engine = EngineSelection.SCHEDULER
    collaborators["decision_trace"].intent = collaborators["intent"]
    collaborators["intent"].raw_transcript = "remind me to call mom in 20 minutes"
    collaborators["context_analysis"].primary_topic = "call mom"
    collaborators["calendar_store"].save.side_effect = RuntimeError("sqlite exploded")

    pipeline._handle_turn_complete("remind me to call mom in 20 minutes", "session-1")

    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "I'm sorry, I couldn't save that reminder right now.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
    )
    collaborators["session_manager"].end_session.assert_not_called()


# --- INTERNET_AGENT routing (Sprint 4.18) -------------------------------------


def test_internet_agent_turn_speaks_summary_with_citation_count(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.INTERNET_AGENT
    collaborators["decision_trace"].intent = collaborators["intent"]
    collaborators["intent"].raw_transcript = "search for the latest Python release"
    collaborators["context_analysis"].primary_topic = "latest Python release"

    results = [
        SearchResult(
            title="T", url="https://example.com", snippet="s", retrieved_at=datetime.now(UTC)
        )
    ]
    collaborators["research_engine"].research.return_value = results
    citations = [Citation(title="T", url="https://example.com", is_corroborated=True)]
    collaborators["source_validator"].validate.return_value = citations
    collaborators["summarizer"].summarize.return_value = ResearchSummary(
        query="latest Python release",
        summary_text="Python 3.13 was released recently.",
        citations=citations,
        generated_at=datetime.now(UTC),
    )

    pipeline._handle_turn_complete("search for the latest Python release", "session-1")

    collaborators["research_engine"].research.assert_called_once_with("latest Python release")
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "Python 3.13 was released recently. (Based on 1 source(s), 1 corroborated.)",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
    )


def test_internet_agent_turn_with_no_results_reports_it_and_never_summarizes(
    pipeline, collaborators
):
    collaborators["decision_trace"].selected_engine = EngineSelection.INTERNET_AGENT
    collaborators["decision_trace"].intent = collaborators["intent"]
    collaborators["intent"].raw_transcript = "search for something obscure"
    collaborators["context_analysis"].primary_topic = "something obscure"
    collaborators["research_engine"].research.return_value = []

    pipeline._handle_turn_complete("search for something obscure", "session-1")

    collaborators["summarizer"].summarize.assert_not_called()
    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "I couldn't find anything for something obscure.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
    )


# --- Proactive reminder announcement (Sprint 4.18) ----------------------------


def test_check_and_announce_due_reminder_skips_when_a_session_is_active(pipeline, collaborators):
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.ACTIVE

    pipeline._check_and_announce_due_reminder()

    collaborators["priority_queue_manager"].peek_next.assert_not_called()
    collaborators["quiet_mode_controller"].activate.assert_not_called()


def test_check_and_announce_due_reminder_skips_when_queue_is_empty(pipeline, collaborators):
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = None

    pipeline._check_and_announce_due_reminder()

    collaborators["priority_queue_manager"].pop_next.assert_not_called()
    collaborators["quiet_mode_controller"].activate.assert_not_called()


def test_check_and_announce_due_reminder_skips_a_non_reminder_item(pipeline, collaborators):
    peeked = MagicMock()
    peeked.priority = PriorityLevel.IMPORTANT_ALERT
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = peeked

    pipeline._check_and_announce_due_reminder()

    collaborators["priority_queue_manager"].pop_next.assert_not_called()
    collaborators["quiet_mode_controller"].activate.assert_not_called()


def test_check_and_announce_due_reminder_announces_a_due_reminder(pipeline, collaborators):
    scheduled_item = ScheduledItem(
        item_id="item-1",
        item_type=ItemType.EVENT,
        title="Team standup",
        scheduled_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    peeked = MagicMock()
    peeked.priority = PriorityLevel.SCHEDULED_REMINDER
    popped = MagicMock()
    popped.payload = scheduled_item
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = peeked
    collaborators["priority_queue_manager"].pop_next.return_value = popped

    pipeline._check_and_announce_due_reminder()

    collaborators["priority_queue_manager"].pop_next.assert_called_once()
    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT, announce_first=("Team standup", "p340")
    )


# --- Sprint 4.19 hardening: adversarial sweep -----------------------------------
#
# Acceptance Criteria, verbatim: "Every internal call site in
# _handle_scheduler_turn()/_handle_internet_agent_turn()/_check_and_
# announce_due_reminder() is covered by the adversarial sweep test."
# Split into two sweeps rather than one, matching the two genuinely
# different expected outcomes investigation found — forcing both into
# one shared parametrize would blur a real, deliberate distinction:
#
# (1) _handle_scheduler_turn()/_handle_internet_agent_turn() both run
#     INSIDE _handle_turn_complete()'s own try/except (Sprint 2.13) — a
#     collaborator fault here must never propagate out of a live turn;
#     it degrades to _handle_turn_complete()'s existing outer catch
#     (ending the session, SessionEndReason.ERROR) unless a narrower
#     guard already exists (calendar_store.save(), Sprint 4.19
#     scenario e, tested separately with its own exact reply text above
#     — included here too for real sweep completeness).
# (2) _check_and_announce_due_reminder() is a bare TaskScheduler job
#     body with no try/except of its own, by design (see this module's
#     docstring) — its collaborators are all in-memory, already-hardened
#     objects with no real external I/O of their own, so a fault here is
#     a genuine bug, not an anticipatable environmental failure; adding
#     a blanket catch would only risk masking that bug rather than
#     degrading a real failure mode. The CORRECT, expected behavior is
#     that it RAISES, safely absorbed by the same TaskScheduler/
#     APScheduler job-isolation guarantee Sprint 4.19 scenario (c)
#     already re-verifies against the real, fully-wired five-job graph
#     (tests/integration/test_scheduler_integration.py) — never left
#     unverified as "presumably fine."


def _make_due_reminder_peek_pop(collaborators) -> None:
    scheduled_item = ScheduledItem(
        item_id="item-1",
        item_type=ItemType.EVENT,
        title="Team standup",
        scheduled_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    peeked = MagicMock()
    peeked.priority = PriorityLevel.SCHEDULED_REMINDER
    popped = MagicMock()
    popped.payload = scheduled_item
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = peeked
    collaborators["priority_queue_manager"].pop_next.return_value = popped


@pytest.mark.parametrize(
    ("selected_engine", "raw_transcript", "primary_topic", "faulty_collaborator", "faulty_method"),
    [
        (
            EngineSelection.SCHEDULER,
            "remind me to call mom in 20 minutes",
            "call mom",
            "calendar_store",
            "save",
        ),
        (
            EngineSelection.INTERNET_AGENT,
            "search for the latest Python release",
            "latest Python release",
            "research_engine",
            "research",
        ),
        (
            EngineSelection.INTERNET_AGENT,
            "search for the latest Python release",
            "latest Python release",
            "source_validator",
            "validate",
        ),
        (
            EngineSelection.INTERNET_AGENT,
            "search for the latest Python release",
            "latest Python release",
            "summarizer",
            "summarize",
        ),
    ],
    ids=[
        "calendar_store.save_raises",
        "research_engine.research_raises",
        "source_validator.validate_raises",
        "summarizer.summarize_raises",
    ],
)
def test_live_turn_sweep_every_scheduler_and_internet_agent_call_site_never_propagates(
    pipeline,
    collaborators,
    selected_engine,
    raw_transcript,
    primary_topic,
    faulty_collaborator,
    faulty_method,
):
    """Sweep (1) — see this section's own header comment. A non-empty
    research_engine.research() result is the default for every
    INTERNET_AGENT case so source_validator.validate()/summarizer.
    summarize() are genuinely reached (not short-circuited by the empty-
    results early return), matching test_internet_agent_turn_speaks_
    summary_with_citation_count's own setup."""
    collaborators["decision_trace"].selected_engine = selected_engine
    collaborators["decision_trace"].intent = collaborators["intent"]
    collaborators["intent"].raw_transcript = raw_transcript
    collaborators["context_analysis"].primary_topic = primary_topic
    collaborators["research_engine"].research.return_value = [
        SearchResult(
            title="T", url="https://example.com", snippet="s", retrieved_at=datetime.now(UTC)
        )
    ]
    getattr(collaborators[faulty_collaborator], faulty_method).side_effect = RuntimeError(
        "simulated collaborator failure"
    )

    pipeline._handle_turn_complete(raw_transcript, "session-1")  # must never raise

    if faulty_collaborator == "calendar_store":
        # The one call site with its own narrower guard (scenario e) —
        # the session continues with an honest reply, never ended.
        collaborators["session_manager"].end_session.assert_not_called()
    else:
        # No narrower guard exists for these three — _handle_turn_
        # complete()'s own outer catch ends the session gracefully
        # rather than leaving it stuck, the same degrade every other
        # genuinely unexpected internal bug already gets.
        collaborators["session_manager"].end_session.assert_called_once_with(SessionEndReason.ERROR)
        collaborators["session_manager"].speak_reply.assert_not_called()


@pytest.mark.parametrize(
    ("faulty_collaborator", "faulty_method"),
    [
        ("quiet_mode_controller", "current_mode"),
        ("priority_queue_manager", "peek_next"),
        ("priority_queue_manager", "pop_next"),
        ("persona_manager", "active_persona"),
        ("quiet_mode_controller", "activate"),
    ],
    ids=[
        "quiet_mode_controller.current_mode_raises",
        "priority_queue_manager.peek_next_raises",
        "priority_queue_manager.pop_next_raises",
        "persona_manager.active_persona_raises",
        "quiet_mode_controller.activate_raises",
    ],
)
def test_check_and_announce_due_reminder_sweep_every_call_site_raises_by_design(
    pipeline, collaborators, faulty_collaborator, faulty_method
):
    """Sweep (2) — see this section's own header comment. Deliberately
    asserts pytest.raises(), not a graceful degrade: this method has no
    try/except of its own, on purpose, and relies on the calling
    TaskScheduler job's own APScheduler-provided isolation instead."""
    _make_due_reminder_peek_pop(collaborators)
    getattr(collaborators[faulty_collaborator], faulty_method).side_effect = RuntimeError(
        "simulated collaborator failure"
    )

    with pytest.raises(RuntimeError, match="simulated collaborator failure"):
        pipeline._check_and_announce_due_reminder()
