"""Reminder Engine — turns CalendarStore's (4.14) stored items into
real, time-driven reminders. See docs/sprint_book/sprint_4_15.md.

Enqueues due items onto PriorityQueueManager (3.10) at
PriorityLevel.SCHEDULED_REMINDER — it does NOT itself decide when to
interrupt the user, drive QuietModeController, or speak. Keeping
scheduler/ from reaching into voice/ preserves the same dependency
direction discipline workflow/ -> device_control/ already established
(see docs/sprint_book/INDEX.md's Recommendations section). The "pop the
queue and speak, respecting Quiet Mode" consumer is Sprint 4.18's job —
after this sprint, a reminder can be scheduled, become due, and get
enqueued, but nothing yet announces it.

_enqueued_item_ids is deliberately in-memory-only, not persisted — a
process restart forgets which due items were already enqueued, so a
still-pending reminder gets enqueued again after a restart. A safe,
honest failure mode (a duplicate reminder is a minor annoyance, not a
missed one) — see this sprint's own Potential Risks.

"Wellness postponement" (Part 2's Scheduler Engine section) is built
here only as a generic, reusable postpone() primitive — no
postponement-count escalation is tracked; that policy belongs to Level
5's Wellness Engine, not guessed at here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from config.schema import SchedulerConfig
from core.logging_setup import get_logger
from decision.priority_queue import PriorityLevel, PriorityQueueManager
from scheduler.calendar_store import CalendarStore
from scheduler.scheduler_model import ScheduledItem
from scheduler.task_scheduler import TaskScheduler

logger = get_logger(__name__)

_JOB_ID = "reminder_engine_poll"


class ReminderEngine:
    """Constructor DI: (calendar_store, priority_queue_manager,
    task_scheduler, scheduler_config). Not a ManagedModule itself — it
    owns no thread/resource of its own now that TaskScheduler does; its
    register()/unregister() are called by whichever ManagedModule
    composes it (Sprint 4.18's job, per main.py's composition-root
    pattern)."""

    def __init__(
        self,
        calendar_store: CalendarStore,
        priority_queue_manager: PriorityQueueManager,
        task_scheduler: TaskScheduler,
        scheduler_config: SchedulerConfig,
    ) -> None:
        self._calendar_store = calendar_store
        self._priority_queue_manager = priority_queue_manager
        self._task_scheduler = task_scheduler
        self._config = scheduler_config
        self._enqueued_item_ids: set[str] = set()

    def register(self) -> None:
        self._task_scheduler.add_job(
            self._poll_due_items, self._config.poll_interval_seconds, _JOB_ID
        )
        logger.info(
            "Reminder engine registered (poll_interval_seconds=%s).",
            self._config.poll_interval_seconds,
        )

    def unregister(self) -> None:
        self._task_scheduler.remove_job(_JOB_ID)
        logger.info("Reminder engine unregistered.")

    def _poll_due_items(self) -> None:
        window_end = datetime.now(UTC) + timedelta(
            seconds=self._config.reminder_lookahead_seconds
        )
        due_items = self._calendar_store.list_due_within(window_end)
        for item in due_items:
            if item.item_id in self._enqueued_item_ids:
                continue
            self._priority_queue_manager.enqueue(
                payload=item, priority=PriorityLevel.SCHEDULED_REMINDER, source="scheduler"
            )
            self._enqueued_item_ids.add(item.item_id)
            logger.info("Enqueued due reminder: %s (%r).", item.item_id, item.title)

    def postpone(self, item_id: str, delay: timedelta) -> ScheduledItem | None:
        item = self._calendar_store.get(item_id)
        if item is None:
            return None
        item.scheduled_at = item.scheduled_at + delay
        self._calendar_store.save(item)
        self._enqueued_item_ids.discard(item_id)
        return item

    def reschedule(self, item_id: str, new_time: datetime) -> ScheduledItem | None:
        item = self._calendar_store.get(item_id)
        if item is None:
            return None
        item.scheduled_at = new_time
        self._calendar_store.save(item)
        self._enqueued_item_ids.discard(item_id)
        return item

    def acknowledge(self, item_id: str) -> bool:
        acknowledged = self._calendar_store.mark_completed(item_id)
        if acknowledged:
            self._enqueued_item_ids.discard(item_id)
        return acknowledged
