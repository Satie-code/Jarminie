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
from typing import Protocol

from core.logging_setup import get_logger
from decision.authority import DecisionTrace
from decision.priority_queue import PriorityLevel
from security.permission_gate import PermissionDecision, PermissionGate

logger = get_logger(__name__)


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
    call consults before an executor ever runs. Not a ManagedModule —
    executors register themselves (via the composition root, Sprint
    4.11) after construction; there is no separate start()/stop()
    lifecycle of its own.

    No exception raised by PermissionGate.check() or an executor's own
    execute() is ever allowed to propagate out of dispatch() — a
    failure at either point resolves to a well-formed
    ActionResult(status=FAILED), per the Fail Gracefully Rule. This
    mirrors AuthorityEvaluator.evaluate()'s own "fail safe-down, never
    safe-up" discipline (Sprint 3.13).
    """

    def __init__(self, permission_gate: PermissionGate) -> None:
        self._permission_gate = permission_gate
        self._executors: list[ActionExecutor] = []

    def register(self, executor: ActionExecutor) -> None:
        self._executors.append(executor)
        logger.info("Action executor registered: %s", type(executor).__name__)

    def dispatch(self, request: ActionRequest) -> ActionResult:
        try:
            decision = self._permission_gate.check(request)
        except Exception:
            logger.exception(
                "PermissionGate.check() failed for action %s; denying as a safe default.",
                request.action_type.value,
            )
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Permission check failed internally.",
            )

        if decision is PermissionDecision.DENY:
            logger.info("Action denied by PermissionGate: %s", request.action_type.value)
            return ActionResult(
                request=request,
                status=ActionStatus.DENIED,
                completed_at=datetime.now(UTC),
                error_message="Denied by permission policy.",
            )

        if decision is PermissionDecision.REQUIRE_CONFIRMATION:
            # Unreachable in Sprint 4.1 — PermissionGate's own stub
            # (security/permission_gate.py) never returns this value.
            # Written now so Sprint 4.7 (Permission & Confirmation
            # System) changes zero call sites here, only PermissionGate's
            # own internals.
            return ActionResult(
                request=request,
                status=ActionStatus.AWAITING_CONFIRMATION,
                completed_at=datetime.now(UTC),
                error_message="This action requires user confirmation before it can proceed.",
            )

        executor = self._find_executor(request.action_type)
        if executor is None:
            logger.warning(
                "No executor registered for action type: %s", request.action_type.value
            )
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message=(
                    f"No executor registered for action type: {request.action_type.value}"
                ),
            )

        try:
            return executor.execute(request)
        except Exception:
            logger.exception(
                "Executor %s raised while executing action: %s",
                type(executor).__name__,
                request.action_type.value,
            )
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Executor raised an unexpected internal error.",
            )

    def _find_executor(self, action_type: ActionType) -> ActionExecutor | None:
        for executor in self._executors:
            if executor.can_handle(action_type):
                return executor
        return None
