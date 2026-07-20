"""Unit tests for device_control.action_engine."""

from datetime import UTC, datetime

import pytest

from decision.authority import AuthorityEvaluator
from device_control.action_engine import (
    ActionContext,
    ActionRegistry,
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)
from security.permission_gate import PermissionDecision, PermissionGate


def make_request(
    action_type: ActionType = ActionType.LAUNCH_APPLICATION,
    parameters: dict | None = None,
) -> ActionRequest:
    return ActionRequest(
        action_type=action_type,
        parameters=parameters if parameters is not None else {},
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )


class FakeExecutor:
    """Duck-typed ActionExecutor — handles exactly one ActionType,
    records every request it's called with."""

    def __init__(
        self, handled_type: ActionType, result_status: ActionStatus = ActionStatus.SUCCEEDED
    ) -> None:
        self.handled_type = handled_type
        self.result_status = result_status
        self.calls: list[ActionRequest] = []

    def can_handle(self, action_type: ActionType) -> bool:
        return action_type is self.handled_type

    def execute(self, request: ActionRequest) -> ActionResult:
        self.calls.append(request)
        return ActionResult(
            request=request, status=self.result_status, completed_at=datetime.now(UTC)
        )


class RaisingExecutor:
    """An executor whose execute() always raises — proves dispatch()
    never lets an executor's own exception escape."""

    def can_handle(self, action_type: ActionType) -> bool:
        return True

    def execute(self, request: ActionRequest) -> ActionResult:
        raise RuntimeError("boom")


class StubPermissionGate:
    """A fixed-decision PermissionGate stand-in, duck-typed against the
    real PermissionGate's check() shape — the "fake at the boundary"
    convention this project uses throughout."""

    def __init__(self, decision: PermissionDecision) -> None:
        self._decision = decision
        self.checked_requests: list[ActionRequest] = []

    def check(self, request: ActionRequest) -> PermissionDecision:
        self.checked_requests.append(request)
        return self._decision


class RaisingPermissionGate:
    def check(self, request: ActionRequest) -> PermissionDecision:
        raise RuntimeError("permission check exploded")


@pytest.fixture
def real_permission_gate() -> PermissionGate:
    return PermissionGate(AuthorityEvaluator())


@pytest.fixture
def registry(real_permission_gate) -> ActionRegistry:
    return ActionRegistry(real_permission_gate)


# --- ActionContext / ActionRequest / ActionResult field defaults --------------


def test_action_context_defaults():
    context = ActionContext(requested_by="user_voice")
    assert context.persona_name is None
    assert context.session_id is None
    assert context.decision_trace is None


def test_action_request_default_risk_hint_and_explicit_timestamp():
    from decision.priority_queue import PriorityLevel

    now = datetime.now(UTC)
    request = ActionRequest(
        action_type=ActionType.LAUNCH_APPLICATION,
        parameters={"executable_path": "notepad.exe"},
        context=ActionContext(requested_by="test"),
        requested_at=now,
    )
    assert request.risk_hint is PriorityLevel.GENERAL_SUGGESTION
    assert request.requested_at is now


def test_action_result_carries_its_own_request():
    request = make_request()
    result = ActionResult(
        request=request, status=ActionStatus.SUCCEEDED, completed_at=datetime.now(UTC)
    )
    assert result.request is request
    assert result.output is None
    assert result.error_message is None


# --- ActionRegistry.register()/dispatch() routing ------------------------------


def test_dispatch_routes_to_correct_executor(registry):
    launch_executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    delete_executor = FakeExecutor(ActionType.FILE_DELETE)
    registry.register(launch_executor)
    registry.register(delete_executor)

    request = make_request(ActionType.FILE_DELETE)
    result = registry.dispatch(request)

    assert result.status is ActionStatus.SUCCEEDED
    assert delete_executor.calls == [request]
    assert launch_executor.calls == []


def test_dispatch_with_no_matching_executor_degrades_to_failed(registry):
    registry.register(FakeExecutor(ActionType.LAUNCH_APPLICATION))

    result = registry.dispatch(make_request(ActionType.FILE_DELETE))

    assert result.status is ActionStatus.FAILED
    assert "No executor registered" in result.error_message


def test_dispatch_with_zero_registered_executors_degrades_to_failed(registry):
    result = registry.dispatch(make_request())
    assert result.status is ActionStatus.FAILED


# --- PermissionGate short-circuiting -------------------------------------------


def test_dispatch_denies_without_calling_executor():
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    gate = StubPermissionGate(PermissionDecision.DENY)
    registry = ActionRegistry(gate)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.DENIED
    assert executor.calls == []
    assert len(gate.checked_requests) == 1


def test_dispatch_require_confirmation_without_calling_executor():
    """REQUIRE_CONFIRMATION is unreachable via the real PermissionGate
    this sprint, but dispatch() must still handle it correctly — Sprint
    4.7 changes zero call sites here."""
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    gate = StubPermissionGate(PermissionDecision.REQUIRE_CONFIRMATION)
    registry = ActionRegistry(gate)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.AWAITING_CONFIRMATION
    assert executor.calls == []


def test_dispatch_allows_and_calls_executor():
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    gate = StubPermissionGate(PermissionDecision.ALLOW)
    registry = ActionRegistry(gate)
    registry.register(executor)

    request = make_request()
    result = registry.dispatch(request)

    assert result.status is ActionStatus.SUCCEEDED
    assert executor.calls == [request]


# --- Fail Gracefully: no exception ever escapes dispatch() --------------------


def test_permission_gate_exception_degrades_to_failed_not_raised():
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    registry = ActionRegistry(RaisingPermissionGate())
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.FAILED
    assert executor.calls == []


def test_executor_exception_degrades_to_failed_not_raised():
    gate = StubPermissionGate(PermissionDecision.ALLOW)
    registry = ActionRegistry(gate)
    registry.register(RaisingExecutor())

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.FAILED
    assert result.error_message


# --- Real PermissionGate integration (not mocked) ------------------------------


def test_dispatch_with_real_permission_gate_and_authority_evaluator(registry):
    """registry's own fixture is built on a real PermissionGate backed by
    a real AuthorityEvaluator — proves the whole chain works end to end,
    not just against stubs."""
    executor = FakeExecutor(ActionType.WINDOW_FOCUS)
    registry.register(executor)

    result = registry.dispatch(make_request(ActionType.WINDOW_FOCUS))

    assert result.status is ActionStatus.SUCCEEDED
    assert len(executor.calls) == 1
