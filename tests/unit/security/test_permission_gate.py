"""Unit tests for security.permission_gate."""

from datetime import UTC, datetime

import pytest

from decision.authority import AuthorityEvaluator
from security.permission_gate import PermissionDecision, PermissionGate


@pytest.fixture
def gate() -> PermissionGate:
    return PermissionGate(AuthorityEvaluator())


def make_request(action_type):
    """A minimal duck-typed stand-in carrying only what check() reads
    this sprint (action_type) — avoids importing device_control here
    just to build a full ActionRequest, and proves PermissionGate
    doesn't reach for any other field this sprint."""

    class _Request:
        pass

    request = _Request()
    request.action_type = action_type
    return request


def test_check_always_allows(gate):
    from device_control.action_engine import ActionType

    for action_type in ActionType:
        result = gate.check(make_request(action_type))
        assert result is PermissionDecision.ALLOW


def test_check_allows_with_a_populated_authority_evaluator_whitelist():
    """Proves the ALLOW-always behavior is genuinely unconditional this
    sprint — even a non-empty (Sprint 4.7+ shaped) whitelist doesn't
    change Sprint 4.1's own stub answer."""
    from device_control.action_engine import ActionType

    evaluator = AuthorityEvaluator(approved_emergency_procedures=frozenset({"battery critical"}))
    gate = PermissionGate(evaluator)

    result = gate.check(make_request(ActionType.SYSTEM_COMMAND))

    assert result is PermissionDecision.ALLOW


def test_constructed_with_a_real_authority_evaluator_not_mocked():
    evaluator = AuthorityEvaluator()
    gate = PermissionGate(evaluator)
    assert gate._authority_evaluator is evaluator


def test_check_does_not_mutate_or_raise_for_a_full_action_request():
    """End-to-end against the real ActionRequest shape, not just the
    minimal duck-typed stand-in used above."""
    from device_control.action_engine import ActionContext, ActionRequest, ActionType

    evaluator = AuthorityEvaluator()
    gate = PermissionGate(evaluator)
    request = ActionRequest(
        action_type=ActionType.FILE_DELETE,
        parameters={"path": "C:/scratch/example.txt"},
        context=ActionContext(requested_by="user_voice"),
        requested_at=datetime.now(UTC),
    )

    result = gate.check(request)

    assert result is PermissionDecision.ALLOW
