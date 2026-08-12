"""Unit tests for proactive.proactive_assistant.

_evaluate_triggers() is exercised directly against a fake ContextEngine
(this sprint file's own Expected Functions names it with a leading
underscore — the one deliberate exception to this codebase's usual
"never import a private helper by name" convention, since it is the only
way to test each of the six triggers independently of _on_tick()'s own
enqueue/cooldown side effects). start()/stop() are exercised against a
REAL TaskScheduler with a fast interval, matching tests/unit/wellness/
test_wellness_tracker.py's own established "real collaborator, short
interval, bounded poll-until wait" precedent.
"""

import ast
import os
import time
from datetime import UTC, datetime, timedelta

from analytics.usage_model import UsageSession
from config.schema import ProactiveConfig
from context.context_model import WorkingContext
from core.resource_monitor import ResourceSnapshot
from decision.priority_queue import PriorityLevel
from knowledge.knowledge_model import Entity, EntityType
from proactive.proactive_assistant import ProactiveAssistant
from proactive.proactive_model import ProactiveTriggerType
from scheduler.scheduler_model import ItemType, ScheduledItem
from scheduler.task_scheduler import TaskScheduler

_NOW = datetime(2026, 8, 9, 13, 0, 0, tzinfo=UTC)  # 13:00 -- inside the default [12, 14) window

_UNUSED_DECISION_ENGINE_V2 = object()
"""A bare sentinel — ProactiveAssistant never calls a method on
decision_engine_v2 this sprint (see proactive_assistant.py's own
docstring), so a real DecisionEngineV2 instance is unnecessary here."""


class FakeContextEngine:
    def __init__(self, working_context: WorkingContext) -> None:
        self._working_context = working_context
        self.build_calls: list[tuple[str, str]] = []

    def build(self, session_id: str, active_persona_name: str) -> WorkingContext:
        """Sprint 6.13 correction: the real ContextEngine.build() requires
        session_id/active_persona_name (no defaults) — this fake used to
        accept zero arguments, silently matching a real bug in
        _evaluate_triggers()'s own call site rather than the real
        method's actual contract. Both are recorded, not just accepted,
        so a test can confirm ProactiveAssistant's own real background-
        tick placeholders are what's actually passed."""
        self.build_calls.append((session_id, active_persona_name))
        return self._working_context


class FakePriorityQueueManager:
    def __init__(self) -> None:
        self.enqueued: list[tuple[object, PriorityLevel, str]] = []

    def enqueue(self, payload: object, priority: PriorityLevel, source: str) -> None:
        self.enqueued.append((payload, priority, source))


class FakeKnowledgeGraphStore:
    def __init__(self, entities: list[Entity]) -> None:
        self._entities = entities

    def find_entities(
        self, entity_type: EntityType | None = None, name_contains: str | None = None
    ) -> list[Entity]:
        return [e for e in self._entities if entity_type is None or e.entity_type is entity_type]


def _working_context(
    upcoming_scheduled_items: list[ScheduledItem] | None = None,
    resource_status: ResourceSnapshot | None = None,
    recent_applications: list[UsageSession] | None = None,
) -> WorkingContext:
    return WorkingContext(
        built_at=_NOW,
        conversation=None,
        recent_memories=[],
        recent_applications=recent_applications or [],
        upcoming_scheduled_items=upcoming_scheduled_items or [],
        resource_status=resource_status,
    )


def _assistant(
    working_context: WorkingContext,
    task_scheduler: TaskScheduler | None = None,
    knowledge_graph_store=None,
    pattern_recognizer=None,
    **config_overrides,
) -> tuple[ProactiveAssistant, FakePriorityQueueManager]:
    task_scheduler = task_scheduler if task_scheduler is not None else TaskScheduler()
    priority_queue_manager = FakePriorityQueueManager()
    config = ProactiveConfig(**config_overrides)
    assistant = ProactiveAssistant(
        task_scheduler,
        priority_queue_manager,
        FakeContextEngine(working_context),
        _UNUSED_DECISION_ENGINE_V2,
        knowledge_graph_store,
        pattern_recognizer,
        config,
    )
    return assistant, priority_queue_manager


def _session(
    started_at: datetime, ended_at: datetime, process_name: str = "code.exe"
) -> UsageSession:
    return UsageSession(
        process_name=process_name,
        category=None,
        started_at=started_at,
        ended_at=ended_at,
        sample_count=1,
    )


# --- UPCOMING_DEADLINE ---------------------------------------------------------------------


def test_upcoming_deadline_fires_within_the_warning_window():
    item = ScheduledItem(
        item_id="d1",
        item_type=ItemType.DEADLINE,
        title="Ship the release",
        scheduled_at=_NOW + timedelta(hours=5),
        created_at=_NOW,
    )
    assistant, _ = _assistant(
        _working_context(upcoming_scheduled_items=[item]), deadline_warning_hours=24.0
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    matches = [p for p in prompts if p.trigger_type is ProactiveTriggerType.UPCOMING_DEADLINE]
    assert len(matches) == 1
    assert matches[0].priority is PriorityLevel.IMPORTANT_ALERT
    assert "Ship the release" in matches[0].message


def test_upcoming_deadline_does_not_fire_beyond_the_warning_window():
    item = ScheduledItem(
        item_id="d1",
        item_type=ItemType.DEADLINE,
        title="Ship the release",
        scheduled_at=_NOW + timedelta(hours=48),
        created_at=_NOW,
    )
    assistant, _ = _assistant(
        _working_context(upcoming_scheduled_items=[item]), deadline_warning_hours=24.0
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.UPCOMING_DEADLINE for p in prompts)


def test_upcoming_deadline_ignores_a_completed_deadline():
    item = ScheduledItem(
        item_id="d1",
        item_type=ItemType.DEADLINE,
        title="Ship the release",
        scheduled_at=_NOW + timedelta(hours=5),
        created_at=_NOW,
        is_completed=True,
    )
    assistant, _ = _assistant(_working_context(upcoming_scheduled_items=[item]))

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.UPCOMING_DEADLINE for p in prompts)


def test_upcoming_deadline_ignores_a_non_deadline_event():
    item = ScheduledItem(
        item_id="e1",
        item_type=ItemType.EVENT,
        title="Team sync",
        scheduled_at=_NOW + timedelta(hours=5),
        created_at=_NOW,
    )
    assistant, _ = _assistant(_working_context(upcoming_scheduled_items=[item]))

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.UPCOMING_DEADLINE for p in prompts)


# --- FORGOTTEN_REMINDER -----------------------------------------------------------------------


def test_forgotten_reminder_fires_for_an_overdue_incomplete_item():
    item = ScheduledItem(
        item_id="r1",
        item_type=ItemType.EVENT,
        title="Call the vet",
        scheduled_at=_NOW - timedelta(hours=2),
        created_at=_NOW - timedelta(days=1),
    )
    assistant, _ = _assistant(_working_context(upcoming_scheduled_items=[item]))

    prompts = assistant._evaluate_triggers(now=_NOW)

    matches = [p for p in prompts if p.trigger_type is ProactiveTriggerType.FORGOTTEN_REMINDER]
    assert len(matches) == 1
    assert matches[0].priority is PriorityLevel.IMPORTANT_ALERT
    assert "Call the vet" in matches[0].message


def test_forgotten_reminder_does_not_fire_for_a_future_item():
    item = ScheduledItem(
        item_id="r1",
        item_type=ItemType.EVENT,
        title="Call the vet",
        scheduled_at=_NOW + timedelta(hours=2),
        created_at=_NOW,
    )
    assistant, _ = _assistant(_working_context(upcoming_scheduled_items=[item]))

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.FORGOTTEN_REMINDER for p in prompts)


def test_forgotten_reminder_ignores_an_overdue_but_completed_item():
    item = ScheduledItem(
        item_id="r1",
        item_type=ItemType.EVENT,
        title="Call the vet",
        scheduled_at=_NOW - timedelta(hours=2),
        created_at=_NOW - timedelta(days=1),
        is_completed=True,
    )
    assistant, _ = _assistant(_working_context(upcoming_scheduled_items=[item]))

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.FORGOTTEN_REMINDER for p in prompts)


# --- BATTERY_CRITICAL ---------------------------------------------------------------------


def test_battery_critical_fires_at_or_below_the_threshold():
    resource_status = ResourceSnapshot(
        cpu_percent=10.0, ram_percent=10.0, disk_percent=10.0, battery_percent=10.0, timestamp=_NOW
    )
    assistant, _ = _assistant(
        _working_context(resource_status=resource_status), battery_critical_percent=15.0
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    matches = [p for p in prompts if p.trigger_type is ProactiveTriggerType.BATTERY_CRITICAL]
    assert len(matches) == 1
    assert matches[0].priority is PriorityLevel.IMPORTANT_ALERT


def test_battery_critical_does_not_fire_above_the_threshold():
    resource_status = ResourceSnapshot(
        cpu_percent=10.0, ram_percent=10.0, disk_percent=10.0, battery_percent=50.0, timestamp=_NOW
    )
    assistant, _ = _assistant(
        _working_context(resource_status=resource_status), battery_critical_percent=15.0
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.BATTERY_CRITICAL for p in prompts)


def test_battery_critical_does_not_fire_when_resource_status_is_none():
    assistant, _ = _assistant(_working_context(resource_status=None))

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.BATTERY_CRITICAL for p in prompts)


def test_battery_critical_does_not_fire_on_a_desktop_with_no_battery():
    resource_status = ResourceSnapshot(
        cpu_percent=10.0, ram_percent=10.0, disk_percent=10.0, battery_percent=None, timestamp=_NOW
    )
    assistant, _ = _assistant(_working_context(resource_status=resource_status))

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.BATTERY_CRITICAL for p in prompts)


# --- LONG_SESSION --------------------------------------------------------------------------


def test_long_session_fires_once_total_active_time_clears_the_threshold():
    sessions = [
        _session(_NOW - timedelta(hours=4), _NOW - timedelta(hours=2)),
        _session(_NOW - timedelta(hours=2), _NOW),
    ]
    assistant, _ = _assistant(
        _working_context(recent_applications=sessions), long_session_hours=3.0
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    matches = [p for p in prompts if p.trigger_type is ProactiveTriggerType.LONG_SESSION]
    assert len(matches) == 1
    assert matches[0].priority is PriorityLevel.GENERAL_SUGGESTION


def test_long_session_does_not_fire_below_the_threshold():
    sessions = [_session(_NOW - timedelta(hours=1), _NOW)]
    assistant, _ = _assistant(
        _working_context(recent_applications=sessions), long_session_hours=3.0
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.LONG_SESSION for p in prompts)


def test_long_session_does_not_fire_with_no_recent_applications():
    assistant, _ = _assistant(_working_context(recent_applications=[]))

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.LONG_SESSION for p in prompts)


# --- MISSED_MEAL -----------------------------------------------------------------------------


def test_missed_meal_fires_with_continuous_activity_through_the_window_and_no_break():
    sessions = [
        _session(_NOW.replace(hour=12, minute=0), _NOW.replace(hour=12, minute=50)),
        _session(_NOW.replace(hour=12, minute=55), _NOW.replace(hour=13, minute=45)),
    ]
    assistant, _ = _assistant(_working_context(recent_applications=sessions))

    prompts = assistant._evaluate_triggers(now=_NOW)

    matches = [p for p in prompts if p.trigger_type is ProactiveTriggerType.MISSED_MEAL]
    assert len(matches) == 1
    assert matches[0].priority is PriorityLevel.GENERAL_SUGGESTION


def test_missed_meal_does_not_fire_when_a_qualifying_break_is_detected():
    sessions = [
        _session(_NOW.replace(hour=12, minute=0), _NOW.replace(hour=12, minute=30)),
        # A 30-minute gap between 12:30 and 13:00 -- a real, detected break.
        _session(_NOW.replace(hour=13, minute=0), _NOW.replace(hour=13, minute=45)),
    ]
    assistant, _ = _assistant(_working_context(recent_applications=sessions))

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.MISSED_MEAL for p in prompts)


def test_missed_meal_does_not_fire_outside_the_configured_window():
    # _NOW itself is 13:00 -- narrow the configured window so it falls outside instead.
    context = _working_context(
        recent_applications=[_session(_NOW.replace(hour=9), _NOW.replace(hour=10))]
    )
    assistant, _ = _assistant(
        context, missed_meal_window_start_hour=20, missed_meal_window_end_hour=21
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.MISSED_MEAL for p in prompts)


# --- PROJECT_INACTIVITY --------------------------------------------------------------------


def test_project_inactivity_fires_for_a_stale_project():
    entity = Entity(
        entity_id="p1",
        entity_type=EntityType.PROJECT,
        name="JARMINEI",
        created_at=_NOW - timedelta(days=30),
        last_referenced_at=_NOW - timedelta(days=10),
    )
    assistant, _ = _assistant(
        _working_context(),
        knowledge_graph_store=FakeKnowledgeGraphStore([entity]),
        project_inactivity_days=7,
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    matches = [p for p in prompts if p.trigger_type is ProactiveTriggerType.PROJECT_INACTIVITY]
    assert len(matches) == 1
    assert matches[0].priority is PriorityLevel.GENERAL_SUGGESTION
    assert matches[0].subject_entity_id == "p1"


def test_project_inactivity_does_not_fire_for_a_recently_referenced_project():
    entity = Entity(
        entity_id="p1",
        entity_type=EntityType.PROJECT,
        name="JARMINEI",
        created_at=_NOW - timedelta(days=30),
        last_referenced_at=_NOW - timedelta(days=1),
    )
    assistant, _ = _assistant(
        _working_context(),
        knowledge_graph_store=FakeKnowledgeGraphStore([entity]),
        project_inactivity_days=7,
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.PROJECT_INACTIVITY for p in prompts)


def test_project_inactivity_degrades_to_silence_when_knowledge_graph_store_is_none():
    assistant, _ = _assistant(_working_context(), knowledge_graph_store=None)

    prompts = assistant._evaluate_triggers(now=_NOW)  # must not raise

    assert not any(p.trigger_type is ProactiveTriggerType.PROJECT_INACTIVITY for p in prompts)


def test_project_inactivity_ignores_non_project_entities():
    entity = Entity(
        entity_id="g1",
        entity_type=EntityType.GOAL,
        name="Learn to code",
        created_at=_NOW - timedelta(days=30),
        last_referenced_at=_NOW - timedelta(days=30),
    )
    assistant, _ = _assistant(
        _working_context(),
        knowledge_graph_store=FakeKnowledgeGraphStore([entity]),
        project_inactivity_days=7,
    )

    prompts = assistant._evaluate_triggers(now=_NOW)

    assert not any(p.trigger_type is ProactiveTriggerType.PROJECT_INACTIVITY for p in prompts)


# --- cooldown --------------------------------------------------------------------------------


def test_on_tick_does_not_re_enqueue_a_still_true_trigger_within_the_cooldown():
    resource_status = ResourceSnapshot(
        cpu_percent=10.0, ram_percent=10.0, disk_percent=10.0, battery_percent=5.0, timestamp=_NOW
    )
    assistant, priority_queue_manager = _assistant(
        _working_context(resource_status=resource_status), trigger_cooldown_seconds=3600.0
    )

    assistant._on_tick()
    assistant._on_tick()

    battery_enqueues = [
        e
        for e in priority_queue_manager.enqueued
        if e[0].trigger_type is ProactiveTriggerType.BATTERY_CRITICAL
    ]
    assert len(battery_enqueues) == 1


def test_on_tick_re_enqueues_after_the_cooldown_expires():
    resource_status = ResourceSnapshot(
        cpu_percent=10.0, ram_percent=10.0, disk_percent=10.0, battery_percent=5.0, timestamp=_NOW
    )
    assistant, priority_queue_manager = _assistant(
        _working_context(resource_status=resource_status), trigger_cooldown_seconds=3600.0
    )

    assistant._on_tick()
    assistant._last_fired_at[ProactiveTriggerType.BATTERY_CRITICAL] = datetime.now(UTC) - timedelta(
        seconds=3601
    )
    assistant._on_tick()

    battery_enqueues = [
        e
        for e in priority_queue_manager.enqueued
        if e[0].trigger_type is ProactiveTriggerType.BATTERY_CRITICAL
    ]
    assert len(battery_enqueues) == 2


def test_on_tick_enqueues_at_the_prompts_own_priority_and_source():
    resource_status = ResourceSnapshot(
        cpu_percent=10.0, ram_percent=10.0, disk_percent=10.0, battery_percent=5.0, timestamp=_NOW
    )
    assistant, priority_queue_manager = _assistant(
        _working_context(resource_status=resource_status)
    )

    assistant._on_tick()

    payload, priority, source = priority_queue_manager.enqueued[0]
    assert priority is PriorityLevel.IMPORTANT_ALERT
    assert source == "proactive_assistant"
    assert payload.trigger_type is ProactiveTriggerType.BATTERY_CRITICAL


# --- start()/stop()/health_check() against a real TaskScheduler --------------------------


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_health_check_false_before_start():
    assistant, _ = _assistant(_working_context())
    assert assistant.health_check() is False


def test_start_registers_exactly_one_job_that_ticks(monkeypatch):
    task_scheduler = TaskScheduler()
    task_scheduler.start()
    assistant, _ = _assistant(
        _working_context(), task_scheduler=task_scheduler, evaluation_interval_seconds=0.05
    )
    tick_count = 0

    def _counting_tick():
        nonlocal tick_count
        tick_count += 1

    monkeypatch.setattr(assistant, "_on_tick", _counting_tick)

    assistant.start()
    try:
        assert assistant.health_check() is True
        assert _wait_until(lambda: tick_count > 0)
    finally:
        assistant.stop()
        task_scheduler.stop()


class _AlwaysRaisingContextEngine:
    """Sprint 6.14 hardening (scenario c): a real ContextEngine.build()
    failure would propagate straight out of _evaluate_triggers() with no
    try/except of its own (by design — see this module's own docstring,
    "no try/except of its own, absorbed by TaskScheduler"). This double
    forces every single tick to raise, to confirm that absorption is
    real for THIS specific job, not merely assumed to transfer from
    scheduler/task_scheduler.py's own docstring claim (verified there
    for a different job, Sprint 4.15/4.18)."""

    def build(self, session_id: str, active_persona_name: str) -> WorkingContext:
        raise RuntimeError("ContextEngine.build() exploded")


def test_a_raising_tick_does_not_stop_future_recurrence(monkeypatch):
    task_scheduler = TaskScheduler()
    task_scheduler.start()
    priority_queue_manager = FakePriorityQueueManager()
    assistant = ProactiveAssistant(
        task_scheduler,
        priority_queue_manager,
        _AlwaysRaisingContextEngine(),
        _UNUSED_DECISION_ENGINE_V2,
        None,
        None,
        ProactiveConfig(evaluation_interval_seconds=0.05),
    )
    tick_count = 0
    real_on_tick = assistant._on_tick

    def _counting_tick():
        nonlocal tick_count
        tick_count += 1
        real_on_tick()  # genuinely raises inside here; APScheduler must absorb it

    monkeypatch.setattr(assistant, "_on_tick", _counting_tick)

    assistant.start()
    try:
        assert _wait_until(lambda: tick_count >= 3)
        assert assistant.health_check() is True  # the job itself is still alive
    finally:
        assistant.stop()
        task_scheduler.stop()


def test_stop_removes_the_job_and_no_further_ticks_occur(monkeypatch):
    task_scheduler = TaskScheduler()
    task_scheduler.start()
    assistant, _ = _assistant(
        _working_context(), task_scheduler=task_scheduler, evaluation_interval_seconds=0.05
    )
    tick_count = 0

    def _counting_tick():
        nonlocal tick_count
        tick_count += 1

    monkeypatch.setattr(assistant, "_on_tick", _counting_tick)

    assistant.start()
    assert _wait_until(lambda: tick_count > 0)
    assistant.stop()
    count_after_stop = tick_count
    time.sleep(0.2)

    assert tick_count == count_after_stop
    assert assistant.health_check() is False
    task_scheduler.stop()


# --- static: never imports an executor-capable module -------------------------------------


def test_proactive_assistant_module_imports_no_executor_module():
    """AST-based, not a substring scan — mirrors tests/unit/learning/
    test_recommendation.py's own import-boundary check precedent.
    Confirms proactive/proactive_assistant.py never imports ActionRegistry/
    WorkflowExecutor's own modules — this module enqueues announcements,
    it structurally cannot dispatch or execute anything."""
    module_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "proactive", "proactive_assistant.py"
    )
    with open(module_path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=module_path)

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    assert "device_control.action_engine" not in imported_modules
    assert "workflow.workflow_executor" not in imported_modules
