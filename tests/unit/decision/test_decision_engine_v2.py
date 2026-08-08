"""Unit tests for decision.decision_engine_v2.

Uses real PermissionPolicyEngine(SecurityConfig()) for the happy-path
ranking-order test (its own already-tested default risk table gives a
realistic, deterministic RiskLevel per ActionType — no need to fake what
this codebase already gets right once) and small, local, duck-typed
fakes for PermissionPolicyEngine/ReasoningEngine everywhere a test needs
to force a failure or assert call arguments — the same "fake only what
the test needs to control" discipline test_planning_engine.py's own
FakeLanguageModelClient already established.
"""

from datetime import UTC, datetime

import pytest

from config.schema import DecisionEngineConfig, SecurityConfig
from decision.authority import AuthorityEvaluator
from decision.decision_engine_v2 import DecisionEngineV2
from decision.priority_queue import PriorityLevel
from device_control.action_engine import ActionContext, ActionRequest, ActionType
from reasoning.reasoning_model import Alternative, ReasoningTrace
from security.confirmation_service import build_prompt_text
from security.policy_engine import PermissionPolicyEngine, RiskLevel, RiskPolicy


class FakePermissionPolicyEngine:
    def __init__(
        self,
        risk_level: RiskLevel = RiskLevel.LOW,
        requires_confirmation: bool = False,
        error: Exception | None = None,
    ) -> None:
        self._risk_level = risk_level
        self._requires_confirmation = requires_confirmation
        self._error = error
        self.classify_calls: list[ActionType] = []

    def classify(self, action_type: ActionType) -> RiskPolicy:
        self.classify_calls.append(action_type)
        if self._error is not None:
            raise self._error
        return RiskPolicy(
            action_type=action_type,
            risk_level=self._risk_level,
            requires_confirmation=self._requires_confirmation,
        )


class FakeReasoningEngine:
    """estimate_confidence() consumes `confidences` in call order — the
    same "one queued value per call, consumed in order" pattern
    FakeLanguageModelClient's own single-response fixtures use, widened
    to a sequence since rank_actions() calls this once per candidate."""

    def __init__(
        self,
        confidences: list[float] | None = None,
        alternatives: list[Alternative] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._confidences = list(confidences) if confidences is not None else []
        self._alternatives = alternatives if alternatives is not None else []
        self._error = error
        self.estimate_confidence_calls: list[tuple[str, object]] = []
        self.alternatives_calls: list[tuple[str, object]] = []

    def estimate_confidence(self, subject: str, working_context=None) -> ReasoningTrace:
        self.estimate_confidence_calls.append((subject, working_context))
        if self._error is not None:
            raise self._error
        confidence = self._confidences[len(self.estimate_confidence_calls) - 1]
        return ReasoningTrace(
            subject=subject,
            question_type="confidence",
            conclusion="A conclusion.",
            confidence=confidence,
            reasoned_at=datetime.now(UTC),
        )

    def alternatives(self, subject: str, working_context=None) -> ReasoningTrace:
        self.alternatives_calls.append((subject, working_context))
        return ReasoningTrace(
            subject=subject,
            question_type="alternatives",
            conclusion="A conclusion.",
            confidence=1.0,
            reasoned_at=datetime.now(UTC),
            alternatives=self._alternatives,
        )


@pytest.fixture
def decision_engine_config() -> DecisionEngineConfig:
    return DecisionEngineConfig(risk_weight=0.4, confidence_weight=0.35, priority_weight=0.25)


@pytest.fixture
def authority_evaluator() -> AuthorityEvaluator:
    return AuthorityEvaluator()


def _action_request(
    action_type: ActionType,
    parameters: dict[str, object] | None = None,
    risk_hint: PriorityLevel = PriorityLevel.GENERAL_SUGGESTION,
) -> ActionRequest:
    return ActionRequest(
        action_type=action_type,
        parameters=parameters or {},
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
        risk_hint=risk_hint,
    )


# --- rank_actions: ordering ---------------------------------------------------------------


def test_rank_actions_orders_descending_by_composite_score(
    authority_evaluator, decision_engine_config
):
    low_risk_urgent = _action_request(
        ActionType.LAUNCH_APPLICATION,
        {"executable_path": "notepad.exe"},
        risk_hint=PriorityLevel.CRITICAL_EMERGENCY,
    )
    high_risk_low_priority = _action_request(
        ActionType.FILE_DELETE, {"path": "C:/tmp/x.txt"}, risk_hint=PriorityLevel.GENERAL_SUGGESTION
    )
    medium_risk_mid_priority = _action_request(
        ActionType.FILE_MOVE,
        {"source": "a", "destination": "b"},
        risk_hint=PriorityLevel.SCHEDULED_REMINDER,
    )

    permission_policy_engine = PermissionPolicyEngine(SecurityConfig())
    reasoning_engine = FakeReasoningEngine(confidences=[1.0, 0.0, 0.5])
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )

    ranked = engine.rank_actions(
        [low_risk_urgent, high_risk_low_priority, medium_risk_mid_priority]
    )

    assert [r.action_request.action_type for r in ranked] == [
        ActionType.LAUNCH_APPLICATION,
        ActionType.FILE_MOVE,
        ActionType.FILE_DELETE,
    ]
    assert ranked[0].composite_score > ranked[1].composite_score > ranked[2].composite_score
    assert ranked[0].risk_level is RiskLevel.LOW
    assert ranked[2].risk_level is RiskLevel.HIGH


def test_rank_actions_composite_score_matches_the_configured_weights(
    authority_evaluator, decision_engine_config
):
    candidate = _action_request(
        ActionType.LAUNCH_APPLICATION,
        {"executable_path": "notepad.exe"},
        risk_hint=PriorityLevel.CRITICAL_EMERGENCY,
    )
    permission_policy_engine = PermissionPolicyEngine(SecurityConfig())
    reasoning_engine = FakeReasoningEngine(confidences=[1.0])
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )

    ranked = engine.rank_actions([candidate])

    # LOW risk -> normalized_risk=0.0; confidence=1.0; CRITICAL_EMERGENCY -> normalized_priority=1.0
    expected = (
        decision_engine_config.risk_weight * 1.0
        + decision_engine_config.confidence_weight * 1.0
        + decision_engine_config.priority_weight * 1.0
    )
    assert ranked[0].composite_score == pytest.approx(expected)


# --- rank_actions: degrade on failure ------------------------------------------------------


def test_rank_actions_degrades_a_candidate_whose_classification_raises(
    authority_evaluator, decision_engine_config
):
    candidate = _action_request(ActionType.LAUNCH_APPLICATION, risk_hint=PriorityLevel.WELLNESS)
    permission_policy_engine = FakePermissionPolicyEngine(error=RuntimeError("classify exploded"))
    reasoning_engine = FakeReasoningEngine(confidences=[0.9])
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )

    ranked = engine.rank_actions([candidate])

    assert ranked[0].risk_level is RiskLevel.HIGH
    assert ranked[0].confidence == 0.0
    assert ranked[0].requires_confirmation is True


def test_rank_actions_degrades_a_candidate_whose_confidence_estimation_raises(
    authority_evaluator, decision_engine_config
):
    candidate = _action_request(ActionType.LAUNCH_APPLICATION)
    permission_policy_engine = FakePermissionPolicyEngine(
        risk_level=RiskLevel.LOW, requires_confirmation=False
    )
    reasoning_engine = FakeReasoningEngine(error=RuntimeError("ollama unreachable"))
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )

    ranked = engine.rank_actions([candidate])

    assert ranked[0].risk_level is RiskLevel.HIGH
    assert ranked[0].confidence == 0.0
    assert ranked[0].requires_confirmation is True


def test_rank_actions_degrades_only_the_failing_candidate(
    authority_evaluator, decision_engine_config
):
    healthy = _action_request(ActionType.LAUNCH_APPLICATION, {"executable_path": "notepad.exe"})
    failing = _action_request(ActionType.FILE_MOVE, {"source": "a", "destination": "b"})
    permission_policy_engine = PermissionPolicyEngine(SecurityConfig())
    reasoning_engine = FakeReasoningEngine(confidences=[0.8])

    call_count = 0
    real_estimate_confidence = reasoning_engine.estimate_confidence

    def flaky_estimate_confidence(subject, working_context=None):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("ollama unreachable")
        return real_estimate_confidence(subject, working_context)

    reasoning_engine.estimate_confidence = flaky_estimate_confidence
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )

    ranked = engine.rank_actions([healthy, failing])

    healthy_result = next(r for r in ranked if r.action_request is healthy)
    failing_result = next(r for r in ranked if r.action_request is failing)
    assert healthy_result.confidence == 0.8
    assert healthy_result.risk_level is RiskLevel.LOW
    assert failing_result.confidence == 0.0
    assert failing_result.risk_level is RiskLevel.HIGH
    assert failing_result.requires_confirmation is True


def test_rank_actions_never_raises_because_of_one_bad_candidate(
    authority_evaluator, decision_engine_config
):
    candidate = _action_request(ActionType.LAUNCH_APPLICATION)
    permission_policy_engine = FakePermissionPolicyEngine(error=RuntimeError("boom"))
    reasoning_engine = FakeReasoningEngine(confidences=[0.5])
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )

    ranked = engine.rank_actions([candidate])  # must not raise

    assert len(ranked) == 1


# --- requires_confirmation: pass-through ----------------------------------------------------


def test_requires_confirmation_passes_through_to_permission_policy_engine(
    authority_evaluator, decision_engine_config
):
    action_request = _action_request(ActionType.FILE_DELETE)
    permission_policy_engine = FakePermissionPolicyEngine(
        risk_level=RiskLevel.HIGH, requires_confirmation=True
    )
    reasoning_engine = FakeReasoningEngine()
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )

    result = engine.requires_confirmation(action_request)

    assert result is True
    assert permission_policy_engine.classify_calls == [ActionType.FILE_DELETE]


def test_requires_confirmation_returns_false_when_policy_engine_says_so(
    authority_evaluator, decision_engine_config
):
    action_request = _action_request(ActionType.LAUNCH_APPLICATION)
    permission_policy_engine = FakePermissionPolicyEngine(
        risk_level=RiskLevel.LOW, requires_confirmation=False
    )
    reasoning_engine = FakeReasoningEngine()
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )

    assert engine.requires_confirmation(action_request) is False


def test_requires_confirmation_matches_a_real_permission_policy_engine(
    authority_evaluator, decision_engine_config
):
    action_request = _action_request(ActionType.FILE_DELETE, {"path": "C:/tmp/x.txt"})
    real_policy_engine = PermissionPolicyEngine(SecurityConfig())
    reasoning_engine = FakeReasoningEngine()
    engine = DecisionEngineV2(
        authority_evaluator, real_policy_engine, reasoning_engine, decision_engine_config
    )

    expected = real_policy_engine.classify(action_request.action_type).requires_confirmation
    assert engine.requires_confirmation(action_request) == expected


# --- suggest_alternatives: pass-through -----------------------------------------------------


def test_suggest_alternatives_passes_through_to_reasoning_engine(
    authority_evaluator, decision_engine_config
):
    action_request = _action_request(ActionType.LAUNCH_APPLICATION, {"executable_path": "x.exe"})
    permission_policy_engine = FakePermissionPolicyEngine(risk_level=RiskLevel.LOW)
    expected_alternatives = [Alternative(description="Do X instead", estimated_trade_off="Safer")]
    reasoning_engine = FakeReasoningEngine(alternatives=expected_alternatives)
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )

    result = engine.suggest_alternatives(action_request)

    assert result == expected_alternatives
    assert len(reasoning_engine.alternatives_calls) == 1
    subject, working_context = reasoning_engine.alternatives_calls[0]
    assert subject == build_prompt_text(action_request, RiskLevel.LOW)
    assert working_context is None


def test_suggest_alternatives_passes_the_given_working_context_through(
    authority_evaluator, decision_engine_config
):
    action_request = _action_request(ActionType.LAUNCH_APPLICATION)
    permission_policy_engine = FakePermissionPolicyEngine(risk_level=RiskLevel.LOW)
    reasoning_engine = FakeReasoningEngine()
    engine = DecisionEngineV2(
        authority_evaluator, permission_policy_engine, reasoning_engine, decision_engine_config
    )
    sentinel_context = object()

    engine.suggest_alternatives(action_request, working_context=sentinel_context)

    assert reasoning_engine.alternatives_calls[0][1] is sentinel_context
