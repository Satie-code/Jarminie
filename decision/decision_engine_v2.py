"""Decision Engine v2 — Level 6 Part A's action ranking, risk
estimation, confidence-weighted gating, required-confirmation
determination, and alternative-suggestion layer over Level 3's original
Decision Engine (decision/authority.py's AuthorityEvaluator). See
docs/sprint_book/sprint_6/sprint_6_5.md.

**Extends decision/, does not fork it.** EngineSelection/AuthorityLevel/
DecisionTrace/PriorityLevel (Sprint 3.10/3.11) are untouched — this
module composes existing collaborators' own output rather than
duplicating any of their already-correct logic.

**Risk estimation reuses security/policy_engine.py's existing
PermissionPolicyEngine (Sprint 4.7) rather than inventing a second risk
taxonomy.** rank_actions()/requires_confirmation() both call
PermissionPolicyEngine.classify() — the one real, existing source of
truth for an ActionType's RiskLevel and whether it requires
confirmation (RiskPolicy.requires_confirmation) — never reimplementing
that policy locally. requires_confirmation() and suggest_alternatives()
are both thin, explicitly-named pass-throughs for exactly this reason:
one coherent Level 6 Part A entry point, not a second decision authority.

**DecisionEngineV2 never dispatches.** It ranks and classifies
candidates, nothing more — no call to ActionRegistry.dispatch() or any
executor appears anywhere in this module. This is a deliberate, load-
bearing boundary: a ranking is not a decision to act. The caller
(Sprint 6.9/6.13) decides whether and when to dispatch a top-ranked,
non-confirmation-required action; the existing confirmation/permission
machinery (security/permission_gate.py) is what gates anything requiring
one. DecisionEngineV2 has no power to skip that gate for any candidate,
regardless of composite_score.

**A real, disclosed gap in this sprint file's own Expected Functions
text**: the constructor accepts authority_evaluator (per Expected
Classes, and Dependencies' own "composes AuthorityEvaluator's existing
output" framing), but none of rank_actions()/requires_confirmation()/
suggest_alternatives() actually calls a method on it — nothing in this
sprint's own Expected Functions names such a call. Stored as
self._authority_evaluator (satisfying the literal constructor
signature) but genuinely unused by this sprint's own three methods,
mirroring AdaptiveWellnessAdjuster's own disclosed "fetched but not
consumed" PREFERRED_TIME precedent (Sprint 5.22) — a real, disclosed gap
for a future sprint (6.12 Adaptive Prioritization, or 6.13 Integration)
to actually consume, not silently invented behavior here.

**Description text for reasoning_engine calls reuses
security/confirmation_service.py's own public build_prompt_text()** —
the one function that module deliberately keeps public (not leading-
underscore) specifically so other callers get the identical, already-
reviewed action description "for free" rather than a second,
independently-maintained describe-this-action implementation. Every
call site in this module that needs a description first classifies the
candidate's risk (a real, necessary input regardless) and reuses that
same RiskPolicy.risk_level for both scoring and description-building —
never a second, redundant classify() call.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.schema import DecisionEngineConfig
from context.context_model import WorkingContext
from core.logging_setup import get_logger
from decision.authority import AuthorityEvaluator
from decision.priority_queue import PriorityLevel
from device_control.action_engine import ActionRequest
from reasoning.reasoning_engine import ReasoningEngine
from reasoning.reasoning_model import Alternative
from security.confirmation_service import build_prompt_text
from security.policy_engine import PermissionPolicyEngine, RiskLevel

logger = get_logger(__name__)

_RISK_NORMALIZATION: dict[RiskLevel, float] = {
    RiskLevel.LOW: 0.0,
    RiskLevel.MEDIUM: 0.5,
    RiskLevel.HIGH: 1.0,
}
"""Normalizes RiskLevel to [0.0, 1.0] for the composite-score formula
(1 - normalized_risk rewards low risk). A 3-point linear scale — the
same "no basis for anything richer than the enum's own real member
count" discipline this codebase applies whenever normalizing a small,
fixed enum (mirrors reasoning/reasoning_engine.py's own confidence-scale
disclosure)."""

_MOST_URGENT_PRIORITY_VALUE = PriorityLevel.CRITICAL_EMERGENCY.value
_LEAST_URGENT_PRIORITY_VALUE = PriorityLevel.GENERAL_SUGGESTION.value


def _normalize_priority(level: PriorityLevel) -> float:
    """ActionRequest.risk_hint (Sprint 4.1) is a non-optional PriorityLevel
    defaulting to GENERAL_SUGGESTION — "if the candidate already carries
    one (else treats priority as neutral)" (this sprint file's own Expected
    Functions text) is therefore never a distinct code path: GENERAL_
    SUGGESTION already normalizes to 0.0, the low end of this range,
    which honestly reads as "no special urgency boost" — a disclosed
    resolution of that text's own hedge, not a separate default branch."""
    span = _MOST_URGENT_PRIORITY_VALUE - _LEAST_URGENT_PRIORITY_VALUE
    return (level.value - _LEAST_URGENT_PRIORITY_VALUE) / span


@dataclass
class RankedAction:
    action_request: ActionRequest
    risk_level: RiskLevel
    confidence: float
    composite_score: float
    requires_confirmation: bool


class DecisionEngineV2:
    """Constructor DI: (authority_evaluator, permission_policy_engine,
    reasoning_engine, decision_engine_config) — every collaborator
    already lifecycle-managed elsewhere; this class constructs none of
    them. Not a ManagedModule — a pure composition/scoring layer, the
    same shape WorkflowExecutor already established for its own four
    collaborators (Sprint 4.10)."""

    def __init__(
        self,
        authority_evaluator: AuthorityEvaluator,
        permission_policy_engine: PermissionPolicyEngine,
        reasoning_engine: ReasoningEngine,
        decision_engine_config: DecisionEngineConfig,
    ) -> None:
        self._authority_evaluator = authority_evaluator
        self._permission_policy_engine = permission_policy_engine
        self._reasoning_engine = reasoning_engine
        self._config = decision_engine_config

    def rank_actions(
        self, candidates: list[ActionRequest], working_context: WorkingContext | None = None
    ) -> list[RankedAction]:
        """Orders candidates descending by composite_score. A single
        candidate's own risk classification or confidence estimation
        raising degrades only that candidate to the most conservative
        ranking (RiskLevel.HIGH, confidence=0.0, requires_confirmation=
        True) rather than aborting the whole call — see this module's
        own docstring and sprint_6_5.md's own Potential Risks for why a
        degraded candidate's composite_score still reflects its own real
        risk_hint (which cannot itself fail to read)."""
        ranked = [self._rank_one(candidate, working_context) for candidate in candidates]
        ranked.sort(key=lambda ranked_action: ranked_action.composite_score, reverse=True)
        return ranked

    def _rank_one(
        self, candidate: ActionRequest, working_context: WorkingContext | None
    ) -> RankedAction:
        try:
            risk_policy = self._permission_policy_engine.classify(candidate.action_type)
            description = build_prompt_text(candidate, risk_policy.risk_level)
            trace = self._reasoning_engine.estimate_confidence(description, working_context)
            risk_level = risk_policy.risk_level
            confidence = trace.confidence
            requires_confirmation = risk_policy.requires_confirmation
        except Exception:
            logger.warning(
                "Ranking candidate %s failed; degrading to the most conservative ranking.",
                candidate.action_type.value,
                exc_info=True,
            )
            risk_level = RiskLevel.HIGH
            confidence = 0.0
            requires_confirmation = True
        composite_score = self._composite_score(risk_level, confidence, candidate.risk_hint)
        return RankedAction(
            action_request=candidate,
            risk_level=risk_level,
            confidence=confidence,
            composite_score=composite_score,
            requires_confirmation=requires_confirmation,
        )

    def _composite_score(
        self, risk_level: RiskLevel, confidence: float, priority: PriorityLevel
    ) -> float:
        normalized_risk = _RISK_NORMALIZATION[risk_level]
        normalized_priority = _normalize_priority(priority)
        return (
            self._config.risk_weight * (1 - normalized_risk)
            + self._config.confidence_weight * confidence
            + self._config.priority_weight * normalized_priority
        )

    def requires_confirmation(self, action_request: ActionRequest) -> bool:
        """A thin, explicitly-named pass-through to permission_policy_
        engine's own existing RiskPolicy.requires_confirmation — never a
        reimplementation of that policy."""
        return self._permission_policy_engine.classify(
            action_request.action_type
        ).requires_confirmation

    def suggest_alternatives(
        self, action_request: ActionRequest, working_context: WorkingContext | None = None
    ) -> list[Alternative]:
        """Thin pass-through to reasoning_engine.alternatives(), given
        the action's own description (build_prompt_text(), reusing the
        risk classification this call needs anyway) as the reasoning
        subject."""
        risk_policy = self._permission_policy_engine.classify(action_request.action_type)
        description = build_prompt_text(action_request, risk_policy.risk_level)
        trace = self._reasoning_engine.alternatives(description, working_context)
        return trace.alternatives
