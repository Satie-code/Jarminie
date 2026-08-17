"""Unit tests for scheduler.reminder_engine.

CalendarStore/TaskScheduler/PriorityQueueManager are all real (not
faked) — matching this project's own established "real collaborator for
timing-sensitive/persistence-sensitive behavior" precedent. The
"enqueued exactly once across multiple poll cycles" scenario drives
ReminderEngine through a genuine, real TaskScheduler background poll
(short poll_interval_seconds for test speed, a bounded poll-until wait
rather than a blind sleep); postpone()/reschedule()/acknowledge()'s own
correctness is exercised by calling the engine's internal
_poll_due_items() directly where only orchestration logic (not real
background timing) is under test, avoiding unnecessary thread-timing
flakiness for assertions that don't need it.

_poll_due_items() itself always compares against the REAL wall-clock
time (datetime.now(UTC)) internally, not a test-injected value — every
ScheduledItem built here uses an offset from a freshly-captured
datetime.now(UTC) at test-execution time, never a fixed historical/
future constant, so these tests are correct regardless of what real
calendar date/time they happen to run at.
"""

import time
from datetime import UTC, datetime, timedelta

import pytest

from config.schema import ResourceThresholds, SchedulerConfig
from core.resource_monitor import ResourceMonitor
from database.sqlite_client import SqliteClient
from decision.priority_queue import PriorityLevel, PriorityQueueManager
from scheduler.calendar_store import CalendarStore
from scheduler.reminder_engine import ReminderEngine
from scheduler.scheduler_model import ItemType, ScheduledItem
from scheduler.task_scheduler import TaskScheduler

_WAIT_TIMEOUT = 2.0


def make_item(item_id: str = "item-1", scheduled_at: datetime | None = None) -> ScheduledItem:
    now = datetime.now(UTC)
    return ScheduledItem(
        item_id=item_id,
        item_type=ItemType.EVENT,
        title="Team standup",
        scheduled_at=scheduled_at if scheduled_at is not None else now,
        created_at=now,
    )


def _wait_until(predicate, timeout: float = _WAIT_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def calendar_store(tmp_path) -> CalendarStore:
    client = SqliteClient(str(tmp_path / "calendar.db"))
    store = CalendarStore(client, SchedulerConfig())
    store.start()
    yield store
    store.stop()


@pytest.fixture
def priority_queue_manager() -> PriorityQueueManager:
    return PriorityQueueManager(ResourceMonitor(ResourceThresholds()))


@pytest.fixture
def task_scheduler():
    ts = TaskScheduler()
    ts.start()
    yield ts
    ts.stop()


@pytest.fixture
def engine(calendar_store, priority_queue_manager, task_scheduler) -> ReminderEngine:
    return ReminderEngine(
        calendar_store, priority_queue_manager, task_scheduler, SchedulerConfig()
    )


# --- real background polling: enqueued exactly once ------------------------------------


def test_due_item_is_enqueued_exactly_once_across_multiple_poll_cycles(
    calendar_store, priority_queue_manager, task_scheduler
):
    fast_config = SchedulerConfig(poll_interval_seconds=0.05)
    reminder_engine = ReminderEngine(
        calendar_store, priority_queue_manager, task_scheduler, fast_config
    )
    item = make_item()
    calendar_store.save(item)

    reminder_engine.register()
    try:
        assert _wait_until(lambda: priority_queue_manager.peek_next() is not None)

        # Let several more poll cycles elapse while the item remains
        # un-acknowledged/un-postponed — it must not be enqueued again.
        time.sleep(0.3)

        first = priority_queue_manager.pop_next()
        assert first is not None
        assert first.payload.item_id == item.item_id
        assert first.priority is PriorityLevel.SCHEDULED_REMINDER
        assert first.source == "scheduler"
        assert priority_queue_manager.pop_next() is None
    finally:
        reminder_engine.unregister()


def test_unregister_stops_further_polling(calendar_store, priority_queue_manager, task_scheduler):
    fast_config = SchedulerConfig(poll_interval_seconds=0.05)
    reminder_engine = ReminderEngine(
        calendar_store, priority_queue_manager, task_scheduler, fast_config
    )
    reminder_engine.register()
    reminder_engine.unregister()

    item = make_item()
    calendar_store.save(item)
    time.sleep(0.3)

    assert priority_queue_manager.peek_next() is None


# --- _poll_due_items() orchestration logic (direct call, deterministic) ----------------


def test_poll_due_items_enqueues_due_item(engine, calendar_store, priority_queue_manager):
    item = make_item()
    calendar_store.save(item)

    engine._poll_due_items()

    enqueued = priority_queue_manager.pop_next()
    assert enqueued is not None
    assert enqueued.payload.item_id == item.item_id


def test_poll_due_items_does_not_reenqueue_already_pending_item(
    engine, calendar_store, priority_queue_manager
):
    item = make_item()
    calendar_store.save(item)

    engine._poll_due_items()
    engine._poll_due_items()

    priority_queue_manager.pop_next()
    assert priority_queue_manager.pop_next() is None


def test_poll_due_items_ignores_not_yet_due_item(engine, calendar_store, priority_queue_manager):
    item = make_item(scheduled_at=datetime.now(UTC) + timedelta(days=1))
    calendar_store.save(item)

    engine._poll_due_items()

    assert priority_queue_manager.pop_next() is None


# --- postpone() --------------------------------------------------------------------------


def test_postpone_updates_scheduled_at_and_allows_reenqueue(
    engine, calendar_store, priority_queue_manager
):
    item = make_item()
    calendar_store.save(item)
    engine._poll_due_items()
    priority_queue_manager.pop_next()  # drain the first, already-tested enqueue

    result = engine.postpone(item.item_id, timedelta(days=1))

    assert result is not None
    assert result.scheduled_at == item.scheduled_at + timedelta(days=1)
    assert calendar_store.get(item.item_id).scheduled_at == item.scheduled_at + timedelta(days=1)

    # Not due yet after being postponed a day into the future.
    engine._poll_due_items()
    assert priority_queue_manager.pop_next() is None

    # Postponing again, this time back to "now", re-enqueues — proving
    # postpone() cleared the earlier enqueued-tracking.
    engine.postpone(item.item_id, -timedelta(days=1))
    engine._poll_due_items()
    assert priority_queue_manager.pop_next() is not None


def test_postpone_nonexistent_item_returns_none(engine):
    assert engine.postpone("does-not-exist", timedelta(minutes=5)) is None


# --- reschedule() --------------------------------------------------------------------------


def test_reschedule_sets_scheduled_at_exactly(engine, calendar_store):
    item = make_item()
    calendar_store.save(item)
    new_time = datetime.now(UTC) + timedelta(days=3)

    result = engine.reschedule(item.item_id, new_time)

    assert result is not None
    assert result.scheduled_at == new_time
    assert calendar_store.get(item.item_id).scheduled_at == new_time


def test_reschedule_clears_enqueued_tracking(engine, calendar_store, priority_queue_manager):
    item = make_item()
    calendar_store.save(item)
    engine._poll_due_items()
    priority_queue_manager.pop_next()

    engine.reschedule(item.item_id, datetime.now(UTC))  # reschedule back to "now"

    engine._poll_due_items()
    assert priority_queue_manager.pop_next() is not None


def test_reschedule_nonexistent_item_returns_none(engine):
    assert engine.reschedule("does-not-exist", datetime.now(UTC)) is None


# --- acknowledge() -----------------------------------------------------------------------


def test_acknowledge_marks_completed_and_excludes_from_future_polls(
    engine, calendar_store, priority_queue_manager
):
    item = make_item()
    calendar_store.save(item)
    engine._poll_due_items()
    priority_queue_manager.pop_next()

    result = engine.acknowledge(item.item_id)

    assert result is True
    assert calendar_store.get(item.item_id).is_completed is True

    engine._poll_due_items()
    assert priority_queue_manager.pop_next() is None


def test_acknowledge_nonexistent_item_returns_false(engine):
    assert engine.acknowledge("does-not-exist") is False


# --- reminder_lookahead_seconds --------------------------------------------------------


def test_reminder_lookahead_seconds_widens_the_due_window(
    calendar_store, priority_queue_manager, task_scheduler
):
    lookahead_config = SchedulerConfig(reminder_lookahead_seconds=3600)
    reminder_engine = ReminderEngine(
        calendar_store, priority_queue_manager, task_scheduler, lookahead_config
    )
    item = make_item(scheduled_at=datetime.now(UTC) + timedelta(minutes=30))
    calendar_store.save(item)

    reminder_engine._poll_due_items()

    assert priority_queue_manager.pop_next() is not None


# --- Sprint 4.19 hardening (scenario e): CalendarStore failure during poll -------------


class _RaisingSqliteClient(SqliteClient):
    """Matches the project's established "_Raising*-style local test
    double" pattern — see tests/unit/scheduler/test_calendar_store.py's
    own identical copy for the full rationale (duplicated, not imported,
    per this project's "tests/ has no __init__.py" convention)."""

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.raise_on_query = False

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self.raise_on_query:
            raise RuntimeError("sqlite query exploded")
        return super().query(sql, params)


def test_a_persistently_failing_poll_keeps_recurring_via_real_task_scheduler(
    tmp_path, priority_queue_manager, task_scheduler
):
    """Sprint 6.17 (Async Background Task Audit) — one of the 12 jobs not
    yet individually verified against TaskScheduler's own explicit
    max_instances=1. _poll_due_items() never actually raises (see
    test_poll_due_items_survives_a_real_calendar_store_failure
    immediately below — CalendarStore.list_due_within() already
    degrades internally), so unlike Sprint 6.14's ProactiveAssistant
    precedent (a job that genuinely propagates), the meaningful property
    to prove here is the real registered job continuing to fire on its
    own real recurring schedule despite a persistently failing
    underlying SqliteClient, not merely surviving one direct call."""
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    calendar_store = CalendarStore(client, SchedulerConfig())
    calendar_store.start()
    client.raise_on_query = True
    fast_config = SchedulerConfig(poll_interval_seconds=0.05)
    reminder_engine = ReminderEngine(
        calendar_store, priority_queue_manager, task_scheduler, fast_config
    )
    tick_count = 0
    real_poll = reminder_engine._poll_due_items

    def _counting_poll():
        nonlocal tick_count
        tick_count += 1
        real_poll()

    reminder_engine._poll_due_items = _counting_poll

    reminder_engine.register()
    try:
        assert _wait_until(lambda: tick_count >= 3)
        assert task_scheduler.health_check() is True
    finally:
        reminder_engine.unregister()
        client.raise_on_query = False
        calendar_store.stop()


def test_poll_due_items_survives_a_real_calendar_store_failure(
    tmp_path, priority_queue_manager, task_scheduler
):
    """Sprint 4.19 hardening, scenario (e): _poll_due_items() has no
    try/except of its own — it doesn't need one, since CalendarStore.
    list_due_within() (this sprint's own hardening) already degrades to
    an empty list on a real SQLite failure rather than raising. This
    test proves that through the real CalendarStore/ReminderEngine pair,
    not just CalendarStore in isolation — a poll during an outage simply
    finds nothing due, never crashes the calling TaskScheduler job."""
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    calendar_store = CalendarStore(client, SchedulerConfig())
    calendar_store.start()
    try:
        calendar_store.save(make_item(scheduled_at=datetime.now(UTC)))
        reminder_engine = ReminderEngine(
            calendar_store, priority_queue_manager, task_scheduler, SchedulerConfig()
        )
        client.raise_on_query = True

        reminder_engine._poll_due_items()  # must not raise

        assert priority_queue_manager.peek_next() is None
    finally:
        client.raise_on_query = False
        calendar_store.stop()
