"""Unit tests for decision.priority_queue.

ResourceMonitor is real (not faked) — it's cheap and side-effect-free to
construct, and PriorityQueueManager never calls anything on it directly
in this sprint's own scope (classify_resource_alert() only inspects the
ResourceAlert it's handed; wiring a live resource_monitor.critical_
alerts() call is Sprint 3.12's job).
"""

from datetime import UTC, datetime

import pytest

from config.schema import ResourceThresholds
from core.resource_monitor import ResourceAlert, ResourceMonitor
from decision.models import Intent, IntentCategory
from decision.priority_queue import PriorityLevel, PriorityQueueManager


@pytest.fixture
def resource_monitor() -> ResourceMonitor:
    return ResourceMonitor(ResourceThresholds())


@pytest.fixture
def queue(resource_monitor) -> PriorityQueueManager:
    return PriorityQueueManager(resource_monitor)


def make_intent(category: IntentCategory) -> Intent:
    return Intent(
        category=category, confidence=0.9, raw_transcript="x", detected_at=datetime.now(UTC)
    )


def make_alert(resource: str = "cpu") -> ResourceAlert:
    return ResourceAlert(resource=resource, value=95.0, threshold=90.0, timestamp=datetime.now(UTC))


# --- classify() ---------------------------------------------------------------


def test_classify_emergency_intent_is_critical_emergency(queue):
    assert queue.classify(make_intent(IntentCategory.EMERGENCY)) is PriorityLevel.CRITICAL_EMERGENCY


@pytest.mark.parametrize(
    "category",
    [
        IntentCategory.INFORMATIONAL,
        IntentCategory.ACTION_REQUEST,
        IntentCategory.MEMORY_RECALL,
        IntentCategory.EMOTIONAL_SUPPORT,
        IntentCategory.CASUAL_CONVERSATION,
        IntentCategory.UNKNOWN,
    ],
)
def test_classify_every_other_category_is_general_suggestion(queue, category):
    assert queue.classify(make_intent(category)) is PriorityLevel.GENERAL_SUGGESTION


# --- classify_resource_alert() -------------------------------------------------


def test_classify_resource_alert_is_always_important_alert(queue):
    assert queue.classify_resource_alert(make_alert("cpu")) is PriorityLevel.IMPORTANT_ALERT
    assert queue.classify_resource_alert(make_alert("battery")) is PriorityLevel.IMPORTANT_ALERT


# --- ordering -------------------------------------------------------------------


def test_items_pop_in_strict_priority_order_regardless_of_enqueue_order(queue):
    queue.enqueue("general", PriorityLevel.GENERAL_SUGGESTION, "test")
    queue.enqueue("wellness", PriorityLevel.WELLNESS, "test")
    queue.enqueue("emergency", PriorityLevel.CRITICAL_EMERGENCY, "test")
    queue.enqueue("scheduled", PriorityLevel.SCHEDULED_REMINDER, "test")
    queue.enqueue("alert", PriorityLevel.IMPORTANT_ALERT, "test")

    popped = [queue.pop_next().payload for _ in range(5)]

    assert popped == ["emergency", "alert", "scheduled", "wellness", "general"]


def test_two_items_at_the_same_priority_pop_in_fifo_order(queue):
    queue.enqueue("first", PriorityLevel.GENERAL_SUGGESTION, "test")
    queue.enqueue("second", PriorityLevel.GENERAL_SUGGESTION, "test")
    queue.enqueue("third", PriorityLevel.GENERAL_SUGGESTION, "test")

    popped = [queue.pop_next().payload for _ in range(3)]

    assert popped == ["first", "second", "third"]


def test_fifo_within_level_holds_even_with_identical_timestamps(monkeypatch, queue):
    """The monotonic tiebreaking counter must guarantee FIFO order even
    if two items are enqueued at the exact same instant (a real
    possibility on a fast machine, not just a theoretical edge case)."""
    fixed_time = datetime.now(UTC)
    monkeypatch.setattr(
        "decision.priority_queue.datetime",
        type("_FixedDatetime", (), {"now": staticmethod(lambda tz=None: fixed_time)}),
    )

    queue.enqueue("first", PriorityLevel.GENERAL_SUGGESTION, "test")
    queue.enqueue("second", PriorityLevel.GENERAL_SUGGESTION, "test")

    assert queue.pop_next().payload == "first"
    assert queue.pop_next().payload == "second"


def test_higher_priority_item_enqueued_after_lower_priority_still_pops_first(queue):
    queue.enqueue("low", PriorityLevel.GENERAL_SUGGESTION, "test")
    queue.enqueue("high", PriorityLevel.CRITICAL_EMERGENCY, "test")

    assert queue.pop_next().payload == "high"
    assert queue.pop_next().payload == "low"


# --- empty queue / peek --------------------------------------------------------


def test_pop_next_on_empty_queue_returns_none(queue):
    assert queue.pop_next() is None


def test_peek_next_on_empty_queue_returns_none(queue):
    assert queue.peek_next() is None


def test_peek_next_does_not_remove_the_item(queue):
    queue.enqueue("only item", PriorityLevel.GENERAL_SUGGESTION, "test")

    peeked = queue.peek_next()
    assert peeked.payload == "only item"

    popped = queue.pop_next()
    assert popped.payload == "only item"
    assert queue.pop_next() is None


def test_peek_next_returns_the_highest_priority_item(queue):
    queue.enqueue("low", PriorityLevel.GENERAL_SUGGESTION, "test")
    queue.enqueue("high", PriorityLevel.CRITICAL_EMERGENCY, "test")

    assert queue.peek_next().payload == "high"


# --- PriorityItem shape ---------------------------------------------------------


def test_enqueued_item_carries_source_and_priority(queue):
    queue.enqueue("payload", PriorityLevel.IMPORTANT_ALERT, "resource_monitor")

    item = queue.pop_next()

    assert item.payload == "payload"
    assert item.priority is PriorityLevel.IMPORTANT_ALERT
    assert item.source == "resource_monitor"
    assert item.enqueued_at is not None


# --- health_check() -------------------------------------------------------------


def test_health_check_true_when_queue_is_small(queue):
    queue.enqueue("item", PriorityLevel.GENERAL_SUGGESTION, "test")
    assert queue.health_check() is True


def test_health_check_false_when_queue_exceeds_the_sane_depth_bound(queue):
    for i in range(1001):
        queue.enqueue(f"item {i}", PriorityLevel.GENERAL_SUGGESTION, "test")

    assert queue.health_check() is False


def test_start_and_stop_do_not_raise(queue):
    queue.start()
    queue.stop()


# --- Sprint 6.14 hardening (scenario d): concurrent enqueue() vs. peek_next()/pop_next() ------


def test_peek_next_survives_concurrent_enqueue_from_many_threads(queue):
    """A real, concrete reproduction, not just reasoning about the GIL
    in the abstract — matching this project's own established "verify a
    race with a real minimal reproduction" discipline (e.g. Sprint
    5.25/5.26's own scheduler-vs-direct-call races). AdaptivePrioritizer.
    next_item() (6.12) calls peek_next() exactly once per call, so this
    exercises the actual shape of the real race: many threads (standing
    in for ProactiveAssistant._on_tick(), WellnessTracker, ReminderEngine,
    etc., all enqueuing onto the same shared queue) hammering enqueue()
    concurrently with another thread repeatedly calling peek_next()/
    pop_next() — heapq.heappush()/heappop() on tuples that already sort
    uniquely by their own monotonic counter (never falling through to
    comparing the non-orderable PriorityItem payload itself) never
    releases the GIL mid-operation in CPython, so no torn read is
    possible; this test proves that empirically rather than asserting it
    from documentation."""
    import threading

    thread_count = 8
    items_per_thread = 200
    errors: list[BaseException] = []
    stop_peeking = threading.Event()
    peek_results: list[PriorityLevel] = []

    def _enqueue_many(thread_index: int) -> None:
        try:
            for i in range(items_per_thread):
                queue.enqueue(f"t{thread_index}-{i}", PriorityLevel.GENERAL_SUGGESTION, "test")
        except BaseException as exc:  # noqa: BLE001 - captured for the main thread to re-raise
            errors.append(exc)

    def _peek_repeatedly() -> None:
        try:
            while not stop_peeking.is_set():
                item = queue.peek_next()
                if item is not None:
                    peek_results.append(item.priority)
        except BaseException as exc:  # noqa: BLE001 - captured for the main thread to re-raise
            errors.append(exc)

    peeker = threading.Thread(target=_peek_repeatedly)
    enqueuers = [
        threading.Thread(target=_enqueue_many, args=(i,)) for i in range(thread_count)
    ]

    peeker.start()
    for t in enqueuers:
        t.start()
    for t in enqueuers:
        t.join()
    stop_peeking.set()
    peeker.join()

    assert errors == []
    assert len(queue._heap) == thread_count * items_per_thread  # nothing lost, nothing duplicated
    # every real peek during the race saw a genuine, valid PriorityItem, never a
    # corrupted/partial one — the only PriorityLevel ever enqueued in this test.
    assert all(priority is PriorityLevel.GENERAL_SUGGESTION for priority in peek_results)
