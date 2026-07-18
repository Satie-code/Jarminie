"""Priority Queue — the Decision Engine pipeline's fourth stage, per
02_System_Architecture.md: "... -> Memory Retrieval -> Priority
Evaluation -> Authority Evaluation -> ..." Also implements Part 2's full
five-level Priority Queue System:

    1  CRITICAL_EMERGENCY  - wired:    Intent.category == EMERGENCY (3.7)
    2  IMPORTANT_ALERT     - wired:    ResourceMonitor critical alerts (1.4)
    3  SCHEDULED_REMINDER  - reserved: Scheduler (Sprint 4.8+)
    4  WELLNESS            - reserved: Wellness Engine (Phase 5.2)
    5  GENERAL_SUGGESTION  - default fallback for everything else

Same "build the full mechanism now, wire real sources incrementally"
discipline already established for SwitchReason (personas/persona_
manager.py, Sprint 2.11) — Level 3 has no genuine multi-source
scheduling problem yet (a single active conversation turn plus
occasional resource alerts), so this sprint is honestly scoped to a
real, correctly-ordered queue and classification function, not a
pretense of richer concurrency than actually exists.

Priority Evaluation runs BEFORE Authority Evaluation (Sprint 3.11) in
Part 2's pipeline — classify() can only TENTATIVELY flag something
CRITICAL_EMERGENCY based on Intent Detection's own classification
(itself imperfect by Sprint 3.7's own admission). Sprint 3.11 is what
actually confirms whether, and how, JARMINEI is authorized to act on it.
"""

import heapq
import itertools
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from core.logging_setup import get_logger
from core.resource_monitor import ResourceAlert, ResourceMonitor
from decision.models import Intent, IntentCategory

logger = get_logger(__name__)

_MAX_SANE_QUEUE_DEPTH = 1000
"""A defensive health_check() bound against an unbounded backlog — not
an expected real condition at Level 3's actual request volume, the same
"large enough that a real value never plausibly reaches it" convention
as memory/event_memory.py's/short_term_memory.py's _LARGE_LIMIT."""


class PriorityLevel(Enum):
    """Part 2's five priority levels. Explicit integer values, matching
    Part 2's own numbered list literally — unlike SwitchReason's
    implicit declaration-order convention, Part 2 numbers these
    directly, so the enum mirrors that rather than relying on
    declaration order to encode priority."""

    CRITICAL_EMERGENCY = 1
    IMPORTANT_ALERT = 2
    SCHEDULED_REMINDER = 3
    WELLNESS = 4
    GENERAL_SUGGESTION = 5


@dataclass
class PriorityItem:
    """One queued item. payload is whatever was classified — an Intent
    (3.7), a ResourceAlert (core/resource_monitor.py), or, once
    Scheduler/Wellness exist, whatever those sources enqueue."""

    payload: object
    priority: PriorityLevel
    enqueued_at: datetime
    source: str


class PriorityQueueManager:
    """Constructor DI: receives the ResourceMonitor it can classify
    alerts from. Not yet called on any real cadence — CoreManager
    already owns ResourceMonitor's own lifecycle; wiring an actual
    periodic critical-alert check into this queue is Sprint 3.12's job,
    the same live-caller deferral every other Level 3 module has had.

    Internal queue: a heapq keyed by (priority.value, enqueued_at, a
    monotonic tiebreaking counter) — priority first, then insertion
    order. The counter guarantees a total order even if two items share
    an identical timestamp, so heapq's comparison never needs to fall
    through to comparing PriorityItem objects themselves (whose payload
    isn't necessarily orderable)."""

    def __init__(self, resource_monitor: ResourceMonitor) -> None:
        self._resource_monitor = resource_monitor
        self._heap: list[tuple[int, datetime, int, PriorityItem]] = []
        self._counter = itertools.count()

    def start(self) -> None:
        logger.info("Priority Queue Manager started.")

    def stop(self) -> None:
        logger.info("Priority Queue Manager stopped.")

    def health_check(self) -> bool:
        """A defensive bound against an unbounded backlog — not an
        expected real condition at Level 3's request volume."""
        return len(self._heap) <= _MAX_SANE_QUEUE_DEPTH

    def classify(self, intent: Intent) -> PriorityLevel:
        """CRITICAL_EMERGENCY for an EMERGENCY intent; GENERAL_SUGGESTION
        otherwise — the honest default, since nothing at Level 3
        produces an Intent or signal shaped like SCHEDULED_REMINDER or
        WELLNESS yet."""
        if intent.category == IntentCategory.EMERGENCY:
            return PriorityLevel.CRITICAL_EMERGENCY
        return PriorityLevel.GENERAL_SUGGESTION

    def classify_resource_alert(self, alert: ResourceAlert) -> PriorityLevel:
        """A ResourceAlert always classifies as IMPORTANT_ALERT — every
        ResourceAlert that exists was already constructed by
        ResourceMonitor.critical_alerts() specifically because it
        crossed a CRITICAL threshold, so there is no lower-severity
        ResourceAlert to distinguish from."""
        return PriorityLevel.IMPORTANT_ALERT

    def enqueue(self, payload: object, priority: PriorityLevel, source: str) -> None:
        enqueued_at = datetime.now(UTC)
        item = PriorityItem(
            payload=payload, priority=priority, enqueued_at=enqueued_at, source=source
        )
        heapq.heappush(self._heap, (priority.value, enqueued_at, next(self._counter), item))

    def pop_next(self) -> PriorityItem | None:
        """The highest-priority, oldest-enqueued item, removed from the
        queue. None if empty — an expected, common state."""
        if not self._heap:
            return None
        return heapq.heappop(self._heap)[3]

    def peek_next(self) -> PriorityItem | None:
        """Same as pop_next(), but non-destructive — used by Sprint 3.11
        to inspect priority without consuming the item."""
        if not self._heap:
            return None
        return self._heap[0][3]
