"""Emotional State Manager (Sprint 5.2 — Level 5 Part A).

Turns Sprint 5.1's per-turn EmotionEstimate into a **continuous,
slowly-evolving emotional state** — the brief's own explicit requirement
that mood/energy/stress/focus/comfort/social-energy/conversation-momentum
"evolve gradually. Not sentence-by-sentence." This is the single read
model every later Part A sprint (Persona Behavioral Adaptation,
Presentation State Engine, Gesture Engine, Companion Experience)
consults — none of them read EmotionEstimate directly.

Deliberately NOT a memory layer: this class holds exactly one live,
in-memory EmotionalState, with no persistence of its own and no history.
Persisting emotionally-significant *moments* (not the continuous state
itself) is Sprint 5.3's distinct responsibility (Single Responsibility).

Emotional State is process-wide, not per-session or per-user — Part 2's
own "long-term emotional context" language implies continuity across
sessions, which a per-session-scoped state would break. A future
multi-profile feature would need real rework here, not just a new
constructor parameter (see docs/sprint_book/sprint_5/sprint_5_2.md's own
Potential Risks).

No live caller yet — Sprint 5.14 (Presentation Layer Integration) wires
this in for real. See docs/sprint_book/sprint_5/sprint_5_2.md.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from config.schema import EmotionConfig
from core.logging_setup import get_logger
from emotion.models import EmotionEstimate, EmotionLabel

logger = get_logger(__name__)

# The six dimensions apply_estimate() drives from EmotionConfig.
# label_state_targets — conversation_momentum is deliberately excluded
# here and handled separately, always, from EmotionSignals.
# pause_before_turn_seconds instead (see apply_estimate()'s own
# docstring and this module's own Architecture Notes in the sprint file).
_LABEL_DRIVEN_DIMENSIONS: tuple[str, ...] = (
    "mood",
    "energy",
    "stress",
    "focus",
    "comfort",
    "social_energy",
)
_ALL_DIMENSIONS: tuple[str, ...] = (*_LABEL_DRIVEN_DIMENSIONS, "conversation_momentum")

_NEUTRAL_BASELINES: dict[str, float] = {
    "mood": 0.0,
    "energy": 50.0,
    "stress": 50.0,
    "focus": 50.0,
    "comfort": 50.0,
    "social_energy": 50.0,
    "conversation_momentum": 50.0,
}
_DIMENSION_RANGES: dict[str, tuple[float, float]] = {
    "mood": (-100.0, 100.0),
    "energy": (0.0, 100.0),
    "stress": (0.0, 100.0),
    "focus": (0.0, 100.0),
    "comfort": (0.0, 100.0),
    "social_energy": (0.0, 100.0),
    "conversation_momentum": (0.0, 100.0),
}


@dataclass
class EmotionalState:
    """A continuous, slowly-evolving read of the user's emotional state.

    All seven dimensions start at their neutral midpoint at construction
    — an honest "no read yet" starting point, not an assumed-positive or
    assumed-negative default. mood ranges -100..100 (negative..positive);
    every other dimension ranges 0..100. conversation_momentum is "how
    engaged/flowing does this conversation feel" — distinct from energy,
    which is about the user, not the conversation itself.
    """

    mood: float = 0.0
    energy: float = 50.0
    stress: float = 50.0
    focus: float = 50.0
    comfort: float = 50.0
    social_energy: float = 50.0
    conversation_momentum: float = 50.0
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _clamp_dimension(dimension: str, value: float) -> float:
    low, high = _DIMENSION_RANGES[dimension]
    return max(low, min(high, value))


def _momentum_target_from_pause(pause_before_turn_seconds: float, config: EmotionConfig) -> float:
    """A short pause (a quick back-and-forth) pushes momentum up; a long
    one decays it down — the identical "quick reply" intuition
    long_pause_threshold_seconds already anchors elsewhere in this Level.
    No pause data at all (0.0, e.g. a session's first turn) reads as a
    genuinely fast exchange, the same "no evidence against it" treatment
    empty signals get elsewhere in this Level."""
    threshold = config.long_pause_threshold_seconds
    raw = 90.0 - (pause_before_turn_seconds / threshold) * 40.0
    return _clamp_dimension("conversation_momentum", raw)


class EmotionalStateManager:
    """Constructor DI per 03_Engineering_Standards.md: receives only the
    EmotionConfig it depends on. Holds no external resource (no model
    load, no network, no file handle) — health_check() is trivially True
    once started, the same shape Sprint 5.1's EmotionDetectionEngine
    already has."""

    def __init__(self, emotion_config: EmotionConfig) -> None:
        self._config = emotion_config
        self._state = EmotionalState()
        self._started = False

    def start(self) -> None:
        self._started = True
        logger.info("Emotional State Manager started.")

    def stop(self) -> None:
        self._started = False
        logger.info("Emotional State Manager stopped.")

    def health_check(self) -> bool:
        return self._started

    def current_state(self) -> EmotionalState:
        """Return a copy, never the live internal object — the same
        defensive-copy discipline ConfidenceScorer.score()'s own
        replace() usage already established for a different dataclass."""
        return replace(self._state)

    def apply_estimate(self, estimate: EmotionEstimate) -> EmotionalState:
        """Bounded EMA nudge from one EmotionEstimate toward that
        estimate's implied target state. Never raises — an
        EmotionLabel.UNKNOWN estimate leaves the six label-driven
        dimensions untouched (a deliberate no-op, logged at DEBUG, not an
        error); conversation_momentum still updates from
        estimate.signals.pause_before_turn_seconds regardless of label,
        since that signal is always available and unrelated to whether
        classification succeeded."""
        alpha = self._config.state_smoothing_alpha
        current = self._state
        targets = self._config.label_state_targets.get(estimate.label.value, {})

        if estimate.label is EmotionLabel.UNKNOWN:
            logger.debug("apply_estimate(): UNKNOWN label, label-driven dimensions left untouched.")

        updated: dict[str, float] = {}
        for dimension in _LABEL_DRIVEN_DIMENSIONS:
            current_value = getattr(current, dimension)
            if estimate.label is EmotionLabel.UNKNOWN or dimension not in targets:
                updated[dimension] = current_value
                continue
            raw_target = targets[dimension]
            effective_target = current_value + (raw_target - current_value) * estimate.confidence
            new_value = current_value * (1 - alpha) + effective_target * alpha
            updated[dimension] = _clamp_dimension(dimension, new_value)

        momentum_target = _momentum_target_from_pause(
            estimate.signals.pause_before_turn_seconds, self._config
        )
        new_momentum = current.conversation_momentum * (1 - alpha) + momentum_target * alpha
        updated["conversation_momentum"] = _clamp_dimension("conversation_momentum", new_momentum)

        self._state = EmotionalState(**updated, updated_at=datetime.now(UTC))
        return self.current_state()

    def decay_toward_baseline(self, elapsed_seconds: float) -> EmotionalState:
        """Proportional pull back toward each dimension's neutral
        midpoint, given real elapsed time since the previous turn. Never
        raises — a zero/negative elapsed_seconds (e.g. a clock anomaly)
        is treated as a no-op, not an error."""
        if elapsed_seconds <= 0:
            return self.current_state()

        half_life = self._config.baseline_decay_half_life_seconds
        decay_factor = 0.5 ** (elapsed_seconds / half_life)

        current = self._state
        updated: dict[str, float] = {}
        for dimension in _ALL_DIMENSIONS:
            current_value = getattr(current, dimension)
            baseline = _NEUTRAL_BASELINES[dimension]
            new_value = baseline + (current_value - baseline) * decay_factor
            updated[dimension] = _clamp_dimension(dimension, new_value)

        self._state = EmotionalState(**updated, updated_at=datetime.now(UTC))
        return self.current_state()
