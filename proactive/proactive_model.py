"""Proactive Assistant data model — ProactiveTriggerType/ProactivePrompt.
See docs/sprint_book/sprint_6/sprint_6_8.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from decision.priority_queue import PriorityLevel


class ProactiveTriggerType(Enum):
    """The six brief-named triggers, exactly as listed."""

    UPCOMING_DEADLINE = "upcoming_deadline"
    FORGOTTEN_REMINDER = "forgotten_reminder"
    BATTERY_CRITICAL = "battery_critical"
    LONG_SESSION = "long_session"
    MISSED_MEAL = "missed_meal"
    PROJECT_INACTIVITY = "project_inactivity"


@dataclass
class ProactivePrompt:
    """subject_entity_id is a knowledge/ Entity reference, set only when
    the trigger genuinely concerns one (PROJECT_INACTIVITY) — None for
    every other trigger type, never a fabricated reference."""

    trigger_type: ProactiveTriggerType
    message: str
    priority: PriorityLevel
    evaluated_at: datetime
    subject_entity_id: str | None = None
