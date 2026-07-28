"""Unit tests for device_control.action_engine."""

from datetime import UTC, datetime

import pytest

from config.schema import DeviceControlConfig, SecurityConfig
from decision.authority import AuthorityEvaluator
from device_control.action_engine import (
    ActionContext,
    ActionRegistry,
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)
from device_control.resource_gate import ResourceGateDecision
from security.confirmation_service import ConfirmationOutcome
from security.permission_gate import PermissionDecision, PermissionGate
from security.policy_engine import PermissionPolicyEngine


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

    def __init__(self) -> None:
        self.call_count = 0

    def can_handle(self, action_type: ActionType) -> bool:
        return True

    def execute(self, request: ActionRequest) -> ActionResult:
        self.call_count += 1
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


class StubResourceGate:
    """A fixed-decision ActionResourceGate stand-in, duck-typed against
    the real ActionResourceGate's check()/last_blocked_alerts() shape."""

    def __init__(
        self, decision: ResourceGateDecision, resource_names: list[str] | None = None
    ) -> None:
        self._decision = decision
        self._resource_names = resource_names or []
        self.checked_action_types: list[ActionType] = []

    def check(self, action_type: ActionType) -> ResourceGateDecision:
        self.checked_action_types.append(action_type)
        return self._decision

    def last_blocked_alerts(self) -> list[object]:
        class _FakeAlert:
            def __init__(self, resource: str) -> None:
                self.resource = resource
                self.value = 99.0

        return [_FakeAlert(name) for name in self._resource_names]


class RaisingResourceGate:
    def check(self, action_type: ActionType) -> ResourceGateDecision:
        raise RuntimeError("resource check exploded")


class _AlwaysConfirmConfirmationService:
    """A stub ConfirmationService that always confirms — this fixture
    exercises ActionRegistry's own dispatch/routing behavior, not
    Sprint 4.7's confirmation flow itself (covered separately in
    tests/unit/security/), so a real voice-backed service isn't needed
    here."""

    def request_confirmation(self, request) -> ConfirmationOutcome:
        return ConfirmationOutcome.CONFIRMED


@pytest.fixture
def real_permission_gate() -> PermissionGate:
    return PermissionGate(
        AuthorityEvaluator(),
        PermissionPolicyEngine(SecurityConfig()),
        _AlwaysConfirmConfirmationService(),
        DeviceControlConfig(),
    )


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


# --- ActionResourceGate integration (Sprint 4.6) --------------------------------


def test_dispatch_with_no_resource_gate_behaves_exactly_as_before(real_permission_gate):
    """Regression: constructing ActionRegistry with no resource_gate
    argument at all (Sprint 4.1's original call shape) must behave
    identically — confirms this sprint's change is genuinely additive."""
    registry = ActionRegistry(real_permission_gate)
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.SUCCEEDED
    assert executor.calls


def test_dispatch_proceeds_when_resource_gate_allows():
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    resource_gate = StubResourceGate(ResourceGateDecision.PROCEED)
    registry = ActionRegistry(permission_gate, resource_gate)
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.SUCCEEDED
    assert executor.calls
    assert resource_gate.checked_action_types == [ActionType.LAUNCH_APPLICATION]


def test_dispatch_blocked_by_resource_gate_never_calls_executor():
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    resource_gate = StubResourceGate(
        ResourceGateDecision.BLOCKED_CRITICAL_RESOURCE, resource_names=["cpu"]
    )
    registry = ActionRegistry(permission_gate, resource_gate)
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.FAILED
    assert executor.calls == []
    assert "cpu" in result.error_message


def test_dispatch_permission_denial_short_circuits_before_resource_gate():
    """Permission is checked first — a DENY must mean the resource gate
    is never even consulted, per this sprint's own fixed-order Integration
    Considerations."""
    permission_gate = StubPermissionGate(PermissionDecision.DENY)
    resource_gate = StubResourceGate(ResourceGateDecision.PROCEED)
    registry = ActionRegistry(permission_gate, resource_gate)
    registry.register(FakeExecutor(ActionType.LAUNCH_APPLICATION))

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.DENIED
    assert resource_gate.checked_action_types == []


def test_dispatch_resource_gate_exception_degrades_to_failed_not_raised():
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    registry = ActionRegistry(permission_gate, RaisingResourceGate())
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.FAILED
    assert executor.calls == []


# --- ActionAuditLog integration (Sprint 4.8) ------------------------------------


class SpyAuditLog:
    def __init__(self) -> None:
        self.records: list[tuple] = []

    def record(self, result, permission_decision, risk_level):
        self.records.append((result, permission_decision, risk_level))
        return None


def test_dispatch_with_no_audit_log_behaves_exactly_as_before():
    """Regression: no audit_log argument at all (pre-4.8 call shape)
    must behave identically — confirms this sprint's change is
    genuinely additive."""
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    registry = ActionRegistry(permission_gate)
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.SUCCEEDED


def test_successful_dispatch_produces_exactly_one_audit_record():
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    audit_log = SpyAuditLog()
    registry = ActionRegistry(permission_gate, audit_log=audit_log)
    registry.register(FakeExecutor(ActionType.LAUNCH_APPLICATION))

    registry.dispatch(make_request())

    assert len(audit_log.records) == 1
    result, permission_decision, risk_level = audit_log.records[0]
    assert result.status is ActionStatus.SUCCEEDED
    assert permission_decision is PermissionDecision.ALLOW
    assert risk_level is None


def test_denied_dispatch_produces_exactly_one_audit_record():
    permission_gate = StubPermissionGate(PermissionDecision.DENY)
    audit_log = SpyAuditLog()
    registry = ActionRegistry(permission_gate, audit_log=audit_log)
    registry.register(FakeExecutor(ActionType.LAUNCH_APPLICATION))

    registry.dispatch(make_request())

    assert len(audit_log.records) == 1
    result, permission_decision, _ = audit_log.records[0]
    assert result.status is ActionStatus.DENIED
    assert permission_decision is PermissionDecision.DENY


def test_failed_dispatch_produces_exactly_one_audit_record():
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    audit_log = SpyAuditLog()
    registry = ActionRegistry(permission_gate, audit_log=audit_log)
    registry.register(RaisingExecutor())

    registry.dispatch(make_request())

    assert len(audit_log.records) == 1
    assert audit_log.records[0][0].status is ActionStatus.FAILED


def test_permission_check_exception_still_produces_an_audit_record():
    audit_log = SpyAuditLog()
    registry = ActionRegistry(RaisingPermissionGate(), audit_log=audit_log)
    registry.register(FakeExecutor(ActionType.LAUNCH_APPLICATION))

    registry.dispatch(make_request())

    assert len(audit_log.records) == 1
    result, permission_decision, _ = audit_log.records[0]
    assert result.status is ActionStatus.FAILED
    assert permission_decision is PermissionDecision.DENY


# --- Retry logic (Sprint 4.8) ----------------------------------------------------


class TransientThenSucceedExecutor:
    """Fails with a timeout-shaped error message for its first
    fail_count calls, then succeeds."""

    def __init__(self, handled_type: ActionType, fail_count: int) -> None:
        self.handled_type = handled_type
        self.fail_count = fail_count
        self.calls: list[ActionRequest] = []

    def can_handle(self, action_type: ActionType) -> bool:
        return action_type is self.handled_type

    def execute(self, request: ActionRequest) -> ActionResult:
        self.calls.append(request)
        if len(self.calls) <= self.fail_count:
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Command timed out after 5.0s.",
            )
        return ActionResult(
            request=request, status=ActionStatus.SUCCEEDED, completed_at=datetime.now(UTC)
        )


class AlwaysTransientFailureExecutor:
    def __init__(self, handled_type: ActionType) -> None:
        self.handled_type = handled_type
        self.calls: list[ActionRequest] = []

    def can_handle(self, action_type: ActionType) -> bool:
        return action_type is self.handled_type

    def execute(self, request: ActionRequest) -> ActionResult:
        self.calls.append(request)
        return ActionResult(
            request=request,
            status=ActionStatus.FAILED,
            completed_at=datetime.now(UTC),
            error_message="Blocked by critical resource pressure: cpu at 95.0% (critical)",
        )


def test_transient_failure_is_retried_until_it_succeeds():
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    registry = ActionRegistry(permission_gate, max_retry_attempts=2)
    executor = TransientThenSucceedExecutor(ActionType.LAUNCH_APPLICATION, fail_count=1)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.SUCCEEDED
    assert len(executor.calls) == 2


def test_transient_failure_exhausts_retries_and_reports_failed():
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    audit_log = SpyAuditLog()
    registry = ActionRegistry(permission_gate, audit_log=audit_log, max_retry_attempts=2)
    executor = AlwaysTransientFailureExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.FAILED
    assert len(executor.calls) == 3  # 1 initial attempt + 2 retries
    assert len(audit_log.records) == 1  # exactly one audit record for the whole call


def test_zero_max_retry_attempts_means_no_retry_at_all():
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    registry = ActionRegistry(permission_gate)  # default max_retry_attempts=0
    executor = AlwaysTransientFailureExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.FAILED
    assert len(executor.calls) == 1


def test_non_transient_denial_is_never_retried():
    permission_gate = StubPermissionGate(PermissionDecision.DENY)
    registry = ActionRegistry(permission_gate, max_retry_attempts=2)
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.DENIED
    assert executor.calls == []


def test_non_transient_failure_is_never_retried():
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    registry = ActionRegistry(permission_gate, max_retry_attempts=2)
    executor = RaisingExecutor()
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.FAILED
    assert result.error_message == "Executor raised an unexpected internal error."
    assert executor.call_count == 1


# --- Sprint 4.12 hardening (scenario f): audit-log failure never affects the ---------
# --- action's own real, returned result --------------------------------------------


class RaisingAuditLog:
    def record(self, result, permission_decision, risk_level):
        raise RuntimeError("audit log exploded")


def test_audit_log_exception_does_not_affect_the_returned_action_result():
    """Deliberate defense in depth: ActionAuditLog.record() already
    guards its own entire body (also hardened this sprint), but this
    proves dispatch() itself never trusts that alone — a raising
    audit_log implementation still leaves the real action outcome
    completely unaffected."""
    permission_gate = StubPermissionGate(PermissionDecision.ALLOW)
    registry = ActionRegistry(permission_gate, audit_log=RaisingAuditLog())
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())

    assert result.status is ActionStatus.SUCCEEDED
    assert executor.calls


@pytest.mark.parametrize(
    ("permission_gate", "resource_gate", "audit_log", "executor_should_run"),
    [
        (RaisingPermissionGate(), None, None, False),
        (StubPermissionGate(PermissionDecision.ALLOW), RaisingResourceGate(), None, False),
        (StubPermissionGate(PermissionDecision.ALLOW), None, RaisingAuditLog(), True),
    ],
    ids=["permission_gate_raises", "resource_gate_raises", "audit_log_raises"],
)
def test_dispatch_sweep_every_internal_collaborator_fault_degrades_gracefully(
    permission_gate, resource_gate, audit_log, executor_should_run
):
    """Sprint 4.12 Acceptance Criteria, verbatim: 'No failure anywhere in
    ActionRegistry.dispatch() propagates as an unhandled exception —
    verified by a dedicated adversarial test sweeping every internal
    call site with an injected failure.' The fourth internal call site
    (executor.execute()) has its own dedicated sweep already
    (test_executor_exception_degrades_to_failed_not_raised above) since
    a RaisingExecutor needs to be the registered executor itself, not
    an additional constructor argument alongside these three."""
    registry = ActionRegistry(permission_gate, resource_gate, audit_log)
    executor = FakeExecutor(ActionType.LAUNCH_APPLICATION)
    registry.register(executor)

    result = registry.dispatch(make_request())  # must never raise, for any case above

    assert isinstance(result, ActionResult)
    if executor_should_run:
        assert executor.calls
    else:
        assert executor.calls == []
