"""Proactive Assistant — Level 6 Part A's safe, restraint-first proactive
behavior: upcoming deadline, forgotten reminder, battery critical, long
session, missed meal, project inactivity. See
docs/sprint_book/sprint_6/sprint_6_8.md.

**Closes backlog/technical_debt.md item 17 for real, at last.**
`decision/priority_queue.py`'s `PriorityLevel.IMPORTANT_ALERT` has been
declared since Sprint 3.10 with no real periodic producer — every other
`PriorityLevel` source (`SCHEDULED_REMINDER`, `WELLNESS`,
`GENERAL_SUGGESTION`) already had one. `ProactiveAssistant` is
`IMPORTANT_ALERT`'s first real producer (`UPCOMING_DEADLINE`/
`BATTERY_CRITICAL`/`FORGOTTEN_REMINDER`); it also produces
`GENERAL_SUGGESTION` for its three softer triggers (`LONG_SESSION`/
`MISSED_MEAL`/`PROJECT_INACTIVITY`), reusing that existing PriorityLevel
rather than widening the enum.

**Enqueues, never announces, never dispatches.** `_on_tick()` only calls
`priority_queue_manager.enqueue()` — the exact same queue
`WellnessTracker`/`ReminderEngine` already feed. `voice/pipeline.py`'s
`_check_and_announce_priority_item()` already dispatches generically over
every `PriorityLevel` this Book gives a real producer to (Sprint 5.24's
own design); this sprint needs no change to that dispatch table, only a
new producer feeding it — Sprint 6.13 (Integration) makes the connection.
This module holds no reference to `ActionRegistry`/`WorkflowExecutor` at
all (see `tests/unit/proactive/test_proactive_assistant.py`'s own AST-
based proof) — a proactive prompt is an announcement, never an action.

**Two real, disclosed "accepted but not yet consumed" constructor
collaborators, the same pattern this Sprint Book has now established
repeatedly (Sprint 6.5's `DecisionEngineV2.authority_evaluator`, Sprint
6.7's optional `WorkflowStore`)**: `decision_engine_v2` is required by
this sprint's own literal Expected Classes signature, but `DecisionEngineV2`
exposes no method suited to producing a bare confidence estimate for
non-`ActionRequest` evidence (its own `rank_actions()` needs a real
`ActionRequest`; `PROJECT_INACTIVITY`'s only evidence is `Entity.
last_referenced_at`, a single timestamp with no "how many samples"
dimension for a confidence estimate to even be about) — stored, not
called, this sprint. `pattern_recognizer` is likewise accepted (optional,
per Expected Classes) but no trigger check below calls it either; neither
this sprint's own Expected Functions text nor any composed data type
names a concrete mechanism for "habit-informed threshold" adjustment.
Both are real, disclosed gaps for a future sprint (6.12 Adaptive
Prioritization, or 6.13 Integration) to actually wire, not invented here.

**Six triggers, six independent checks, one shared cooldown — no rules-
engine/plugin abstraction**: no basis in this brief for more than six
named triggers, and a generic trigger-plugin system would be real,
unrequested infrastructure for a fixed, small list. Each `_check_*()`
method returns at most one `ProactivePrompt`; `_is_cooled_down()` dedups
per `ProactiveTriggerType` only (not per specific item), the identical
shape `_maybe_enqueue_wellness_prompt()`'s own Sprint 5.24 precedent
already established for WellnessTracker's own inherently-singular
triggers.

**Two real, disclosed design decisions this sprint file's own text left
without a concrete formula, both resolved directly**:

1. `LONG_SESSION` is measured as total *logged active time* across
   `WorkingContext.recent_applications` within `ContextEngine`'s own
   bounded `usage_lookback_hours` window (each session's own
   `ended_at - started_at`, summed) — not strict single-unbroken-block
   contiguity. `UsageSession` carries no gap/break information beyond
   its own `started_at`/`ended_at`, and no gap-tolerance constant is
   named anywhere in this sprint's own `ProactiveConfig` — summing real
   logged active time within the bounded window is the honest, buildable
   proxy this data actually supports. A disclosed limitation, matching
   this sprint file's own Potential Risks framing: a burst of activity
   from earlier in the lookback window, followed by the user stepping
   away, still reads as "long session" until it ages out of that window.
2. `MISSED_MEAL`'s "no qualifying break detected" uses a real, disclosed,
   unvalidated local constant (`_QUALIFYING_BREAK_SECONDS`, 15 minutes)
   as the minimum gap between two consecutive sessions overlapping the
   configured meal window that counts as "the user stepped away" — not
   promoted to `ProactiveConfig` since this sprint file's own Files to
   Modify names no such field, the same "real, disclosed, unvalidated
   first-pass constant" treatment every comparable tuned value in this
   codebase already carries when no config surface was named for it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from config.schema import ProactiveConfig
from core.logging_setup import get_logger
from decision.priority_queue import PriorityLevel, PriorityQueueManager
from knowledge.knowledge_model import EntityType
from proactive.proactive_model import ProactivePrompt, ProactiveTriggerType
from scheduler.scheduler_model import ItemType
from scheduler.task_scheduler import TaskScheduler

if TYPE_CHECKING:
    from context.context_engine import ContextEngine
    from context.context_model import WorkingContext
    from decision.decision_engine_v2 import DecisionEngineV2
    from knowledge.knowledge_graph_store import KnowledgeGraphStore
    from learning.pattern_recognizer import PatternRecognizer

logger = get_logger(__name__)

_JOB_ID = "proactive_assistant_evaluation"
_BACKGROUND_TICK_SESSION_ID = "proactive-assistant-tick"
"""Sprint 6.13 (Integration) correction to a real, previously-latent bug,
found only once a real ContextEngine was ever actually wired in (this
sprint is the first live caller): ContextEngine.build() requires
session_id/active_persona_name (no defaults), but this class's own
_evaluate_triggers() previously called it with zero arguments — every
existing unit test faked context_engine as a plain mock, which accepts
any call signature, so this was never actually exercised against the
real method before now. ProactiveAssistant runs as a background tick with
no live session/persona of its own to reference at all (the identical
"no real session exists at this call site" problem
CommunicationPipiline._check_and_announce_priority_item() independently
also has — see that method's own _last_session_id docstring); a fixed,
self-documenting sentinel session_id and a plain default persona name are
the honest placeholders available, matching ConversationSessionStore.
get_recent_turns()'s own "an unknown session_id just returns []" harmless
behavior."""
_BACKGROUND_TICK_PERSONA_NAME = "jarvis"

_TRIGGER_PRIORITIES: dict[ProactiveTriggerType, PriorityLevel] = {
    ProactiveTriggerType.UPCOMING_DEADLINE: PriorityLevel.IMPORTANT_ALERT,
    ProactiveTriggerType.FORGOTTEN_REMINDER: PriorityLevel.IMPORTANT_ALERT,
    ProactiveTriggerType.BATTERY_CRITICAL: PriorityLevel.IMPORTANT_ALERT,
    ProactiveTriggerType.LONG_SESSION: PriorityLevel.GENERAL_SUGGESTION,
    ProactiveTriggerType.MISSED_MEAL: PriorityLevel.GENERAL_SUGGESTION,
    ProactiveTriggerType.PROJECT_INACTIVITY: PriorityLevel.GENERAL_SUGGESTION,
}

_QUALIFYING_BREAK_SECONDS = 900.0
"""15 minutes — see this module's own docstring, design decision (2)."""


class ProactiveAssistant:
    """Constructor DI: (task_scheduler, priority_queue_manager,
    context_engine, decision_engine_v2, knowledge_graph_store=None,
    pattern_recognizer=None, proactive_config). knowledge_graph_store/
    pattern_recognizer are optional — PROJECT_INACTIVITY (and any future
    habit-informed adjustment) degrades to silence, never a crash or
    fabricated urgency, when either is absent. A real ManagedModule:
    start()/stop() register/remove one TaskScheduler job, matching
    WellnessTracker's own established shape exactly."""

    def __init__(
        self,
        task_scheduler: TaskScheduler,
        priority_queue_manager: PriorityQueueManager,
        context_engine: ContextEngine,
        decision_engine_v2: DecisionEngineV2,
        knowledge_graph_store: KnowledgeGraphStore | None,
        pattern_recognizer: PatternRecognizer | None,
        proactive_config: ProactiveConfig,
    ) -> None:
        self._task_scheduler = task_scheduler
        self._priority_queue_manager = priority_queue_manager
        self._context_engine = context_engine
        self._decision_engine_v2 = decision_engine_v2
        self._knowledge_graph_store = knowledge_graph_store
        self._pattern_recognizer = pattern_recognizer
        self._config = proactive_config
        self._started = False
        self._last_fired_at: dict[ProactiveTriggerType, datetime] = {}

    def start(self) -> None:
        self._task_scheduler.add_job(
            self._on_tick, self._config.evaluation_interval_seconds, job_id=_JOB_ID
        )
        self._started = True
        logger.info(
            "Proactive assistant started (evaluation_interval_seconds=%s).",
            self._config.evaluation_interval_seconds,
        )

    def stop(self) -> None:
        self._task_scheduler.remove_job(_JOB_ID)
        self._started = False
        logger.info("Proactive assistant stopped.")

    def health_check(self) -> bool:
        return self._started

    def _on_tick(self) -> None:
        for prompt in self._evaluate_triggers():
            if not self._is_cooled_down(prompt.trigger_type):
                continue
            self._priority_queue_manager.enqueue(
                prompt, prompt.priority, source="proactive_assistant"
            )
            self._last_fired_at[prompt.trigger_type] = datetime.now(UTC)
            logger.info("Proactive prompt enqueued: %s", prompt.trigger_type.value)

    def _evaluate_triggers(self, now: datetime | None = None) -> list[ProactivePrompt]:
        """Builds one real WorkingContext, then checks all six triggers
        against it — a pure function of that snapshot (plus, for
        PROJECT_INACTIVITY, a real knowledge_graph_store read), directly
        callable in tests independent of the timer. now defaults to the
        real current time in production; tests pass an explicit value —
        the identical "deliberately callable directly in tests,
        independent of the timer" shape WellnessTracker.evaluate_triggers()
        already established, including its own "a real late-night test
        run can never make an unrelated boundary test flaky" reasoning."""
        working_context = self._context_engine.build(
            _BACKGROUND_TICK_SESSION_ID, _BACKGROUND_TICK_PERSONA_NAME
        )
        now = now if now is not None else datetime.now(UTC)
        checks = (
            self._check_upcoming_deadline,
            self._check_forgotten_reminder,
            self._check_battery_critical,
            self._check_long_session,
            self._check_missed_meal,
            self._check_project_inactivity,
        )
        prompts: list[ProactivePrompt] = []
        for check in checks:
            prompt = check(working_context, now)
            if prompt is not None:
                prompts.append(prompt)
        return prompts

    def _is_cooled_down(self, trigger_type: ProactiveTriggerType) -> bool:
        """True when trigger_type is allowed to fire again — never fired
        before, or trigger_cooldown_seconds has elapsed since it last
        did. Mirrors _maybe_enqueue_wellness_prompt()'s own per-trigger-
        type (not per-item) in-memory dedup precedent (Sprint 5.24)."""
        last_fired = self._last_fired_at.get(trigger_type)
        if last_fired is None:
            return True
        elapsed = (datetime.now(UTC) - last_fired).total_seconds()
        return elapsed >= self._config.trigger_cooldown_seconds

    def _check_upcoming_deadline(
        self, working_context: WorkingContext, now: datetime
    ) -> ProactivePrompt | None:
        warning_window_end = now + timedelta(hours=self._config.deadline_warning_hours)
        candidates = [
            item
            for item in working_context.upcoming_scheduled_items
            if item.item_type is ItemType.DEADLINE
            and not item.is_completed
            and now <= item.scheduled_at <= warning_window_end
        ]
        if not candidates:
            return None
        soonest = min(candidates, key=lambda item: item.scheduled_at)
        return ProactivePrompt(
            trigger_type=ProactiveTriggerType.UPCOMING_DEADLINE,
            message=f"'{soonest.title}' is due soon.",
            priority=_TRIGGER_PRIORITIES[ProactiveTriggerType.UPCOMING_DEADLINE],
            evaluated_at=now,
        )

    def _check_forgotten_reminder(
        self, working_context: WorkingContext, now: datetime
    ) -> ProactivePrompt | None:
        candidates = [
            item
            for item in working_context.upcoming_scheduled_items
            if not item.is_completed and item.scheduled_at < now
        ]
        if not candidates:
            return None
        most_overdue = min(candidates, key=lambda item: item.scheduled_at)
        return ProactivePrompt(
            trigger_type=ProactiveTriggerType.FORGOTTEN_REMINDER,
            message=f"You may have forgotten: '{most_overdue.title}'.",
            priority=_TRIGGER_PRIORITIES[ProactiveTriggerType.FORGOTTEN_REMINDER],
            evaluated_at=now,
        )

    def _check_battery_critical(
        self, working_context: WorkingContext, now: datetime
    ) -> ProactivePrompt | None:
        resource_status = working_context.resource_status
        if resource_status is None or resource_status.battery_percent is None:
            return None
        if resource_status.battery_percent > self._config.battery_critical_percent:
            return None
        return ProactivePrompt(
            trigger_type=ProactiveTriggerType.BATTERY_CRITICAL,
            message=f"Battery is critically low ({resource_status.battery_percent:.0f}%).",
            priority=_TRIGGER_PRIORITIES[ProactiveTriggerType.BATTERY_CRITICAL],
            evaluated_at=now,
        )

    def _check_long_session(
        self, working_context: WorkingContext, now: datetime
    ) -> ProactivePrompt | None:
        sessions = working_context.recent_applications
        if not sessions:
            return None
        total_active_seconds = sum(
            (session.ended_at - session.started_at).total_seconds() for session in sessions
        )
        threshold_seconds = self._config.long_session_hours * 3600.0
        if total_active_seconds < threshold_seconds:
            return None
        hours = total_active_seconds / 3600.0
        return ProactivePrompt(
            trigger_type=ProactiveTriggerType.LONG_SESSION,
            message=f"You've been active for about {hours:.1f} hours — consider a break.",
            priority=_TRIGGER_PRIORITIES[ProactiveTriggerType.LONG_SESSION],
            evaluated_at=now,
        )

    def _check_missed_meal(
        self, working_context: WorkingContext, now: datetime
    ) -> ProactivePrompt | None:
        if not (
            self._config.missed_meal_window_start_hour
            <= now.hour
            < self._config.missed_meal_window_end_hour
        ):
            return None
        window_start = now.replace(
            hour=self._config.missed_meal_window_start_hour, minute=0, second=0, microsecond=0
        )
        window_end = now.replace(
            hour=self._config.missed_meal_window_end_hour, minute=0, second=0, microsecond=0
        )
        sessions = sorted(
            (
                session
                for session in working_context.recent_applications
                if session.ended_at >= window_start and session.started_at <= window_end
            ),
            key=lambda session: session.started_at,
        )
        for earlier, later in zip(sessions, sessions[1:], strict=False):
            gap_seconds = (later.started_at - earlier.ended_at).total_seconds()
            if gap_seconds >= _QUALIFYING_BREAK_SECONDS:
                return None
        return ProactivePrompt(
            trigger_type=ProactiveTriggerType.MISSED_MEAL,
            message="You may have missed a meal — no break detected during your usual window.",
            priority=_TRIGGER_PRIORITIES[ProactiveTriggerType.MISSED_MEAL],
            evaluated_at=now,
        )

    def _check_project_inactivity(
        self, working_context: WorkingContext, now: datetime
    ) -> ProactivePrompt | None:
        if self._knowledge_graph_store is None:
            return None
        projects = self._knowledge_graph_store.find_entities(entity_type=EntityType.PROJECT)
        threshold = timedelta(days=self._config.project_inactivity_days)
        stale_projects = [
            project for project in projects if now - project.last_referenced_at >= threshold
        ]
        if not stale_projects:
            return None
        most_stale = min(stale_projects, key=lambda project: project.last_referenced_at)
        return ProactivePrompt(
            trigger_type=ProactiveTriggerType.PROJECT_INACTIVITY,
            message=f"'{most_stale.name}' hasn't been touched in a while.",
            priority=_TRIGGER_PRIORITIES[ProactiveTriggerType.PROJECT_INACTIVITY],
            evaluated_at=now,
            subject_entity_id=most_stale.entity_id,
        )
