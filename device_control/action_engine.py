"""Action Engine Foundation — the shared contract every Level 4 action
(application launch, file operation, window operation, system command,
workflow step) is built against. See docs/sprint_book/sprint_4_1.md.

This module owns exactly one thing: a typed request/result shape, an
executor interface, and a registry that dispatches a request to the
correct executor after a permission check. No application/file/window/
command logic lives here — that belongs to Sprints 4.2-4.5's own
executors, each implementing ActionExecutor.

Deliberately the same register()/lookup shape as
core.module_registry.ModuleRegistry (Sprint 1.5) — a name/type-keyed
lookup over a small protocol, reusing an already-proven pattern rather
than inventing a new one. A distinct class, not a reuse of
ModuleRegistry itself: ManagedModule answers "is this subsystem alive",
ActionExecutor answers "can you perform this specific, parameterized
action" — different questions, same shape, Single Responsibility
preserved by keeping them separate.

`workflow/` depends on this module (a WorkflowStep is, structurally,
nothing more than an ActionRequest — see Sprint 4.9), never the
reverse — Device Control is the more architecturally foundational of
the two per Part 2's own Workflow Engine example (a workflow is a
sequence of device-control-shaped steps).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from core.logging_setup import get_logger
from decision.authority import DecisionTrace
from decision.priority_queue import PriorityLevel
from security.permission_gate import PermissionDecision, PermissionGate

if TYPE_CHECKING:
    from device_control.action_log import ActionAuditLog
    from device_control.resource_gate import ActionResourceGate

logger = get_logger(__name__)

_TRANSIENT_FAILURE_MARKERS = ("timed out", "did not complete within", "critical resource pressure")
"""Substrings identifying a FAILED ActionResult as transient-shaped
(worth retrying) per Sprint 4.8's own scope: a Sprint 4.4/4.5 native-
call timeout, or a Sprint 4.6 resource-gate block. Deliberately narrow
— a genuine DENIED, a bad-path FAILED (e.g. FileNotFoundError), or any
other failure shape is never retried; retrying a non-transient failure
would be pointless and noisy, per this sprint's own Acceptance Criteria."""


class ActionType(Enum):
    """Every concrete action Sprints 4.2-4.10 implement, declared once
    here so no executor invents its own ad hoc type strings."""

    LAUNCH_APPLICATION = "launch_application"
    CLOSE_APPLICATION = "close_application"
    FILE_CREATE = "file_create"
    FILE_MOVE = "file_move"
    FILE_COPY = "file_copy"
    FILE_RENAME = "file_rename"
    FILE_DELETE = "file_delete"
    FOLDER_CREATE = "folder_create"
    FOLDER_DELETE = "folder_delete"
    WINDOW_FOCUS = "window_focus"
    WINDOW_MOVE = "window_move"
    WINDOW_RESIZE = "window_resize"
    WINDOW_MINIMIZE = "window_minimize"
    WINDOW_CLOSE = "window_close"
    SYSTEM_COMMAND = "system_command"
    WORKFLOW_STEP = "workflow_step"


class ActionStatus(Enum):
    """RECOVERED's real producer is Sprint 4.8 (Action Logging &
    Recovery) — declared here now so ActionResult never needs a
    breaking change once that sprint exists."""

    PENDING = "pending"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    APPROVED = "approved"
    DENIED = "denied"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass
class ActionContext:
    """Who/why an action was requested. decision_trace is Optional
    because not every action originates from a live conversation turn —
    a workflow step triggered by another workflow step has no single
    originating DecisionTrace to attach; None is the honest value in
    that case, not a synthetic one."""

    requested_by: str
    persona_name: str | None = None
    session_id: str | None = None
    decision_trace: DecisionTrace | None = None


@dataclass
class ActionRequest:
    """risk_hint reuses Sprint 3.10's PriorityLevel rather than a new
    enum — a known, flagged trade-off (conflates "how urgent" with "how
    risky"); Sprint 4.7 may introduce a dedicated RiskLevel instead.
    Defaults to GENERAL_SUGGESTION, the Priority Queue's own "default
    fallback for everything else"."""

    action_type: ActionType
    parameters: dict[str, object]
    context: ActionContext
    requested_at: datetime
    risk_hint: PriorityLevel = PriorityLevel.GENERAL_SUGGESTION


@dataclass
class ActionResult:
    request: ActionRequest
    status: ActionStatus
    completed_at: datetime
    output: object | None = None
    error_message: str | None = None


class ActionExecutor(Protocol):
    """Contract every concrete Level 4 executor (Application Manager,
    File & Folder Operations, Window Management, Command Execution)
    implements. Kept deliberately minimal (two methods), mirroring
    ManagedModule's own "kept deliberately minimal" precedent."""

    def can_handle(self, action_type: ActionType) -> bool: ...

    def execute(self, request: ActionRequest) -> ActionResult: ...


class ActionRegistry:
    """Constructor DI: receives the PermissionGate every dispatch()
    call consults before an executor ever runs, plus an optional
    ActionResourceGate (Sprint 4.6) consulted second, after a PermissionGate
    ALLOW and before the executor runs, plus an optional ActionAuditLog
    (Sprint 4.8) that records exactly one ActionAuditRecord per dispatch()
    call — success, denial, or failure alike — once retries (if any)
    are exhausted. All three additions default to None/0 so any caller
    from Sprint 4.1 onward keeps its exact original behavior, an
    additive, non-breaking change. Not a ManagedModule — executors
    register themselves (via the composition root, Sprint 4.11) after
    construction; there is no separate start()/stop() lifecycle of its
    own.

    No exception raised by PermissionGate.check(), ActionResourceGate.check(),
    or an executor's own execute() is ever allowed to propagate out of
    dispatch() — a failure at any of those points resolves to a
    well-formed ActionResult(status=FAILED), per the Fail Gracefully
    Rule. This mirrors AuthorityEvaluator.evaluate()'s own "fail
    safe-down, never safe-up" discipline (Sprint 3.13).

    max_retry_attempts is a plain int, not the whole DeviceControlConfig
    — this class doesn't otherwise need the full config object, and a
    single int keeps its constructor's dependency surface minimal.
    audit_log.record() always receives risk_level=None: PermissionGate's
    own check() (Sprint 4.7, security/permission_gate.py — not this
    sprint's Files to Modify) computes a RiskLevel internally but never
    returns it, so dispatch() genuinely has no RiskLevel to report —
    ActionAuditRecord.record()'s own risk_level: RiskLevel | None
    signature anticipates exactly this case, not a workaround.
    """

    def __init__(
        self,
        permission_gate: PermissionGate,
        resource_gate: ActionResourceGate | None = None,
        audit_log: ActionAuditLog | None = None,
        max_retry_attempts: int = 0,
    ) -> None:
        self._permission_gate = permission_gate
        self._resource_gate = resource_gate
        self._audit_log = audit_log
        self._max_retry_attempts = max_retry_attempts
        self._executors: list[ActionExecutor] = []

    def register(self, executor: ActionExecutor) -> None:
        self._executors.append(executor)
        logger.info("Action executor registered: %s", type(executor).__name__)

    def dispatch(self, request: ActionRequest) -> ActionResult:
        """Public entry point: runs _dispatch_once() (retrying up to
        max_retry_attempts additional times if the result is
        transient-shaped), then — if an audit_log is configured —
        records exactly one ActionAuditRecord for the final outcome,
        per this sprint's own Acceptance Criteria ("every dispatch()
        call... produces exactly one persisted ActionAuditRecord," not
        one per internal retry attempt)."""
        result, permission_decision = self._dispatch_once(request)
        max_attempts = 1 + max(self._max_retry_attempts, 0)
        attempts = 1
        while _is_transient_failure(result) and attempts < max_attempts:
            logger.info(
                "Retrying transient failure for %s (attempt %d/%d): %s",
                request.action_type.value,
                attempts + 1,
                max_attempts,
                result.error_message,
            )
            result, permission_decision = self._dispatch_once(request)
            attempts += 1

        if self._audit_log is not None:
            self._audit_log.record(result, permission_decision, None)
        return result

    def _dispatch_once(self, request: ActionRequest) -> tuple[ActionResult, PermissionDecision]:
        try:
            decision = self._permission_gate.check(request)
        except Exception:
            logger.exception(
                "PermissionGate.check() failed for action %s; denying as a safe default.",
                request.action_type.value,
            )
            return (
                ActionResult(
                    request=request,
                    status=ActionStatus.FAILED,
                    completed_at=datetime.now(UTC),
                    error_message="Permission check failed internally.",
                ),
                PermissionDecision.DENY,
            )

        if decision is PermissionDecision.DENY:
            logger.info("Action denied by PermissionGate: %s", request.action_type.value)
            return (
                ActionResult(
                    request=request,
                    status=ActionStatus.DENIED,
                    completed_at=datetime.now(UTC),
                    error_message="Denied by permission policy.",
                ),
                decision,
            )

        if decision is PermissionDecision.REQUIRE_CONFIRMATION:
            # Unreachable in Sprint 4.1 — PermissionGate's own stub
            # (security/permission_gate.py) never returns this value.
            # Written now so Sprint 4.7 (Permission & Confirmation
            # System) changes zero call sites here, only PermissionGate's
            # own internals.
            return (
                ActionResult(
                    request=request,
                    status=ActionStatus.AWAITING_CONFIRMATION,
                    completed_at=datetime.now(UTC),
                    error_message="This action requires user confirmation before it can proceed.",
                ),
                decision,
            )

        if self._resource_gate is not None:
            blocked_result = self._check_resource_gate(request)
            if blocked_result is not None:
                return blocked_result, decision

        executor = self._find_executor(request.action_type)
        if executor is None:
            logger.warning(
                "No executor registered for action type: %s", request.action_type.value
            )
            return (
                ActionResult(
                    request=request,
                    status=ActionStatus.FAILED,
                    completed_at=datetime.now(UTC),
                    error_message=(
                        f"No executor registered for action type: {request.action_type.value}"
                    ),
                ),
                decision,
            )

        try:
            return executor.execute(request), decision
        except Exception:
            logger.exception(
                "Executor %s raised while executing action: %s",
                type(executor).__name__,
                request.action_type.value,
            )
            return (
                ActionResult(
                    request=request,
                    status=ActionStatus.FAILED,
                    completed_at=datetime.now(UTC),
                    error_message="Executor raised an unexpected internal error.",
                ),
                decision,
            )

    def _check_resource_gate(self, request: ActionRequest) -> ActionResult | None:
        """None means "proceed"; a returned ActionResult means dispatch()
        should return it immediately without calling an executor.
        Imports ResourceGateDecision inside the method body, not at
        module level — device_control.resource_gate imports ActionType
        from this module, so a top-level import here would create a
        device_control-internal circular import; TYPE_CHECKING alone
        (used for the ActionResourceGate parameter's own type hint
        above) isn't enough since this comparison needs the real enum
        value at runtime, not just an annotation."""
        from device_control.resource_gate import ResourceGateDecision

        try:
            decision = self._resource_gate.check(request.action_type)
        except Exception:
            logger.exception(
                "ActionResourceGate.check() failed for action %s; "
                "failing safe-down rather than optimistically proceeding.",
                request.action_type.value,
            )
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Resource check failed internally.",
            )

        if decision is ResourceGateDecision.PROCEED:
            return None

        alerts = self._resource_gate.last_blocked_alerts()
        resource_summary = ", ".join(f"{a.resource} at {a.value:.1f}% (critical)" for a in alerts)
        logger.info(
            "Action blocked by ActionResourceGate: %s (%s)",
            request.action_type.value,
            resource_summary,
        )
        return ActionResult(
            request=request,
            status=ActionStatus.FAILED,
            completed_at=datetime.now(UTC),
            error_message=f"Blocked by critical resource pressure: {resource_summary}",
        )

    def _find_executor(self, action_type: ActionType) -> ActionExecutor | None:
        for executor in self._executors:
            if executor.can_handle(action_type):
                return executor
        return None


def _is_transient_failure(result: ActionResult) -> bool:
    if result.status is not ActionStatus.FAILED or not result.error_message:
        return False
    lowered = result.error_message.lower()
    return any(marker in lowered for marker in _TRANSIENT_FAILURE_MARKERS)
