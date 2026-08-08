"""Unit tests for workflow.workflow_executor.

FakeActionRegistry/FakeWorkflowStore/FakeConfirmationService are local,
duck-typed doubles at WorkflowExecutor's own collaborator boundaries —
matching tests/unit/device_control/test_action_engine.py's established
"fake at the boundary" convention. PermissionPolicyEngine is used for
real (SecurityConfig()'s own built-in RiskLevel defaults), the same
"prefer a real, cheap collaborator over a fake" precedent
test_action_engine.py's own real_permission_gate fixture already set.
"""

from datetime import UTC, datetime

import pytest

from config.schema import SecurityConfig, WorkflowConfig
from device_control.action_engine import (
    ActionContext,
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)
from security.confirmation_service import ConfirmationOutcome, ConfirmationRequest
from security.policy_engine import PermissionPolicyEngine
from workflow.workflow_executor import WorkflowExecutor
from workflow.workflow_model import WorkflowDefinition, WorkflowStep


def make_step(
    step_index: int,
    action_type: ActionType = ActionType.WINDOW_FOCUS,
    continue_on_failure: bool = False,
    parameters: dict | None = None,
) -> WorkflowStep:
    return WorkflowStep(
        step_index=step_index,
        action_type=action_type,
        parameters=parameters if parameters is not None else {},
        description=f"Step {step_index}",
        continue_on_failure=continue_on_failure,
    )


def make_definition(
    steps: list[WorkflowStep],
    workflow_id: str = "wf-1",
    name: str = "Test Workflow",
    is_enabled: bool = True,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id=workflow_id,
        name=name,
        steps=steps,
        created_by="user_voice",
        created_at=datetime(2026, 7, 21, 10, 0, 0, tzinfo=UTC),
        is_enabled=is_enabled,
    )


class FakeWorkflowStore:
    def __init__(self, definition: WorkflowDefinition | None) -> None:
        self._definition = definition
        self.recorded_runs: list[tuple[str, datetime]] = []

    def get(self, workflow_id: str) -> WorkflowDefinition | None:
        return self._definition

    def record_run(self, workflow_id: str, run_at: datetime) -> None:
        self.recorded_runs.append((workflow_id, run_at))


class FakeActionRegistry:
    """Records every dispatched ActionRequest; returns statuses from a
    pre-queued list, in dispatch order, defaulting to SUCCEEDED once the
    queue is exhausted."""

    def __init__(self, statuses: list[ActionStatus] | None = None) -> None:
        self.dispatched: list[ActionRequest] = []
        self._statuses = list(statuses) if statuses is not None else []

    def dispatch(self, request: ActionRequest) -> ActionResult:
        self.dispatched.append(request)
        status = self._statuses.pop(0) if self._statuses else ActionStatus.SUCCEEDED
        error_message = "boom" if status in (ActionStatus.FAILED, ActionStatus.DENIED) else None
        return ActionResult(
            request=request,
            status=status,
            completed_at=datetime.now(UTC),
            error_message=error_message,
        )


class FakeConfirmationService:
    def __init__(self, outcome: ConfirmationOutcome = ConfirmationOutcome.CONFIRMED) -> None:
        self.outcome = outcome
        self.requests: list[ConfirmationRequest] = []

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationOutcome:
        self.requests.append(request)
        return self.outcome


def make_executor(
    definition: WorkflowDefinition | None,
    statuses: list[ActionStatus] | None = None,
    confirmation_outcome: ConfirmationOutcome = ConfirmationOutcome.CONFIRMED,
    workflow_config: WorkflowConfig | None = None,
) -> tuple[WorkflowExecutor, FakeActionRegistry, FakeConfirmationService]:
    registry = FakeActionRegistry(statuses)
    confirmation_service = FakeConfirmationService(confirmation_outcome)
    executor = WorkflowExecutor(
        workflow_store=FakeWorkflowStore(definition),
        action_registry=registry,
        permission_policy_engine=PermissionPolicyEngine(SecurityConfig()),
        confirmation_service=confirmation_service,
        workflow_config=workflow_config if workflow_config is not None else WorkflowConfig(),
    )
    return executor, registry, confirmation_service


BASE_CONTEXT = ActionContext(requested_by="test_caller", persona_name="jarvis", session_id="s1")


# --- Full successful multi-step run --------------------------------------------------


def test_full_successful_run_executes_every_step_in_order():
    steps = [make_step(i) for i in range(3)]
    definition = make_definition(steps)
    executor, registry, confirmation_service = make_executor(definition)

    result = executor.run("wf-1", BASE_CONTEXT)

    assert result.workflow_id == "wf-1"
    assert result.aborted_early is False
    assert len(result.step_results) == 3
    assert [sr.action_result.status for sr in result.step_results] == [ActionStatus.SUCCEEDED] * 3
    assert all(not sr.skipped for sr in result.step_results)
    assert len(registry.dispatched) == 3
    assert confirmation_service.requests == []  # small, low-risk workflow: no whole-workflow prompt
    assert result.whole_workflow_confirmation is None
    assert result.run_id
    assert result.completed_at >= result.started_at


def test_step_requests_are_rewritten_with_workflow_requested_by():
    steps = [make_step(0, parameters={"executable_path": "code.exe"})]
    definition = make_definition(steps, workflow_id="wf-rewrite")
    executor, registry, _ = make_executor(definition)

    executor.run("wf-rewrite", BASE_CONTEXT)

    dispatched = registry.dispatched[0]
    assert dispatched.context.requested_by == "workflow:wf-rewrite"
    assert dispatched.context.persona_name == "jarvis"
    assert dispatched.context.session_id == "s1"
    assert dispatched.parameters == {"executable_path": "code.exe"}


# --- Abort-on-failure with correct skipped marking ------------------------------------


def test_failure_with_continue_on_failure_false_aborts_and_skips_remaining_steps():
    steps = [
        make_step(0, continue_on_failure=False),
        make_step(1, continue_on_failure=False),
        make_step(2, continue_on_failure=False),
    ]
    definition = make_definition(steps)
    executor, registry, _ = make_executor(definition, statuses=[ActionStatus.FAILED])

    result = executor.run("wf-1", BASE_CONTEXT)

    assert result.aborted_early is True
    assert len(registry.dispatched) == 1  # only the failed step was ever dispatched
    assert result.step_results[0].skipped is False
    assert result.step_results[0].action_result.status is ActionStatus.FAILED
    assert result.step_results[1].skipped is True
    assert result.step_results[1].action_result.status is ActionStatus.PENDING
    assert "Skipped" in result.step_results[1].action_result.error_message
    assert result.step_results[2].skipped is True


def test_denied_step_with_continue_on_failure_false_aborts_the_run():
    steps = [make_step(0, continue_on_failure=False), make_step(1, continue_on_failure=False)]
    definition = make_definition(steps)
    executor, registry, _ = make_executor(definition, statuses=[ActionStatus.DENIED])

    result = executor.run("wf-1", BASE_CONTEXT)

    assert result.aborted_early is True
    assert len(registry.dispatched) == 1
    assert result.step_results[1].skipped is True


# --- continue_on_failure=True allows the run to proceed -------------------------------


def test_continue_on_failure_true_proceeds_past_a_failed_step():
    steps = [
        make_step(0, continue_on_failure=True),
        make_step(1, continue_on_failure=False),
    ]
    definition = make_definition(steps)
    executor, registry, _ = make_executor(
        definition, statuses=[ActionStatus.FAILED, ActionStatus.SUCCEEDED]
    )

    result = executor.run("wf-1", BASE_CONTEXT)

    assert result.aborted_early is False
    assert len(registry.dispatched) == 2
    assert result.step_results[0].action_result.status is ActionStatus.FAILED
    assert result.step_results[0].skipped is False
    assert result.step_results[1].action_result.status is ActionStatus.SUCCEEDED
    assert result.step_results[1].skipped is False


# --- Whole-workflow confirmation: step-count threshold --------------------------------


def test_whole_workflow_confirmation_triggers_at_step_count_threshold():
    steps = [make_step(i) for i in range(5)]  # WINDOW_FOCUS is LOW risk; default threshold is 5
    definition = make_definition(steps, name="Morning Routine")
    executor, registry, confirmation_service = make_executor(definition)

    result = executor.run("wf-1", BASE_CONTEXT)

    assert len(confirmation_service.requests) == 1
    prompt_text = confirmation_service.requests[0].prompt_text
    assert "Morning Routine" in prompt_text
    assert "5 actions" in prompt_text
    # Sprint 4.13 (Technical Debt Resolution, backlog/technical_debt.md
    # item 25): tells VoiceConfirmationService to speak this richer
    # template text verbatim rather than rebuilding a generic one.
    assert confirmation_service.requests[0].has_custom_prompt is True
    assert result.whole_workflow_confirmation is ConfirmationOutcome.CONFIRMED
    assert len(registry.dispatched) == 5  # confirmed -> steps still run


def test_whole_workflow_confirmation_not_triggered_below_threshold_and_low_risk():
    steps = [make_step(i) for i in range(4)]  # below default threshold of 5, all LOW risk
    definition = make_definition(steps)
    executor, registry, confirmation_service = make_executor(definition)

    executor.run("wf-1", BASE_CONTEXT)

    assert confirmation_service.requests == []
    assert len(registry.dispatched) == 4


# --- Whole-workflow confirmation: any HIGH-risk step, even under threshold -----------


def test_whole_workflow_confirmation_triggers_on_any_high_risk_step_under_threshold():
    steps = [make_step(0, action_type=ActionType.FILE_DELETE, parameters={"path": "a.txt"})]
    definition = make_definition(steps)
    executor, registry, confirmation_service = make_executor(definition)

    result = executor.run("wf-1", BASE_CONTEXT)

    assert len(confirmation_service.requests) == 1
    assert "1 higher-risk" in confirmation_service.requests[0].prompt_text
    assert result.whole_workflow_confirmation is ConfirmationOutcome.CONFIRMED
    assert len(registry.dispatched) == 1


# --- Declined/timed-out whole-workflow confirmation aborts before any dispatch() ------


@pytest.mark.parametrize("outcome", [ConfirmationOutcome.DECLINED, ConfirmationOutcome.TIMED_OUT])
def test_declined_or_timed_out_confirmation_aborts_before_any_step_dispatches(outcome):
    steps = [make_step(i) for i in range(5)]
    definition = make_definition(steps)
    executor, registry, confirmation_service = make_executor(
        definition, confirmation_outcome=outcome
    )

    result = executor.run("wf-1", BASE_CONTEXT)

    assert result.aborted_early is True
    assert result.whole_workflow_confirmation is outcome
    assert result.step_results == []
    assert registry.dispatched == []  # the spy proof: dispatch() is never called


# --- Disabled/nonexistent workflow handling --------------------------------------------


def test_disabled_workflow_is_rejected_before_any_confirmation_or_step():
    steps = [make_step(i) for i in range(5)]  # would otherwise trigger confirmation
    definition = make_definition(steps, is_enabled=False)
    executor, registry, confirmation_service = make_executor(definition)

    result = executor.run("wf-1", BASE_CONTEXT)

    assert result.aborted_early is True
    assert result.step_results == []
    assert confirmation_service.requests == []
    assert registry.dispatched == []


def test_nonexistent_workflow_id_degrades_to_reportable_abort_not_exception():
    executor, registry, confirmation_service = make_executor(definition=None)

    result = executor.run("does-not-exist", BASE_CONTEXT)

    assert result.workflow_id == "does-not-exist"
    assert result.aborted_early is True
    assert result.step_results == []
    assert result.whole_workflow_confirmation is None
    assert confirmation_service.requests == []
    assert registry.dispatched == []


# --- Sprint 6.7 (Learning Engine v2): record_run() call site ------------------------


def _make_executor_with_visible_workflow_store(
    definition: WorkflowDefinition | None,
    confirmation_outcome: ConfirmationOutcome = ConfirmationOutcome.CONFIRMED,
) -> tuple[WorkflowExecutor, FakeWorkflowStore, FakeActionRegistry]:
    workflow_store = FakeWorkflowStore(definition)
    registry = FakeActionRegistry()
    executor = WorkflowExecutor(
        workflow_store=workflow_store,
        action_registry=registry,
        permission_policy_engine=PermissionPolicyEngine(SecurityConfig()),
        confirmation_service=FakeConfirmationService(confirmation_outcome),
        workflow_config=WorkflowConfig(),
    )
    return executor, workflow_store, registry


def test_record_run_called_once_a_workflow_starts_executing():
    steps = [make_step(i) for i in range(3)]
    definition = make_definition(steps)
    executor, workflow_store, _ = _make_executor_with_visible_workflow_store(definition)

    result = executor.run("wf-1", BASE_CONTEXT)

    assert workflow_store.recorded_runs == [("wf-1", result.started_at)]


def test_record_run_not_called_for_a_disabled_workflow():
    steps = [make_step(i) for i in range(3)]
    definition = make_definition(steps, is_enabled=False)
    executor, workflow_store, _ = _make_executor_with_visible_workflow_store(definition)

    executor.run("wf-1", BASE_CONTEXT)

    assert workflow_store.recorded_runs == []


def test_record_run_not_called_for_a_nonexistent_workflow():
    executor, workflow_store, _ = _make_executor_with_visible_workflow_store(definition=None)

    executor.run("does-not-exist", BASE_CONTEXT)

    assert workflow_store.recorded_runs == []


def test_record_run_not_called_when_whole_workflow_confirmation_is_declined():
    steps = [make_step(i) for i in range(5)]  # triggers the whole-workflow prompt
    definition = make_definition(steps)
    executor, workflow_store, _ = _make_executor_with_visible_workflow_store(
        definition, confirmation_outcome=ConfirmationOutcome.DECLINED
    )

    executor.run("wf-1", BASE_CONTEXT)

    assert workflow_store.recorded_runs == []


class RaisingRecordRunWorkflowStore:
    """A real, non-raising get() (the run must genuinely start) paired
    with a record_run() that raises — proves a run-history recording
    failure never aborts or affects the real workflow execution."""

    def __init__(self, definition: WorkflowDefinition) -> None:
        self._definition = definition

    def get(self, workflow_id: str) -> WorkflowDefinition | None:
        return self._definition

    def record_run(self, workflow_id: str, run_at) -> None:
        raise RuntimeError("record_run() exploded")


def test_record_run_failure_does_not_abort_the_run():
    steps = [make_step(i) for i in range(3)]
    definition = make_definition(steps)
    registry = FakeActionRegistry()
    executor = WorkflowExecutor(
        workflow_store=RaisingRecordRunWorkflowStore(definition),
        action_registry=registry,
        permission_policy_engine=PermissionPolicyEngine(SecurityConfig()),
        confirmation_service=FakeConfirmationService(),
        workflow_config=WorkflowConfig(),
    )

    result = executor.run("wf-1", BASE_CONTEXT)  # must not raise

    assert result.aborted_early is False
    assert len(registry.dispatched) == 3


# --- Sprint 4.12 hardening (scenario d): internal faults never propagate ------------


class RaisingWorkflowStore:
    def get(self, workflow_id: str):
        raise RuntimeError("workflow_store.get() exploded")


class RaisingActionRegistry:
    def __init__(self) -> None:
        self.dispatched: list[ActionRequest] = []

    def dispatch(self, request: ActionRequest) -> ActionResult:
        self.dispatched.append(request)
        raise RuntimeError("dispatch() exploded")


class RaisingConfirmationService:
    def __init__(self) -> None:
        self.requests: list[ConfirmationRequest] = []

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationOutcome:
        self.requests.append(request)
        raise RuntimeError("request_confirmation() exploded")


def test_workflow_store_get_exception_degrades_to_reportable_abort_not_exception():
    executor = WorkflowExecutor(
        workflow_store=RaisingWorkflowStore(),
        action_registry=FakeActionRegistry(),
        permission_policy_engine=PermissionPolicyEngine(SecurityConfig()),
        confirmation_service=FakeConfirmationService(),
        workflow_config=WorkflowConfig(),
    )

    result = executor.run("wf-1", BASE_CONTEXT)  # must not raise

    assert result.aborted_early is True
    assert result.step_results == []


def test_confirmation_service_exception_times_out_and_aborts_before_any_dispatch():
    steps = [make_step(i) for i in range(5)]  # triggers the whole-workflow prompt
    definition = make_definition(steps)
    registry = FakeActionRegistry()
    executor = WorkflowExecutor(
        workflow_store=FakeWorkflowStore(definition),
        action_registry=registry,
        permission_policy_engine=PermissionPolicyEngine(SecurityConfig()),
        confirmation_service=RaisingConfirmationService(),
        workflow_config=WorkflowConfig(),
    )

    result = executor.run("wf-1", BASE_CONTEXT)  # must not raise

    assert result.aborted_early is True
    assert result.whole_workflow_confirmation is ConfirmationOutcome.TIMED_OUT
    assert registry.dispatched == []


def test_dispatch_exception_preserves_prior_step_results_and_marks_the_fault_distinctly():
    steps = [make_step(0), make_step(1, continue_on_failure=False), make_step(2)]
    definition = make_definition(steps)
    registry = RaisingActionRegistry()
    executor = WorkflowExecutor(
        workflow_store=FakeWorkflowStore(definition),
        action_registry=registry,
        permission_policy_engine=PermissionPolicyEngine(SecurityConfig()),
        confirmation_service=FakeConfirmationService(),
        workflow_config=WorkflowConfig(),
    )

    result = executor.run("wf-1", BASE_CONTEXT)  # must not raise

    assert len(registry.dispatched) == 1  # aborted after the first step's own fault
    assert result.aborted_early is True
    assert len(result.step_results) == 3
    assert result.step_results[0].action_result.status is ActionStatus.FAILED
    assert "internal executor fault" in result.step_results[0].action_result.error_message.lower()
    assert result.step_results[1].skipped is True
    assert result.step_results[2].skipped is True


@pytest.mark.parametrize(
    ("steps_count", "workflow_store_raises", "confirmation_raises", "dispatch_raises"),
    [
        (1, True, False, False),
        (5, False, True, False),
        (2, False, False, True),
    ],
    ids=[
        "workflow_store_get_raises",
        "confirmation_service_raises",
        "action_registry_dispatch_raises",
    ],
)
def test_run_sweep_every_internal_call_site_fault_degrades_gracefully(
    steps_count, workflow_store_raises, confirmation_raises, dispatch_raises
):
    """Sprint 4.12 Acceptance Criteria, verbatim: 'No failure anywhere in
    ... WorkflowExecutor.run() propagates as an unhandled exception —
    verified by a dedicated adversarial test sweeping every internal
    call site with an injected failure.' Consolidates the three
    individual scenario-d tests above (each with its own, more specific
    assertions) into one explicit sweep across all three of run()'s own
    internal call sites."""
    steps = [make_step(i) for i in range(steps_count)]
    definition = make_definition(steps)

    workflow_store = (
        RaisingWorkflowStore() if workflow_store_raises else FakeWorkflowStore(definition)
    )
    confirmation_service = (
        RaisingConfirmationService() if confirmation_raises else FakeConfirmationService()
    )
    action_registry = RaisingActionRegistry() if dispatch_raises else FakeActionRegistry()

    executor = WorkflowExecutor(
        workflow_store=workflow_store,
        action_registry=action_registry,
        permission_policy_engine=PermissionPolicyEngine(SecurityConfig()),
        confirmation_service=confirmation_service,
        workflow_config=WorkflowConfig(),
    )

    result = executor.run("wf-1", BASE_CONTEXT)  # must never raise, for any case above

    assert result.aborted_early is True
