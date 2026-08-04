"""Adaptive Wellness — bridges Sprint 5.18/5.19's own time-and-escalation-
driven Wellness Engine with Sprint 5.21's Pattern Recognition. See
docs/sprint_book/sprint_5/sprint_5_22.md.

**A real, disclosed integration seam, not a new dependency edge between
Wellness and Learning's own core packages**: this is the ONE file under
wellness/ allowed to import from learning/ — wellness_tracker.py/
escalation.py/wellness_model.py still import nothing from learning/
directly (see tests/unit/wellness/test_wellness_tracker.py's own
package-wide AST-based import-boundary test, extended this sprint to
allow exactly this one file). AdaptiveWellnessAdjuster reads PatternStore
and produces plain numeric interval multipliers; WellnessTracker.
evaluate_triggers() accepts them through a new, additive, optional
parameter it has no idea came from pattern recognition at all. A caller
who does not wire this adapter in gets Sprint 5.18/5.19's original,
already-tested static-threshold behavior, unchanged.

**Bounded adjustment, never unbounded**: every multiplier is clamped into
[WellnessConfig.adaptive_min_multiplier, adaptive_max_multiplier] —
Part 2's own "Adjust reminders accordingly" widens the *interval* a
trigger's threshold check compares against, never removes or disables a
reminder outright (that remains the Hard Limit Rule's own, separate
mechanism, Sprint 5.19).

**A real, deliberate narrowing to avoid a perverse incentive**: only
BREAK/EYE_PROTECTION are ever widened by compute_overrides()'s own real
rule this sprint. LATE_NIGHT/OVERWORK are always 1.0 here — a WORK_HABIT
pattern reflecting an UNHEALTHY habit (e.g. consistently working very
late) must never widen the very reminders meant to counter it. HYDRATION
also stays 1.0 this sprint, a real, disclosed gap (not an oversight):
Sprint 5.21's own WORK_HABIT detection has no natural hydration-specific
analogue yet (see this sprint's own Future Considerations).

**One-directional composition, never the reverse**: AdaptiveWellnessAdjuster
never talks to WellnessEscalationManager and never itself decides whether
a trigger fires — only WellnessTracker.evaluate_triggers() consumes its
output, and only as an interval multiplier upstream of the threshold
check. This keeps "adjust reminders accordingly" honestly scoped to WHEN
a reminder fires, never WHETHER the Hard Limit Rule still applies once it
does.
"""

from __future__ import annotations

from config.schema import WellnessConfig
from core.logging_setup import get_logger
from learning.pattern_model import LearnedPattern, PatternType
from learning.pattern_store import PatternStore
from wellness.wellness_model import WellnessTriggerType

logger = get_logger(__name__)

# The only triggers compute_overrides()'s own real rule ever widens this
# sprint — see this module's own docstring for why LATE_NIGHT/OVERWORK are
# deliberately excluded (perverse-incentive avoidance) and HYDRATION is a
# disclosed, not-yet-built gap.
_ADAPTIVE_TRIGGERS: tuple[WellnessTriggerType, ...] = (
    WellnessTriggerType.BREAK,
    WellnessTriggerType.EYE_PROTECTION,
)

_NO_EVIDENCE_EXPLANATION = "No pattern evidence yet — using the default interval."


class AdaptiveWellnessAdjuster:
    """Constructor DI: (pattern_store, wellness_config). Not a
    ManagedModule — no lifecycle of its own, the same non-ManagedModule-
    helper-class precedent wellness/escalation.py's WellnessEscalationManager
    already established (Sprint 5.19). Stateless beyond its own
    constructor DI, matching AnalyticsDashboardService's own "no caching,
    compose fresh at call time" precedent (Sprint 5.20)."""

    def __init__(self, pattern_store: PatternStore, wellness_config: WellnessConfig) -> None:
        self._pattern_store = pattern_store
        self._config = wellness_config

    def compute_overrides(self) -> dict[WellnessTriggerType, float]:
        """A trigger type with no relevant pattern evidence gets a
        multiplier of exactly 1.0 — inert, the honest "nothing learned
        yet" default, never a guess. PREFERRED_TIME patterns are fetched
        (matching this method's own literal Expected Functions text) but
        not yet consumed by this sprint's own single real rule — a
        disclosed gap, not a bug (see this module's own docstring's
        HYDRATION note and the sprint's own Future Considerations)."""
        self._pattern_store.list_by_type(PatternType.PREFERRED_TIME)

        overrides: dict[WellnessTriggerType, float] = dict.fromkeys(WellnessTriggerType, 1.0)
        strongest = self._strongest_work_habit_pattern()
        if strongest is not None:
            multiplier = self._multiplier_from_confidence(strongest.confidence)
            for trigger_type in _ADAPTIVE_TRIGGERS:
                overrides[trigger_type] = multiplier
        return overrides

    def explain(self, trigger_type: WellnessTriggerType) -> str:
        """A one-sentence, human-readable justification for trigger_type's
        own current multiplier — the Explainability Rule's own
        deliverable, mirroring decision/authority.py's DecisionTrace.
        reasoning_text precedent."""
        if trigger_type not in _ADAPTIVE_TRIGGERS:
            return _NO_EVIDENCE_EXPLANATION
        strongest = self._strongest_work_habit_pattern()
        if strongest is None:
            return _NO_EVIDENCE_EXPLANATION
        multiplier = self._multiplier_from_confidence(strongest.confidence)
        percent = round((multiplier - 1.0) * 100)
        return f"Widened by {percent}% based on a consistent '{strongest.subject}' work habit."

    def _strongest_work_habit_pattern(self) -> LearnedPattern | None:
        patterns = self._pattern_store.list_by_type(PatternType.WORK_HABIT)
        if not patterns:
            return None
        return max(patterns, key=lambda pattern: pattern.confidence)

    def _multiplier_from_confidence(self, confidence: float) -> float:
        raw = 1.0 + confidence * (self._config.adaptive_max_multiplier - 1.0)
        return max(
            self._config.adaptive_min_multiplier, min(self._config.adaptive_max_multiplier, raw)
        )
