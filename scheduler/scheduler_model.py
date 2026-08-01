"""Calendar & Deadlines Store — the Scheduler Engine's definition model.
See docs/sprint_book/sprint_4_14.md.

ScheduledItem is a single dataclass covering both of Part 2's "Calendar"
and "Deadlines" nouns, distinguished only by ItemType — not three
parallel classes/tables. The two share every field that matters for
storage and querying; the only real behavioral difference (a deadline
counts down to a hard due time, an event is announced in advance of a
start time) is Sprint 4.15's (Reminder Engine) concern, not a storage-
shape concern. Mirrors WorkflowStep/ActionRequest's own deliberately
aligned shapes (Sprint 4.9) and memory/memory_store.py's MemoryType-as-
a-single-table-discriminator design (Sprint 3.1) — the established
pattern in this codebase for "several conceptually distinct things that
share one real storage shape."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ItemType(Enum):
    EVENT = "event"
    DEADLINE = "deadline"


@dataclass
class ScheduledItem:
    """scheduled_at is one timestamp field for both event-start and
    deadline-due semantics deliberately — item_type alone disambiguates
    what it means for every capability this Sprint Book actually
    specifies. See scheduler_model.py's own module docstring."""

    item_id: str
    item_type: ItemType
    title: str
    scheduled_at: datetime
    created_at: datetime
    description: str | None = None
    is_completed: bool = False
