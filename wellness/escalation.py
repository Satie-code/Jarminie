"""Wellness Escalation & Hard Limit. See
docs/sprint_book/sprint_5/sprint_5_19.md.

Gives Sprint 5.18's raw WellnessTracker.evaluate_triggers() detection its
escalation/postponement-tracking half: `WellnessTracker` decides *whether
a threshold is crossed*, `WellnessEscalationManager` decides *whether
that crossing is still allowed to produce a prompt at all* (not hard-
limited) and *what wording level* it should carry — the same "storage/
tracking split from behavior/policy" separation
scheduler/calendar_store.py's CalendarStore/scheduler/reminder_engine.py's
ReminderEngine already established for the Scheduler.

**One real reset signal serving all three of Part 2's own named resume
conditions, a disclosed simplification**: Part 2 lists "New session,"
"Actual break," and "Significant inactivity" as three separate Hard Limit
Rule resume conditions, but this codebase has only ever had one real
underlying signal for any of them — WellnessTracker's own significant-
inactivity reset (wellness_tracker.py's _on_tick(), Sprint 5.18). "New
session" and "actual break" are, in this codebase's own real terms,
indistinguishable from "the user was significantly inactive and has now
returned," so reset_all() is called from that exact same signal rather
than building a second, separate reset mechanism with no real basis of
its own.

A pure, injectable policy object holding no reference to WellnessTracker,
PriorityQueueManager, or any voice/UI collaborator — the same "pure
decision function over collaborators it doesn't own" discipline
emotion/detection_engine.py's _score_significance()/
presentation/gesture_engine.py both already established.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.schema import WellnessConfig
from core.logging_setup import get_logger
from wellness.wellness_model import WellnessTriggerType

logger = get_logger(__name__)

# Used only when a trigger type has no dedicated entry in
# WellnessConfig.escalation_message_templates — deliberately NOT itself a
# config field, since the sprint's own Files to Modify names only
# max_postponements_before_hard_limit/escalation_message_templates as new
# WellnessConfig fields.
_GENERIC_TEMPLATE: tuple[str, str, str] = (
    "This might be a good moment for a wellness break.",
    "It's been a while — please consider taking care of this soon.",
    "This really should not wait much longer.",
)

_MAX_LEVEL = 3


@dataclass
class _TriggerEscalationState:
    level: int = 1
    postponement_count: int = 0


class WellnessEscalationManager:
    """Constructor DI: (wellness_config,). Holds an internal
    dict[WellnessTriggerType, _TriggerEscalationState], lazily
    initialized per trigger type at level 1 / zero postponements on
    first access — a trigger type never explicitly postponed/reset stays
    at its own honest default state."""

    def __init__(self, wellness_config: WellnessConfig) -> None:
        self._config = wellness_config
        self._states: dict[WellnessTriggerType, _TriggerEscalationState] = {}

    def register_prompt_shown(self, trigger_type: WellnessTriggerType) -> None:
        """Marks that a prompt at the trigger's current level was
        actually surfaced. Deliberately does NOT itself escalate or
        reset anything — only register_postponed() escalates, per this
        module's own Architecture Notes (being told something and doing
        nothing about it is not, per Part 2's own text, a
        postponement)."""
        self._get_state(trigger_type)
        logger.debug("Wellness prompt shown: %s", trigger_type.value)

    def register_postponed(self, trigger_type: WellnessTriggerType) -> None:
        """Increments the trigger's postponement count and raises its
        escalation level by one, capped at 3. Once the postponement
        count reaches max_postponements_before_hard_limit, the trigger
        becomes hard-limited (is_hard_limited() below) — no separate
        flag is stored, so the two can never drift out of sync."""
        state = self._get_state(trigger_type)
        state.postponement_count += 1
        state.level = min(state.level + 1, _MAX_LEVEL)
        logger.info(
            "Wellness prompt postponed: %s (postponement_count=%d, level=%d, hard_limited=%s)",
            trigger_type.value,
            state.postponement_count,
            state.level,
            self.is_hard_limited(trigger_type),
        )

    def is_hard_limited(self, trigger_type: WellnessTriggerType) -> bool:
        state = self._get_state(trigger_type)
        return state.postponement_count >= self._config.max_postponements_before_hard_limit

    def current_level(self, trigger_type: WellnessTriggerType) -> int:
        """Always 1-3, never 0 — level exists independently of whether a
        prompt has been shown yet."""
        return self._get_state(trigger_type).level

    def message_for(self, trigger_type: WellnessTriggerType) -> str:
        """Resolves WellnessConfig.escalation_message_templates at the
        trigger's current_level(), falling back to _GENERIC_TEMPLATE when
        the trigger type has no dedicated entry."""
        templates = self._config.escalation_message_templates.get(
            trigger_type.value, list(_GENERIC_TEMPLATE)
        )
        return templates[self.current_level(trigger_type) - 1]

    def reset_all(self) -> None:
        """The Hard Limit Rule's own resume path — every trigger's level
        returns to 1, postponement count to 0, hard-limit cleared."""
        self._states.clear()
        logger.info("Wellness escalation state reset for all triggers.")

    def reset(self, trigger_type: WellnessTriggerType) -> None:
        """The narrower, single-trigger version — used once a specific
        reminder is genuinely acted on (e.g. the user actually takes a
        break), distinct from a blanket reset_all() inactivity reset."""
        self._states.pop(trigger_type, None)
        logger.info("Wellness escalation state reset for %s.", trigger_type.value)

    def _get_state(self, trigger_type: WellnessTriggerType) -> _TriggerEscalationState:
        return self._states.setdefault(trigger_type, _TriggerEscalationState())
