"""GestureEngine (Sprint 5.9 — Level 5 Part A).

Decides **when** a discrete gesture should fire — persona-agnostic, per
the brief's own listed gesture categories (notification reactions, turn
start/end, mode transitions, listening/speaking posture, ambient idle
behavior). **How it looks** is entirely each renderer's own job
(`JarvisRenderer`: a brief accent pulse on the segmented ring;
`MinieRenderer`: a real `AvatarRenderer.trigger_gesture()` call) — this
module never imports `jarvis_renderer.py`/`minie_renderer.py`/
`vtube_studio_renderer.py`, mirroring the same when/how split already
drawn between `decision/authority.py` and `CommunicationPipeline`, or
`PriorityQueueManager.classify()` and its own consumer.

Two structurally distinct trigger sources, matching their own genuinely
different call shapes: `trigger_event()` (event-driven — a notification
arriving, a turn starting/ending, an `OperatingMode` transition) and
`maybe_roll_ambient_gesture()` (polled — a small, rate-limited chance
each tick of a purely ambient gesture, gated by
`PresentationState.gesture_probability`, which is what makes an idle
avatar/dashboard feel alive rather than static).

**Rate limiting (Sprint 5.15, scenario f)**: `trigger_event()` is now
rate-limited too, per `GestureTrigger` value, via
`PresentationConfig.gesture_trigger_min_interval_seconds` — the same
interval-gate discipline `maybe_roll_ambient_gesture()` already applies
to its own ambient path (only a genuine fire consumes the interval; a
call that returns None because the vocabulary is empty does not), so a
bug elsewhere calling `trigger_event()` far more often than intended
(e.g. a retry loop firing it every millisecond) cannot flood a renderer
with gesture calls either. Each `GestureTrigger` value has its own
independent budget — a burst of `TURN_START` calls cannot suppress a
legitimate `TURN_END` call arriving moments later.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from config.schema import PresentationConfig
from core.logging_setup import get_logger

logger = get_logger(__name__)


class GestureTrigger(Enum):
    """The brief's own named gesture categories (notification reactions,
    listening posture, speaking posture, idle posture) plus the turn/mode
    transitions that most naturally produce a discrete gesture."""

    NOTIFICATION = "notification"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    MODE_TRANSITION_TO_ACTIVE = "mode_transition_to_active"
    MODE_TRANSITION_TO_DORMANT = "mode_transition_to_dormant"
    LISTENING_POSTURE = "listening_posture"
    SPEAKING_POSTURE = "speaking_posture"
    AMBIENT_IDLE = "ambient_idle"


@dataclass
class GestureEvent:
    """A single, persona-agnostic gesture decision. gesture_id is the
    concrete, renderer-facing id chosen from
    PresentationConfig.gesture_vocabulary[trigger.value] — deliberately
    single-gesture-shaped (a gesture *sequence* is new scope, not this
    sprint's own job, per Future Considerations)."""

    trigger: GestureTrigger
    gesture_id: str
    persona_name: str
    triggered_at: datetime


class GestureEngine:
    """Constructor DI per 03_Engineering_Standards.md: receives only
    PresentationConfig — no PersonaManager/EmotionalStateManager/renderer
    reference. Every method takes exactly the data it needs as
    parameters and returns a plain GestureEvent | None, the same pure-
    decision-function discipline ConfidenceScorer._score_significance()
    (Sprint 5.3) already applied. The one deliberate exception to
    "pure": this class tracks its own last-ambient-fire timestamp
    internally so maybe_roll_ambient_gesture() can rate-limit itself —
    a disclosed trade-off (Architecture Notes' claim of purity is about
    collaborator references, not internal state), not a hidden
    inconsistency."""

    def __init__(self, presentation_config: PresentationConfig) -> None:
        self._config = presentation_config
        self._round_robin_index: dict[GestureTrigger, int] = {}
        self._last_ambient_fired_at: datetime | None = None
        self._last_trigger_fired_at: dict[GestureTrigger, datetime] = {}

    def trigger_event(self, trigger: GestureTrigger, persona_name: str) -> GestureEvent | None:
        """Never raises. Returns None (a logged no-op) if trigger's
        configured vocabulary is empty; otherwise round-robins through
        the configured candidates for config-driven variety rather than
        always the first entry. Sprint 5.15 scenario (f): also returns
        None, without consuming a round-robin slot, if this same trigger
        fired more recently than gesture_trigger_min_interval_seconds
        ago — see this module's own docstring."""
        now = datetime.now(UTC)
        last_fired = self._last_trigger_fired_at.get(trigger)
        if last_fired is not None:
            elapsed = (now - last_fired).total_seconds()
            if elapsed < self._config.gesture_trigger_min_interval_seconds:
                return None
        event = self._select_event(trigger, persona_name, now)
        if event is not None:
            self._last_trigger_fired_at[trigger] = now
        return event

    def maybe_roll_ambient_gesture(
        self, gesture_probability: float, persona_name: str
    ) -> GestureEvent | None:
        """Rolls against gesture_probability (0.0-1.0, from
        PresentationState) — returns None far more often than not by
        design. Rate-limited by ambient_gesture_roll_interval_seconds
        regardless of gesture_probability: the interval gate is checked
        before any roll happens, so even a probability of 1.0 cannot
        fire more than once per configured interval. The gate only
        tracks genuine fires (a non-None result) — a roll that fails
        (or whose vocabulary happens to be empty) does not consume the
        interval, so the next call can try again immediately."""
        now = datetime.now(UTC)
        if self._last_ambient_fired_at is not None:
            elapsed = (now - self._last_ambient_fired_at).total_seconds()
            if elapsed < self._config.ambient_gesture_roll_interval_seconds:
                return None
        if random.random() >= gesture_probability:
            return None
        event = self._select_event(GestureTrigger.AMBIENT_IDLE, persona_name, now)
        if event is not None:
            self._last_ambient_fired_at = now
        return event

    def _select_event(
        self, trigger: GestureTrigger, persona_name: str, triggered_at: datetime
    ) -> GestureEvent | None:
        candidates = self._config.gesture_vocabulary.get(trigger.value, [])
        if not candidates:
            logger.info(
                "trigger_event(%s): no configured gesture vocabulary; no-op.", trigger.value
            )
            return None
        index = self._round_robin_index.get(trigger, 0)
        gesture_id = candidates[index % len(candidates)]
        self._round_robin_index[trigger] = index + 1
        return GestureEvent(
            trigger=trigger,
            gesture_id=gesture_id,
            persona_name=persona_name,
            triggered_at=triggered_at,
        )
