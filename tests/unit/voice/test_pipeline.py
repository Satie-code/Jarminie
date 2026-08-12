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

from config.schema import (
    LearningConfig,
    MemoryConfig,
    RuntimeConfig,
    SchedulerConfig,
    WellnessConfig,
)
from core.resource_monitor import ResourceSnapshot
from decision.adaptive_prioritizer import PrioritizationDecision
from decision.authority import EngineSelection
from decision.llm_client import LlmError
from decision.priority_queue import PriorityLevel
from device_control.action_engine import ActionResult, ActionStatus
from emotion.state_manager import EmotionalState
from internet.search_provider import SearchResult
from internet.source_validator import Citation
from internet.summarizer import ResearchSummary
from learning.recommendation import Recommendation
from personas.persona_manager import SwitchReason
from planning.planning_model import Goal, Milestone, PlanningStatus, Task
from planning.task_graph import TaskGraph
from presentation.adaptive_workspace import WorkspaceProfile
from reasoning.explainability import Explanation
from scheduler.scheduler_model import ItemType, ScheduledItem
from security.confirmation_service import ConfirmationOutcome
from voice.pipeline import CallbackRelay, CommunicationPipeline
from voice.quiet_mode import ActivationReason, OperatingMode
from voice.session_manager import SessionEndReason
from wellness.wellness_model import WellnessPrompt, WellnessTriggerType
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

    # Sprint 5.24 (Level 5 Part B) collaborators. wellness_tracker.
    # evaluate_triggers() defaults to None (no prompt currently due) —
    # the same "sensible no-op default" discipline priority_queue_
    # manager.peek_next()/pop_next() above already established — so an
    # unconfigured test's own _maybe_enqueue_wellness_prompt() call
    # never has an accidental enqueue side effect.
    wellness_tracker = MagicMock()
    wellness_tracker.evaluate_triggers.return_value = None
    wellness_escalation_manager = MagicMock()
    adaptive_wellness_adjuster = MagicMock()
    adaptive_wellness_adjuster.compute_overrides.return_value = {}
    dashboard_service = MagicMock()
    usage_tracker = MagicMock()
    pattern_recognizer = MagicMock()
    recommendation_engine = MagicMock()
    recommendation_engine.generate_recommendations.return_value = []

    # Runtime Phase 9 (Runtime Refactor Sprint) collaborators. Always
    # real constructor parameters (never None), so no optional-guard
    # pattern like the Level 5 Part B six above. resource_monitor.
    # is_over_threshold() defaults to False so _run_runtime_housekeeping()
    # never triggers resource-pressure eviction in a test that hasn't
    # explicitly configured a breach — the same "sensible no-op default"
    # discipline priority_queue_manager.peek_next()/pop_next() above
    # already established.
    runtime_manager = MagicMock()
    runtime_manager.sweep_idle_services.return_value = []
    runtime_manager.evict_least_recently_used.return_value = []
    resource_monitor = MagicMock()
    resource_monitor.is_over_threshold.return_value = False

    # Sprint 6.13 (Level 6 Part A) collaborators. context_engine/
    # adaptive_prioritizer default to None (not a MagicMock) —
    # deliberately, unlike every other collaborator in this fixture:
    # _peek_next_priority_item() branches on "is either one None" to
    # decide whether to consult AdaptivePrioritizer at all or fall back
    # to a plain peek_next() (see that method's own docstring). Leaving
    # either as a real MagicMock here would silently reroute EVERY
    # existing (pre-6.13) _check_and_announce_priority_item() test through
    # the new AdaptivePrioritizer-informed path instead of the plain
    # peek_next()-driven one those tests actually configure and assert
    # against — a real trap a first draft of this fixture fell into
    # (confirmed by running the suite: every _make_due_reminder_peek_pop()-
    # based test failed until this was corrected). A dedicated test
    # building its own pipeline via _build_pipeline() with these two
    # forced to real MagicMocks (the same "deliberately-modified
    # collaborators dict" pattern _build_pipeline()'s own docstring
    # already names) is what actually exercises the new path.
    task_graph_store = MagicMock()
    planning_engine = MagicMock()
    context_engine = None
    explainability_layer = MagicMock()
    adaptive_prioritizer = None
    task_graph_workflow_adapter = MagicMock()
    session_resumption = MagicMock()
    self_evaluator = MagicMock()

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
        "wellness_tracker": wellness_tracker,
        "wellness_escalation_manager": wellness_escalation_manager,
        "adaptive_wellness_adjuster": adaptive_wellness_adjuster,
        "dashboard_service": dashboard_service,
        "usage_tracker": usage_tracker,
        "pattern_recognizer": pattern_recognizer,
        "recommendation_engine": recommendation_engine,
        "learning_config": LearningConfig(),
        "wellness_config": WellnessConfig(),
        "runtime_manager": runtime_manager,
        "resource_monitor": resource_monitor,
        "runtime_config": RuntimeConfig(),
        "task_graph_store": task_graph_store,
        "planning_engine": planning_engine,
        "context_engine": context_engine,
        "explainability_layer": explainability_layer,
        "adaptive_prioritizer": adaptive_prioritizer,
        "task_graph_workflow_adapter": task_graph_workflow_adapter,
        "session_resumption": session_resumption,
        "self_evaluator": self_evaluator,
        "persona": persona,
        "context": context,
        "intent": intent,
        "context_analysis": context_analysis,
        "priority_level": priority_level,
        "decision_trace": decision_trace,
    }


def _build_pipeline(collaborators: dict) -> CommunicationPipeline:
    """Shared by the pipeline fixture below and any test that needs a
    pipeline built from a deliberately-modified collaborators dict (e.g.
    a Level 5 Part B dependency forced to None) — avoids duplicating this
    whole constructor call a second time."""
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
        wellness_tracker=collaborators["wellness_tracker"],
        wellness_escalation_manager=collaborators["wellness_escalation_manager"],
        adaptive_wellness_adjuster=collaborators["adaptive_wellness_adjuster"],
        dashboard_service=collaborators["dashboard_service"],
        usage_tracker=collaborators["usage_tracker"],
        pattern_recognizer=collaborators["pattern_recognizer"],
        recommendation_engine=collaborators["recommendation_engine"],
        learning_config=collaborators["learning_config"],
        wellness_config=collaborators["wellness_config"],
        runtime_manager=collaborators["runtime_manager"],
        resource_monitor=collaborators["resource_monitor"],
        runtime_config=collaborators["runtime_config"],
        task_graph_store=collaborators["task_graph_store"],
        planning_engine=collaborators["planning_engine"],
        context_engine=collaborators["context_engine"],
        explainability_layer=collaborators["explainability_layer"],
        adaptive_prioritizer=collaborators["adaptive_prioritizer"],
        task_graph_workflow_adapter=collaborators["task_graph_workflow_adapter"],
        session_resumption=collaborators["session_resumption"],
        self_evaluator=collaborators["self_evaluator"],
    )


@pytest.fixture
def pipeline(collaborators):
    return _build_pipeline(collaborators)


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
        "proactive_priority_item_announcement",
        "wellness_prompt_enqueue",
        "pattern_detection_pass",
        "recommendation_generation",
        "runtime_housekeeping",
    }


def test_start_registers_maintenance_jobs_with_the_configured_interval(pipeline, collaborators):
    pipeline.start()

    add_job = collaborators["task_scheduler"].add_job
    interval_for_job_id = {call.kwargs["job_id"]: call.args[1] for call in add_job.call_args_list}
    scheduler_config = collaborators["scheduler_config"]
    learning_config = collaborators["learning_config"]
    wellness_config = collaborators["wellness_config"]
    assert interval_for_job_id["memory_lifecycle_cleanup_pass"] == (
        scheduler_config.maintenance_interval_seconds
    )
    assert interval_for_job_id["conversation_store_purge"] == (
        scheduler_config.maintenance_interval_seconds
    )
    assert interval_for_job_id["proactive_priority_item_announcement"] == (
        scheduler_config.poll_interval_seconds
    )
    assert interval_for_job_id["wellness_prompt_enqueue"] == (
        wellness_config.idle_check_interval_seconds
    )
    assert interval_for_job_id["pattern_detection_pass"] == (
        learning_config.pattern_detection_interval_seconds
    )
    assert interval_for_job_id["recommendation_generation"] == (
        learning_config.recommendation_generation_interval_seconds
    )
    assert interval_for_job_id["runtime_housekeeping"] == (
        collaborators["runtime_config"].housekeeping_interval_seconds
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
    assert func_for_job_id["proactive_priority_item_announcement"] == (
        pipeline._check_and_announce_priority_item
    )
    assert func_for_job_id["wellness_prompt_enqueue"] == pipeline._maybe_enqueue_wellness_prompt
    assert func_for_job_id["pattern_detection_pass"] == (
        collaborators["pattern_recognizer"].run_detection_pass
    )
    assert func_for_job_id["recommendation_generation"] == (
        pipeline._generate_and_enqueue_recommendations
    )
    assert func_for_job_id["runtime_housekeeping"] == pipeline._run_runtime_housekeeping


def test_start_does_not_register_wellness_or_learning_jobs_when_dependencies_are_none(
    collaborators,
):
    """The None-guards in start() — see CommunicationPipeline's own
    docstring for why (a genuine Level 5 Part B construction failure,
    main.py's own null-fallback)."""
    collaborators["wellness_tracker"] = None
    collaborators["pattern_recognizer"] = None
    collaborators["recommendation_engine"] = None
    pipeline = _build_pipeline(collaborators)

    pipeline.start()

    add_job = collaborators["task_scheduler"].add_job
    registered_job_ids = {call.kwargs["job_id"] for call in add_job.call_args_list}
    assert "wellness_prompt_enqueue" not in registered_job_ids
    assert "pattern_detection_pass" not in registered_job_ids
    assert "recommendation_generation" not in registered_job_ids


# --- Runtime Phase 9 (Runtime Refactor Sprint) — _run_runtime_housekeeping() ------------


def test_run_runtime_housekeeping_always_sweeps_idle_services(pipeline, collaborators):
    pipeline._run_runtime_housekeeping()

    collaborators["runtime_manager"].sweep_idle_services.assert_called_once_with()


def test_run_runtime_housekeeping_skips_pressure_eviction_when_under_threshold(
    pipeline, collaborators
):
    collaborators["resource_monitor"].is_over_threshold.return_value = False

    pipeline._run_runtime_housekeeping()

    collaborators["runtime_manager"].evict_least_recently_used.assert_not_called()


def test_run_runtime_housekeeping_evicts_one_service_when_over_threshold(pipeline, collaborators):
    collaborators["resource_monitor"].is_over_threshold.return_value = True

    pipeline._run_runtime_housekeeping()

    collaborators["runtime_manager"].evict_least_recently_used.assert_called_once_with(1)


def test_run_runtime_housekeeping_checks_pressure_against_a_fresh_sample(pipeline, collaborators):
    snapshot = ResourceSnapshot(
        cpu_percent=10.0,
        ram_percent=20.0,
        disk_percent=30.0,
        battery_percent=None,
        timestamp=datetime.now(UTC),
    )
    collaborators["resource_monitor"].sample.return_value = snapshot

    pipeline._run_runtime_housekeeping()

    collaborators["resource_monitor"].is_over_threshold.assert_called_once_with(snapshot)


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
        "proactive_priority_item_announcement",
        "wellness_prompt_enqueue",
        "pattern_detection_pass",
        "recommendation_generation",
        "runtime_housekeeping",
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


def test_check_and_announce_priority_item_skips_when_a_session_is_active(pipeline, collaborators):
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.ACTIVE

    pipeline._check_and_announce_priority_item()

    collaborators["priority_queue_manager"].peek_next.assert_not_called()
    collaborators["quiet_mode_controller"].activate.assert_not_called()


def test_check_and_announce_priority_item_skips_when_queue_is_empty(pipeline, collaborators):
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = None

    pipeline._check_and_announce_priority_item()

    collaborators["priority_queue_manager"].pop_next.assert_not_called()
    collaborators["quiet_mode_controller"].activate.assert_not_called()


def test_check_and_announce_priority_item_skips_an_unrecognized_priority(pipeline, collaborators):
    """Sprint 6.13: _priority_item_handlers is now exhaustive over every
    real PriorityLevel member (SCHEDULED_REMINDER/WELLNESS/
    GENERAL_SUGGESTION/IMPORTANT_ALERT; CRITICAL_EMERGENCY is never
    queued at all) — no genuine PriorityLevel value can reach the
    "unrecognized" branch below any more (this test used
    PriorityLevel.IMPORTANT_ALERT for exactly that before this sprint
    gave it a real handler). A MagicMock stands in for a priority value
    that matches no real dict key, confirming the defensive fallback
    itself still works, even though nothing in this codebase can trigger
    it today."""
    peeked = MagicMock()
    peeked.priority = MagicMock(name="unrecognized_priority_level")
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = peeked

    pipeline._check_and_announce_priority_item()

    collaborators["priority_queue_manager"].pop_next.assert_not_called()
    collaborators["quiet_mode_controller"].activate.assert_not_called()


def test_check_and_announce_priority_item_announces_a_due_reminder(pipeline, collaborators):
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

    pipeline._check_and_announce_priority_item()

    collaborators["priority_queue_manager"].pop_next.assert_called_once()
    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT, announce_first=("Team standup", "p340")
    )


# --- Sprint 5.24: WELLNESS/GENERAL_SUGGESTION proactive announcement -----------


def test_check_and_announce_priority_item_announces_wellness_with_forced_switch_and_resume(
    pipeline, collaborators
):
    minie = MagicMock()
    minie.name = "minie"
    minie.voice_id = "m110"
    collaborators["persona_manager"].select.return_value = True
    collaborators["persona_manager"].active_persona.return_value = minie
    prompt = WellnessPrompt(
        trigger_type=WellnessTriggerType.BREAK,
        message="You've been active for a while — consider taking a short break.",
        triggered_at=datetime.now(UTC),
    )
    peeked = MagicMock()
    peeked.priority = PriorityLevel.WELLNESS
    popped = MagicMock()
    popped.payload = prompt
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = peeked
    collaborators["priority_queue_manager"].pop_next.return_value = popped

    pipeline._check_and_announce_priority_item()

    collaborators["persona_manager"].select.assert_called_once_with(
        "minie", SwitchReason.WELLNESS
    )
    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT, announce_first=(prompt.message, "m110")
    )
    collaborators["persona_manager"].resume_previous.assert_called_once()
    collaborators["wellness_escalation_manager"].register_prompt_shown.assert_called_once_with(
        WellnessTriggerType.BREAK
    )


def test_check_and_announce_priority_item_announces_wellness_without_resume_when_refused(
    pipeline, collaborators
):
    """select() is refused (e.g. a genuine CRITICAL_EMERGENCY is already
    active) — the announcement still goes out through whichever persona
    IS active, but resume_previous() must not be called, since nothing
    was actually switched."""
    collaborators["persona_manager"].select.return_value = False
    prompt = WellnessPrompt(
        trigger_type=WellnessTriggerType.HYDRATION,
        message="It might be a good time to drink some water.",
        triggered_at=datetime.now(UTC),
    )
    peeked = MagicMock()
    peeked.priority = PriorityLevel.WELLNESS
    popped = MagicMock()
    popped.payload = prompt
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = peeked
    collaborators["priority_queue_manager"].pop_next.return_value = popped

    pipeline._check_and_announce_priority_item()

    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT, announce_first=(prompt.message, "p340")
    )
    collaborators["persona_manager"].resume_previous.assert_not_called()


def test_check_and_announce_priority_item_announces_general_suggestion_no_switch(
    pipeline, collaborators
):
    recommendation = Recommendation(
        text="You often use devenv.exe — want me to open it next time?",
        based_on_pattern_id="pattern-1",
        generated_at=datetime.now(UTC),
    )
    peeked = MagicMock()
    peeked.priority = PriorityLevel.GENERAL_SUGGESTION
    popped = MagicMock()
    popped.payload = recommendation
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = peeked
    collaborators["priority_queue_manager"].pop_next.return_value = popped

    pipeline._check_and_announce_priority_item()

    collaborators["persona_manager"].select.assert_not_called()
    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT, announce_first=(recommendation.text, "p340")
    )


def test_maybe_enqueue_wellness_prompt_enqueues_when_a_prompt_is_produced(pipeline, collaborators):
    prompt = WellnessPrompt(
        trigger_type=WellnessTriggerType.EYE_PROTECTION, message="m", triggered_at=datetime.now(UTC)
    )
    collaborators["wellness_tracker"].evaluate_triggers.return_value = prompt

    pipeline._maybe_enqueue_wellness_prompt()

    collaborators["priority_queue_manager"].enqueue.assert_called_once_with(
        prompt, PriorityLevel.WELLNESS, source="wellness_tracker"
    )


def test_maybe_enqueue_wellness_prompt_passes_adaptive_wellness_overrides(pipeline, collaborators):
    overrides = {WellnessTriggerType.BREAK: 1.2}
    collaborators["adaptive_wellness_adjuster"].compute_overrides.return_value = overrides

    pipeline._maybe_enqueue_wellness_prompt()

    collaborators["wellness_tracker"].evaluate_triggers.assert_called_once_with(
        interval_overrides=overrides
    )


def test_maybe_enqueue_wellness_prompt_noop_when_none_produced(pipeline, collaborators):
    pipeline._maybe_enqueue_wellness_prompt()

    collaborators["priority_queue_manager"].enqueue.assert_not_called()


def test_maybe_enqueue_wellness_prompt_dedups_a_still_pending_trigger_type(pipeline, collaborators):
    """evaluate_triggers() is a pure read with no memory of its own — the
    dedup living in CommunicationPipeline is what stops a still-crossed
    trigger from being enqueued as a fresh duplicate on every poll."""
    prompt = WellnessPrompt(
        trigger_type=WellnessTriggerType.BREAK, message="m", triggered_at=datetime.now(UTC)
    )
    collaborators["wellness_tracker"].evaluate_triggers.return_value = prompt

    pipeline._maybe_enqueue_wellness_prompt()
    pipeline._maybe_enqueue_wellness_prompt()

    collaborators["priority_queue_manager"].enqueue.assert_called_once()


def test_maybe_enqueue_wellness_prompt_reenqueues_after_being_announced(pipeline, collaborators):
    """The dedup entry is cleared by _announce_wellness() once the prompt
    is actually spoken — a still-crossed trigger can legitimately fire
    again afterward."""
    prompt = WellnessPrompt(
        trigger_type=WellnessTriggerType.BREAK, message="m", triggered_at=datetime.now(UTC)
    )
    collaborators["wellness_tracker"].evaluate_triggers.return_value = prompt
    peeked = MagicMock()
    peeked.priority = PriorityLevel.WELLNESS
    popped = MagicMock()
    popped.payload = prompt
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = peeked
    collaborators["priority_queue_manager"].pop_next.return_value = popped

    pipeline._check_and_announce_priority_item()  # enqueues, then announces+clears dedup
    pipeline._maybe_enqueue_wellness_prompt()

    assert collaborators["priority_queue_manager"].enqueue.call_count == 2


def test_maybe_enqueue_wellness_prompt_noop_when_wellness_tracker_is_none(collaborators):
    collaborators["wellness_tracker"] = None
    pipeline = _build_pipeline(collaborators)

    pipeline._maybe_enqueue_wellness_prompt()

    collaborators["priority_queue_manager"].enqueue.assert_not_called()


def test_generate_and_enqueue_recommendations_enqueues_new_recommendations(pipeline, collaborators):
    recommendation = Recommendation(
        text="t", based_on_pattern_id="pattern-1", generated_at=datetime.now(UTC)
    )
    collaborators["recommendation_engine"].generate_recommendations.return_value = [recommendation]

    pipeline._generate_and_enqueue_recommendations()

    collaborators["priority_queue_manager"].enqueue.assert_called_once_with(
        recommendation, PriorityLevel.GENERAL_SUGGESTION, source="recommendation_engine"
    )


def test_generate_and_enqueue_recommendations_dedups_by_pattern_id(pipeline, collaborators):
    recommendation = Recommendation(
        text="t", based_on_pattern_id="pattern-1", generated_at=datetime.now(UTC)
    )
    collaborators["recommendation_engine"].generate_recommendations.return_value = [recommendation]

    pipeline._generate_and_enqueue_recommendations()
    pipeline._generate_and_enqueue_recommendations()

    collaborators["priority_queue_manager"].enqueue.assert_called_once()


def test_generate_and_enqueue_recommendations_noop_when_recommendation_engine_is_none(
    collaborators,
):
    collaborators["recommendation_engine"] = None
    pipeline = _build_pipeline(collaborators)

    pipeline._generate_and_enqueue_recommendations()

    collaborators["priority_queue_manager"].enqueue.assert_not_called()


# --- Sprint 5.24: EngineSelection.WELLNESS live-turn routing --------------------


def test_handle_turn_complete_routes_wellness_engine_selection(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.WELLNESS
    summary = MagicMock()
    summary.total_active_seconds = 1200.0
    collaborators["dashboard_service"].daily_summary.return_value = summary

    pipeline._handle_turn_complete("how am I doing today?", "session-1")

    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "You've been active for about 20 minute(s) today. No wellness reminders are due right now.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
    )


def test_handle_wellness_turn_reports_active_time_and_a_due_prompt(pipeline, collaborators):
    summary = MagicMock()
    summary.total_active_seconds = 1800.0
    collaborators["dashboard_service"].daily_summary.return_value = summary
    prompt = WellnessPrompt(
        trigger_type=WellnessTriggerType.BREAK,
        message="take a break",
        triggered_at=datetime.now(UTC),
    )
    collaborators["wellness_tracker"].evaluate_triggers.return_value = prompt

    reply = pipeline._handle_wellness_turn(collaborators["decision_trace"])

    assert reply == "You've been active for about 30 minute(s) today. take a break"


def test_handle_wellness_turn_reports_nothing_due_when_no_prompt(pipeline, collaborators):
    summary = MagicMock()
    summary.total_active_seconds = 600.0
    collaborators["dashboard_service"].daily_summary.return_value = summary

    reply = pipeline._handle_wellness_turn(collaborators["decision_trace"])

    assert reply == (
        "You've been active for about 10 minute(s) today. No wellness reminders are due right now."
    )


def test_handle_wellness_turn_degrades_honestly_when_no_usage_data(pipeline, collaborators):
    summary = MagicMock()
    summary.total_active_seconds = 0.0
    collaborators["dashboard_service"].daily_summary.return_value = summary

    reply = pipeline._handle_wellness_turn(collaborators["decision_trace"])

    assert reply == "I don't have enough information about today yet."


def test_handle_wellness_turn_degrades_when_wellness_tracker_is_none(collaborators):
    collaborators["wellness_tracker"] = None
    pipeline = _build_pipeline(collaborators)

    reply = pipeline._handle_wellness_turn(collaborators["decision_trace"])

    assert reply == "I don't have enough information about today yet."


def test_handle_wellness_turn_degrades_when_dashboard_service_is_none(collaborators):
    collaborators["dashboard_service"] = None
    pipeline = _build_pipeline(collaborators)

    reply = pipeline._handle_wellness_turn(collaborators["decision_trace"])

    assert reply == "I don't have enough information about today yet."


# --- Sprint 6.13: IMPORTANT_ALERT announcement + GENERAL_SUGGESTION dual payload --------


def test_announce_important_alert_speaks_a_proactive_prompt_message(pipeline, collaborators):
    item = MagicMock()
    item.payload = MagicMock(message="Your deadline is coming up.")

    pipeline._announce_important_alert(item)

    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT,
        announce_first=("Your deadline is coming up.", "p340"),
    )


def test_check_and_announce_priority_item_announces_an_important_alert(pipeline, collaborators):
    """Sprint 6.13 closes backlog/technical_debt.md item 17 in full —
    IMPORTANT_ALERT now has a real end-to-end announced path, not just a
    producer."""
    peeked = MagicMock()
    peeked.priority = PriorityLevel.IMPORTANT_ALERT
    popped = MagicMock()
    popped.payload = MagicMock(message="Battery is critically low.")
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = peeked
    collaborators["priority_queue_manager"].pop_next.return_value = popped

    pipeline._check_and_announce_priority_item()

    collaborators["priority_queue_manager"].pop_next.assert_called_once()
    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT, announce_first=("Battery is critically low.", "p340")
    )


def test_announce_general_suggestion_reads_text_from_a_recommendation_payload(
    pipeline, collaborators
):
    """The pre-6.13 producer (RecommendationEngine) — Recommendation.text."""
    item = MagicMock()
    item.payload = MagicMock(text="Consider batching your emails.")

    pipeline._announce_general_suggestion(item)

    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT,
        announce_first=("Consider batching your emails.", "p340"),
    )


def test_announce_general_suggestion_reads_message_from_a_proactive_prompt_payload(
    pipeline, collaborators
):
    """Sprint 6.13's own real, previously-latent bug fix: ProactiveAssistant's
    three softer triggers also enqueue at GENERAL_SUGGESTION, but with a
    ProactivePrompt payload (.message), not a Recommendation (.text) —
    this method used to only read .text, an AttributeError waiting to
    happen the moment ProactiveAssistant went live."""
    item = MagicMock()
    item.payload = MagicMock(message="You've been at this a while.")

    pipeline._announce_general_suggestion(item)

    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT,
        announce_first=("You've been at this a while.", "p340"),
    )


def test_announce_important_alert_falls_back_when_payload_has_no_real_text(
    pipeline, collaborators
):
    """Tested only through the public _announce_important_alert() contract
    — this codebase's own established convention never imports an
    underscore-prefixed helper (_extract_announcement_text) directly."""
    item = MagicMock()
    item.payload = object()

    pipeline._announce_important_alert(item)

    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT,
        announce_first=("You have a new item to review.", "p340"),
    )


# --- Sprint 6.13: AdaptivePrioritizer-informed dispatch ---------------------------------


def test_check_and_announce_priority_item_surfaces_now_via_adaptive_prioritizer(
    pipeline, collaborators
):
    scheduled_item = ScheduledItem(
        item_id="item-1",
        item_type=ItemType.EVENT,
        title="Team standup",
        scheduled_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    popped = MagicMock()
    popped.priority = PriorityLevel.SCHEDULED_REMINDER
    popped.payload = scheduled_item
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["context_engine"] = MagicMock()
    collaborators["adaptive_prioritizer"] = MagicMock()
    collaborators["adaptive_prioritizer"].next_item.return_value = (
        popped,
        PrioritizationDecision.SURFACE_NOW,
    )
    collaborators["priority_queue_manager"].pop_next.return_value = popped
    pipeline = _build_pipeline(collaborators)

    pipeline._check_and_announce_priority_item()

    collaborators["priority_queue_manager"].peek_next.assert_not_called()
    collaborators["priority_queue_manager"].pop_next.assert_called_once()
    collaborators["quiet_mode_controller"].activate.assert_called_once_with(
        ActivationReason.SCHEDULED_ALERT, announce_first=("Team standup", "p340")
    )


def test_check_and_announce_priority_item_defers_via_adaptive_prioritizer(
    pipeline, collaborators
):
    peeked = MagicMock()
    peeked.priority = PriorityLevel.GENERAL_SUGGESTION
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["context_engine"] = MagicMock()
    collaborators["adaptive_prioritizer"] = MagicMock()
    collaborators["adaptive_prioritizer"].next_item.return_value = (
        peeked,
        PrioritizationDecision.DEFER_BRIEFLY,
    )
    pipeline = _build_pipeline(collaborators)

    pipeline._check_and_announce_priority_item()

    collaborators["priority_queue_manager"].pop_next.assert_not_called()
    collaborators["quiet_mode_controller"].activate.assert_not_called()


def test_check_and_announce_priority_item_falls_back_to_peek_next_when_context_engine_build_fails(
    pipeline, collaborators
):
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["context_engine"] = MagicMock()
    collaborators["context_engine"].build.side_effect = RuntimeError("boom")
    collaborators["adaptive_prioritizer"] = MagicMock()
    collaborators["priority_queue_manager"].peek_next.return_value = None
    pipeline = _build_pipeline(collaborators)

    pipeline._check_and_announce_priority_item()

    collaborators["adaptive_prioritizer"].next_item.assert_not_called()
    collaborators["priority_queue_manager"].pop_next.assert_not_called()


def test_check_and_announce_priority_item_uses_plain_peek_next_when_adaptive_prioritizer_absent(
    pipeline, collaborators
):
    """The default fixture shape (context_engine/adaptive_prioritizer both
    None) — every pre-6.12 test in this file already relies on this
    exact fallback; this test makes the contract explicit."""
    collaborators["quiet_mode_controller"].current_mode.return_value = OperatingMode.DORMANT
    collaborators["priority_queue_manager"].peek_next.return_value = None

    pipeline._check_and_announce_priority_item()

    collaborators["priority_queue_manager"].peek_next.assert_called_once()


# --- Sprint 6.13: EngineSelection.PLANNING live-turn routing ----------------------------


def _with_transcript(collaborators: dict, transcript: str) -> None:
    collaborators["decision_trace"].intent = MagicMock(raw_transcript=transcript)


def _make_goal(status: PlanningStatus = PlanningStatus.PROPOSED) -> Goal:
    return Goal(
        goal_id="g1",
        statement="learn guitar",
        milestones=[
            Milestone(
                milestone_id="m1",
                title="Get a guitar",
                tasks=[
                    Task(task_id="t1", title="Buy a guitar", description="", status=status),
                ],
            ),
        ],
        created_at=datetime.now(UTC),
        status=status,
    )


def test_handle_turn_complete_routes_planning_engine_selection(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.PLANNING
    _with_transcript(collaborators, "help me plan learning guitar")
    goal = _make_goal()
    collaborators["planning_engine"].decompose_goal.return_value = goal

    pipeline._handle_turn_complete("help me plan learning guitar", "session-1")

    reply = collaborators["session_manager"].speak_reply.call_args[0][0]
    assert "learn guitar" in reply


def test_handle_planning_turn_proposes_a_fresh_goal(pipeline, collaborators):
    goal = _make_goal()
    collaborators["planning_engine"].decompose_goal.return_value = goal
    _with_transcript(collaborators, "help me plan learning guitar")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert pipeline._pending_proposed_goal is goal
    assert "learn guitar" in reply
    assert "1 milestone" in reply
    assert "1 task" in reply


def test_handle_planning_turn_degrades_on_llm_error(pipeline, collaborators):
    collaborators["planning_engine"].decompose_goal.side_effect = LlmError("unreachable")
    _with_transcript(collaborators, "help me plan learning guitar")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert pipeline._pending_proposed_goal is None
    assert reply == "I'm sorry, I couldn't work out a plan for that right now."


def test_handle_planning_turn_degrades_when_planning_engine_is_none(collaborators):
    collaborators["planning_engine"] = None
    pipeline = _build_pipeline(collaborators)
    _with_transcript(collaborators, "help me plan learning guitar")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert reply == "Planning isn't currently available."


def test_handle_planning_turn_accepts_a_pending_goal_on_yes(pipeline, collaborators):
    goal = _make_goal()
    collaborators["planning_engine"].decompose_goal.return_value = goal
    _with_transcript(collaborators, "help me plan learning guitar")
    pipeline._handle_planning_turn(collaborators["decision_trace"], "session-1", "jarvis")

    _with_transcript(collaborators, "yes")
    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert pipeline._pending_proposed_goal is None
    assert goal.status is PlanningStatus.ACCEPTED
    collaborators["task_graph_store"].save_goal.assert_called_once_with(goal)
    assert "learn guitar" in reply


def test_handle_planning_turn_accept_degrades_honestly_on_a_save_failure(
    pipeline, collaborators
):
    """Sprint 6.14 hardening (scenario b): a TaskGraphStore.save_goal()
    failure must never be silently swallowed into a false "I've saved
    your plan" claim — caught here and degraded to the exact same honest
    reply already used for the store-absent case, matching
    memory/memory_store.py's own "never claim success on a failed
    write" discipline."""
    goal = _make_goal()
    collaborators["planning_engine"].decompose_goal.return_value = goal
    _with_transcript(collaborators, "help me plan learning guitar")
    pipeline._handle_planning_turn(collaborators["decision_trace"], "session-1", "jarvis")
    collaborators["task_graph_store"].save_goal.side_effect = RuntimeError("disk full")

    _with_transcript(collaborators, "yes")
    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert pipeline._pending_proposed_goal is None
    assert reply == "I can't save that plan right now, but I'll remember it for this conversation."


def test_handle_planning_turn_rejects_a_pending_goal_on_no(pipeline, collaborators):
    goal = _make_goal()
    collaborators["planning_engine"].decompose_goal.return_value = goal
    _with_transcript(collaborators, "help me plan learning guitar")
    pipeline._handle_planning_turn(collaborators["decision_trace"], "session-1", "jarvis")

    _with_transcript(collaborators, "no")
    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert pipeline._pending_proposed_goal is None
    collaborators["task_graph_store"].save_goal.assert_not_called()
    assert reply == "Okay, I've discarded that plan."


def test_handle_turn_complete_routes_a_pending_goal_response_regardless_of_selected_engine(
    pipeline, collaborators
):
    """A bare "yes"/"no" is far too generic for decision/authority.py's
    own stateless keyword routing to ever classify as PLANNING — this
    class's own conversational state is what recognizes it instead (see
    _handle_turn_complete()'s own docstring)."""
    goal = _make_goal()
    collaborators["planning_engine"].decompose_goal.return_value = goal
    _with_transcript(collaborators, "help me plan learning guitar")
    pipeline._handle_planning_turn(collaborators["decision_trace"], "session-1", "jarvis")

    collaborators["decision_trace"].selected_engine = EngineSelection.CONVERSATIONAL_RESPONSE
    _with_transcript(collaborators, "yes")

    pipeline._handle_turn_complete("yes", "session-1")

    assert pipeline._pending_proposed_goal is None
    collaborators["task_graph_store"].save_goal.assert_called_once_with(goal)


def test_handle_planning_turn_runs_the_most_recently_accepted_plan(pipeline, collaborators):
    goal = _make_goal(status=PlanningStatus.ACCEPTED)
    collaborators["task_graph_store"].list_goals.return_value = [goal]
    collaborators["task_graph_store"].get_edges.return_value = []
    definition = MagicMock(workflow_id="wf-1")
    collaborators["task_graph_workflow_adapter"].build_workflow.return_value = (
        definition,
        [goal.milestones[0].tasks[0]],
    )
    run_result = WorkflowRunResult(
        workflow_id="wf-1",
        run_id="run-1",
        step_results=[MagicMock()],
        aborted_early=False,
        whole_workflow_confirmation=None,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    collaborators["workflow_executor"].run.return_value = run_result
    _with_transcript(collaborators, "run my plan")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    collaborators["workflow_store"].save.assert_called_once_with(definition)
    collaborators["workflow_executor"].run.assert_called_once()
    assert "learn guitar" in reply
    collaborators["self_evaluator"].evaluate_workflow_run.assert_called_once_with(run_result)


def test_handle_planning_turn_run_degrades_honestly_on_a_workflow_save_failure(
    pipeline, collaborators
):
    """Sprint 6.14 hardening (scenario b, adversarial-re-read finding):
    WorkflowStore.save() failing must never propagate to
    _handle_turn_complete()'s own outer catch and end the session."""
    goal = _make_goal(status=PlanningStatus.ACCEPTED)
    collaborators["task_graph_store"].list_goals.return_value = [goal]
    collaborators["task_graph_store"].get_edges.return_value = []
    definition = MagicMock(workflow_id="wf-1")
    collaborators["task_graph_workflow_adapter"].build_workflow.return_value = (
        definition,
        [goal.milestones[0].tasks[0]],
    )
    collaborators["workflow_store"].save.side_effect = RuntimeError("disk full")
    _with_transcript(collaborators, "run my plan")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert reply == "I couldn't set up your plan to run right now."
    collaborators["workflow_executor"].run.assert_not_called()


def test_handle_planning_turn_run_with_no_accepted_plan(pipeline, collaborators):
    collaborators["task_graph_store"].list_goals.return_value = []
    _with_transcript(collaborators, "run my plan")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert reply == "You don't have an accepted plan to run yet."


def test_handle_planning_turn_run_with_nothing_ready(pipeline, collaborators):
    goal = _make_goal(status=PlanningStatus.COMPLETED)
    collaborators["task_graph_store"].list_goals.return_value = [goal]
    collaborators["task_graph_store"].get_edges.return_value = []
    _with_transcript(collaborators, "run my plan")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert "nothing left to run" in reply
    collaborators["task_graph_workflow_adapter"].build_workflow.assert_not_called()


def test_handle_planning_turn_resumes_a_previous_session(pipeline, collaborators):
    definition = MagicMock(workflow_id="wf-2", name="Resume session: Project X")
    collaborators["session_resumption"].build_workflow.return_value = definition
    run_result = WorkflowRunResult(
        workflow_id="wf-2",
        run_id="run-2",
        step_results=[MagicMock()],
        aborted_early=False,
        whole_workflow_confirmation=None,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    collaborators["workflow_executor"].run.return_value = run_result
    _with_transcript(collaborators, "resume my session")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    collaborators["workflow_store"].save.assert_called_once_with(definition)
    assert "Resume session: Project X" in reply


def test_handle_planning_turn_resume_degrades_honestly_on_a_workflow_save_failure(
    pipeline, collaborators
):
    """Sprint 6.14 hardening (scenario b, adversarial-re-read finding):
    the identical WorkflowStore.save() gap as _run_accepted_plan()'s
    own, for the resume-session sub-flow."""
    definition = MagicMock(workflow_id="wf-2", name="Resume session: Project X")
    collaborators["session_resumption"].build_workflow.return_value = definition
    collaborators["workflow_store"].save.side_effect = RuntimeError("disk full")
    _with_transcript(collaborators, "resume my session")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert reply == "I couldn't set up your session to resume right now."
    collaborators["workflow_executor"].run.assert_not_called()


def test_handle_planning_turn_resume_with_nothing_to_resume(pipeline, collaborators):
    collaborators["session_resumption"].build_workflow.return_value = None
    _with_transcript(collaborators, "resume my session")

    reply = pipeline._handle_planning_turn(
        collaborators["decision_trace"], "session-1", "jarvis"
    )

    assert reply == "I don't have a previous session to resume."


def test_finalize_workflow_run_marks_completed_tasks_and_calls_self_evaluator(
    pipeline, collaborators
):
    goal = _make_goal(status=PlanningStatus.ACCEPTED)
    task = goal.milestones[0].tasks[0]

    task_graph = TaskGraph(goal)
    step_result = MagicMock()
    step_result.skipped = False
    step_result.action_result.status = ActionStatus.SUCCEEDED
    run_result = MagicMock()
    run_result.step_results = [step_result]

    pipeline._finalize_workflow_run(run_result, task_graph, [task], goal)

    assert task.status is PlanningStatus.COMPLETED
    collaborators["task_graph_store"].save_goal.assert_called_once_with(goal)
    collaborators["self_evaluator"].evaluate_workflow_run.assert_called_once_with(run_result)


def test_finalize_workflow_run_marks_failed_tasks(pipeline, collaborators):
    goal = _make_goal(status=PlanningStatus.ACCEPTED)
    task = goal.milestones[0].tasks[0]

    task_graph = TaskGraph(goal)
    step_result = MagicMock()
    step_result.skipped = False
    step_result.action_result.status = ActionStatus.FAILED
    run_result = MagicMock()
    run_result.step_results = [step_result]

    pipeline._finalize_workflow_run(run_result, task_graph, [task], goal)

    assert task.status is PlanningStatus.ABANDONED


def test_finalize_workflow_run_leaves_skipped_tasks_untouched(pipeline, collaborators):
    goal = _make_goal(status=PlanningStatus.ACCEPTED)
    task = goal.milestones[0].tasks[0]

    task_graph = TaskGraph(goal)
    step_result = MagicMock()
    step_result.skipped = True
    run_result = MagicMock()
    run_result.step_results = [step_result]

    pipeline._finalize_workflow_run(run_result, task_graph, [task], goal)

    assert task.status is PlanningStatus.ACCEPTED


def test_finalize_workflow_run_swallows_self_evaluator_failure(pipeline, collaborators):
    """Sprint 6.14 hardening (scenario f): a real Task's own
    mark_completed()/save_goal() already happened, in an earlier,
    separate try/except block, before SelfEvaluator.evaluate_workflow_run()
    is ever called — a failure there can never block or reverse work
    that already committed, only the evaluation itself is lost."""
    goal = _make_goal(status=PlanningStatus.ACCEPTED)
    task = goal.milestones[0].tasks[0]

    task_graph = TaskGraph(goal)
    step_result = MagicMock()
    step_result.skipped = False
    step_result.action_result.status = ActionStatus.SUCCEEDED
    run_result = MagicMock()
    run_result.step_results = [step_result]
    collaborators["self_evaluator"].evaluate_workflow_run.side_effect = RuntimeError("boom")

    pipeline._finalize_workflow_run(run_result, task_graph, [task], goal)  # must not raise

    assert task.status is PlanningStatus.COMPLETED
    collaborators["task_graph_store"].save_goal.assert_called_once_with(goal)


def test_finalize_workflow_run_still_calls_self_evaluator_after_a_save_goal_failure(
    pipeline, collaborators
):
    """Sprint 6.14 hardening (scenario f), the reverse direction: the
    two try/except blocks are genuinely independent — a failure in the
    first (task bookkeeping) does not skip the second (evaluation)
    either. In-memory task_graph.mark_completed() already ran (it's
    save_goal() that fails here, not the mutation itself), and the
    evaluation is still attempted for whatever real WorkflowRunResult
    exists, regardless of whether persistence of the bookkeeping
    succeeded."""
    goal = _make_goal(status=PlanningStatus.ACCEPTED)
    task = goal.milestones[0].tasks[0]

    task_graph = TaskGraph(goal)
    step_result = MagicMock()
    step_result.skipped = False
    step_result.action_result.status = ActionStatus.SUCCEEDED
    run_result = MagicMock()
    run_result.step_results = [step_result]
    collaborators["task_graph_store"].save_goal.side_effect = RuntimeError("disk full")

    pipeline._finalize_workflow_run(run_result, task_graph, [task], goal)  # must not raise

    assert task.status is PlanningStatus.COMPLETED  # in-memory mutation still happened
    collaborators["self_evaluator"].evaluate_workflow_run.assert_called_once_with(run_result)


# --- Sprint 6.13: EngineSelection.EXPLANATION live-turn routing --------------------------


def test_handle_turn_complete_routes_explanation_engine_selection(pipeline, collaborators):
    collaborators["decision_trace"].selected_engine = EngineSelection.EXPLANATION
    explanation = Explanation(
        subject_id="most_recent_turn",
        narrative="Because you asked to open notepad.",
        sources=["DecisionTrace"],
        confidence=None,
    )
    collaborators["explainability_layer"].explain.return_value = explanation

    pipeline._handle_turn_complete("why did you do that", "session-1")

    collaborators["session_manager"].speak_reply.assert_called_once_with(
        "Because you asked to open notepad.",
        "p340",
        on_audio_ready=pipeline._drive_lip_sync_if_avatar_mounted,
    )


def test_handle_explanation_turn_returns_the_narrative(pipeline, collaborators):
    explanation = Explanation(
        subject_id="most_recent_turn", narrative="Because X.", sources=["DecisionTrace"],
        confidence=None,
    )
    collaborators["explainability_layer"].explain.return_value = explanation

    reply = pipeline._handle_explanation_turn(collaborators["decision_trace"])

    assert reply == "Because X."


def test_handle_explanation_turn_degrades_when_explainability_layer_is_none(collaborators):
    collaborators["explainability_layer"] = None
    pipeline = _build_pipeline(collaborators)

    reply = pipeline._handle_explanation_turn(collaborators["decision_trace"])

    assert reply == "I can't explain my reasoning right now."


def test_handle_explanation_turn_uses_context_engine_when_available(pipeline, collaborators):
    collaborators["context_engine"] = MagicMock()
    pipeline = _build_pipeline(collaborators)
    explanation = Explanation(
        subject_id="most_recent_turn", narrative="Because X.", sources=["ReasoningTrace"],
        confidence=1.0,
    )
    collaborators["explainability_layer"].explain.return_value = explanation

    pipeline._handle_explanation_turn(collaborators["decision_trace"])

    collaborators["context_engine"].build.assert_called_once()


def test_handle_explanation_turn_degrades_context_build_failure_gracefully(
    pipeline, collaborators
):
    collaborators["context_engine"] = MagicMock()
    collaborators["context_engine"].build.side_effect = RuntimeError("boom")
    pipeline = _build_pipeline(collaborators)
    explanation = Explanation(
        subject_id="most_recent_turn", narrative="Because X.", sources=["DecisionTrace"],
        confidence=None,
    )
    collaborators["explainability_layer"].explain.return_value = explanation

    reply = pipeline._handle_explanation_turn(collaborators["decision_trace"])

    assert reply == "Because X."


def test_handle_explanation_turn_degrades_honestly_on_an_llm_error(pipeline, collaborators):
    """Sprint 6.14 hardening (scenario a): explain() falls through to
    ReasoningEngine.explain_why() (raises LlmError by design, 6.4) when
    _gather() finds nothing composable — previously uncaught here, which
    would have propagated to _handle_turn_complete()'s own outer catch
    and ended the whole session rather than just degrading this turn,
    mirroring _propose_new_goal()'s own already-correct identical
    shape."""
    collaborators["explainability_layer"].explain.side_effect = LlmError("unreachable")

    reply = pipeline._handle_explanation_turn(collaborators["decision_trace"])

    assert reply == "I can't reach my reasoning model right now."


def test_handle_turn_complete_survives_an_explanation_turns_llm_error(pipeline, collaborators):
    """The full, live-turn version of the test above: a real turn
    routed to EngineSelection.EXPLANATION whose explain() raises LlmError
    still produces a real spoken reply and keeps the session alive,
    rather than ending it via _handle_turn_complete()'s own outer
    catch."""
    collaborators["decision_trace"].selected_engine = EngineSelection.EXPLANATION
    collaborators["explainability_layer"].explain.side_effect = LlmError("unreachable")

    pipeline._handle_turn_complete("why did you do that", "session-1")

    collaborators["session_manager"].speak_reply.assert_called_once()
    spoken_text = collaborators["session_manager"].speak_reply.call_args[0][0]
    assert "reasoning model" in spoken_text
    collaborators["session_manager"].end_session.assert_not_called()


# --- Sprint 6.13: lookup_last_decision_trace() / _last_decision_trace tracking -----------


def test_lookup_last_decision_trace_returns_the_most_recent_turns_trace(pipeline, collaborators):
    pipeline._handle_turn_complete("open notepad", "session-1")

    assert pipeline.lookup_last_decision_trace("anything") is collaborators["decision_trace"]


def test_last_decision_trace_excludes_an_explanation_turns_own_trace(pipeline, collaborators):
    pipeline._handle_turn_complete("open notepad", "session-1")
    first_trace = pipeline._last_decision_trace

    collaborators["decision_trace"].selected_engine = EngineSelection.EXPLANATION
    collaborators["explainability_layer"].explain.return_value = Explanation(
        subject_id="most_recent_turn", narrative="Because X.", sources=["DecisionTrace"],
        confidence=None,
    )
    pipeline._handle_turn_complete("why did you do that", "session-1")

    assert pipeline._last_decision_trace is first_trace


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
# (2) _check_and_announce_priority_item() is a bare TaskScheduler job
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
def test_check_and_announce_priority_item_sweep_every_call_site_raises_by_design(
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
        pipeline._check_and_announce_priority_item()
