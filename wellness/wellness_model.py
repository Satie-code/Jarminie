"""Wellness Triggers — the Wellness Engine's detection-half data model.
See docs/sprint_book/sprint_5/sprint_5_18.md.

WellnessPrompt is a produced, not-yet-spoken recommendation — this sprint
never speaks, enqueues, or otherwise acts on one. Sprint 5.19 (escalation/
postponement/the Hard Limit Rule) and Sprint 5.24 (a real
PriorityQueueManager.enqueue() call plus the actual spoken announcement)
are both deliberately out of scope here.

escalation_level defaults to 1 and is given real behavior only by Sprint
5.19 — present now so this dataclass's own shape does not need a breaking
change later, the same "field exists before the sprint that gives it real
behavior" precedent presentation/presentation_state.py's own
gesture_probability already established (Sprint 5.5/5.9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class WellnessTriggerType(Enum):
    """The five named categories Part 2's Wellness Engine section lists
    (Screen time/Overwork awareness, Hydration, Eye protection, Break
    reminders, Late-night reminders)."""

    BREAK = "break"
    HYDRATION = "hydration"
    EYE_PROTECTION = "eye_protection"
    LATE_NIGHT = "late_night"
    OVERWORK = "overwork"


@dataclass
class WellnessPrompt:
    """A single produced wellness recommendation. prompt_id is generated
    on construction (UUID4) unless supplied — matching analytics/
    usage_model.py's AppFocusSample.sample_id precedent (Sprint 5.17)."""

    trigger_type: WellnessTriggerType
    message: str
    triggered_at: datetime
    prompt_id: str = field(default_factory=lambda: str(uuid4()))
    escalation_level: int = 1
