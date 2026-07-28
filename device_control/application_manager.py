"""Application Manager — Level 4's first real ActionExecutor: launch,
list, focus, and close applications. See docs/sprint_book/sprint_4_2.md.

Only ever acts on a process it itself launched and tracked — a hard,
structural safety boundary, not a convenience default. There is no
"close/focus any running application by PID" capability here; that
would be a materially higher-risk capability requiring its own
Permission & Confirmation System (Sprint 4.7) review.

Sprint 4.12 hardening (scenario a): launch() no longer just fires
subprocess.Popen() and trusts it blindly — it also performs a short,
bounded, non-blocking-on-exit liveness check (device_control_config.
application_launch_readiness_check_seconds) confirming the process is
still running shortly after spawn, not already dead. This is a
best-effort heuristic only, not a real "is this arbitrary application
responsive" guarantee — no universal OS-level signal for that exists
without a window handle, which many valid launches (CLI/background
processes) never create at all. ActionStatus is still always SUCCEEDED
once Popen() itself succeeds (the process DID spawn — reporting FAILED
would be dishonest); the distinction lives in TrackedApplication's own
new readiness_confirmed field, which ActionAuditLog (Sprint 4.8) also
now surfaces in its parameters_summary.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import psutil
import win32gui
import win32process

from config.schema import DeviceControlConfig
from core.logging_setup import get_logger
from device_control.action_engine import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)

logger = get_logger(__name__)

_HANDLED_TYPES = frozenset({ActionType.LAUNCH_APPLICATION, ActionType.CLOSE_APPLICATION})
_PROCESS_TERMINATE_TIMEOUT_SECONDS = 5
_READINESS_POLL_INTERVAL_SECONDS = 0.05


@dataclass
class TrackedApplication:
    """One application this manager itself launched. launched_via is
    the ActionContext.requested_by value that launched it, kept for
    Sprint 4.8's (Action Logging & Recovery) own audit trail.
    readiness_confirmed (Sprint 4.12) is True once launch()'s own
    bounded post-spawn check found the process still running — False
    means it had already exited within that short window (a real,
    worth-surfacing signal that it may have crashed immediately or
    never truly started), not that the launch itself failed."""

    process_id: int
    executable_path: str
    launched_at: datetime
    launched_via: str
    readiness_confirmed: bool = True


class ApplicationManager:
    """Constructor DI: (device_control_config). Handles
    ActionType.LAUNCH_APPLICATION/CLOSE_APPLICATION — FOCUS and LIST are
    routed as sub-operations of the same two action types via
    ActionRequest.parameters["operation"], not separate ActionType
    values (they are read/low-risk variants of the same "application"
    concern per this sprint's own spec).

    execute() only ever catches OSError/psutil.Error — errors this
    class can meaningfully interpret and report — never a bare except,
    per docs/CODING_STANDARDS.md.
    """

    def __init__(self, device_control_config: DeviceControlConfig) -> None:
        self._config = device_control_config
        self._tracked: dict[int, TrackedApplication] = {}

    def can_handle(self, action_type: ActionType) -> bool:
        return action_type in _HANDLED_TYPES

    def execute(self, request: ActionRequest) -> ActionResult:
        operation = request.parameters.get("operation")
        try:
            if operation == "launch":
                return self._handle_launch(request)
            if operation == "close":
                return self._handle_close(request)
            if operation == "focus":
                return self._handle_focus(request)
            if operation == "list":
                return self._handle_list(request)
        except (OSError, psutil.Error) as exc:
            logger.exception("ApplicationManager operation %r failed", operation)
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message=str(exc),
            )
        return ActionResult(
            request=request,
            status=ActionStatus.FAILED,
            completed_at=datetime.now(UTC),
            error_message=f"Unknown or missing operation: {operation!r}",
        )

    def launch(
        self, executable_path: str, requested_by: str, args: list[str] | None = None
    ) -> TrackedApplication:
        """Spawns executable_path (optionally with args) and tracks the
        resulting process. Raises OSError (e.g. FileNotFoundError) for a
        bad path — callers going through execute() get that converted
        to ActionStatus.FAILED; direct callers see the real exception.
        """
        process = subprocess.Popen([executable_path, *(args or [])])
        readiness_confirmed = self._confirm_process_alive(
            process, self._config.application_launch_readiness_check_seconds
        )
        tracked = TrackedApplication(
            process_id=process.pid,
            executable_path=executable_path,
            launched_at=datetime.now(UTC),
            launched_via=requested_by,
            readiness_confirmed=readiness_confirmed,
        )
        self._tracked[tracked.process_id] = tracked
        if readiness_confirmed:
            logger.info("Application launched: %s (pid=%d)", executable_path, tracked.process_id)
        else:
            logger.warning(
                "Application %s (pid=%d) could not be confirmed alive within %.2fs of "
                "launch — it may have exited immediately or be hung at OS level.",
                executable_path,
                tracked.process_id,
                self._config.application_launch_readiness_check_seconds,
            )
        return tracked

    def _confirm_process_alive(self, process: subprocess.Popen, timeout_seconds: float) -> bool:
        """Sprint 4.12 hardening (scenario a): a bounded, non-blocking-
        on-exit poll — never waits for the process to exit, only checks
        whether it already has. Deliberately a liveness check, not a
        real readiness/responsiveness check: this module has no
        universal way to know an arbitrary application has become
        interactive (many valid launches, e.g. CLI/background processes,
        never create a window at all), so "still running after a short
        bound" is the most honest signal available without one."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return False
            time.sleep(_READINESS_POLL_INTERVAL_SECONDS)
        return process.poll() is None

    def close(self, process_id: int) -> bool:
        """False if process_id isn't tracked by this manager — refuses
        to touch anything it didn't itself launch. A process that
        already exited on its own before close() runs is treated as a
        successful close (nothing left to terminate), not a failure."""
        if process_id not in self._tracked:
            logger.warning("Refused to close untracked process: %d", process_id)
            return False
        try:
            process = psutil.Process(process_id)
            process.terminate()
            try:
                process.wait(timeout=_PROCESS_TERMINATE_TIMEOUT_SECONDS)
            except psutil.TimeoutExpired:
                process.kill()
        except psutil.NoSuchProcess:
            logger.info("Process %d had already exited before close() ran.", process_id)
        del self._tracked[process_id]
        logger.info("Application closed: pid=%d", process_id)
        return True

    def list_tracked(self) -> list[TrackedApplication]:
        return list(self._tracked.values())

    def focus(self, process_id: int) -> bool:
        """False if process_id isn't tracked, or if it has no
        currently-visible top-level window — a launched CLI/background
        process with no window is a real, expected case, not an error.
        """
        if process_id not in self._tracked:
            logger.warning("Refused to focus untracked process: %d", process_id)
            return False
        hwnd = self._find_window_for_process(process_id)
        if hwnd is None:
            logger.warning("No visible window found for tracked process: %d", process_id)
            return False
        win32gui.SetForegroundWindow(hwnd)
        logger.info("Focused window for process: %d", process_id)
        return True

    def _find_window_for_process(self, process_id: int) -> int | None:
        """First visible top-level window belonging to process_id, or
        None. "First", not "best" — no ranking, matching this project's
        consistent plain-match discipline for similar lookups (e.g.
        PersonaManager's trigger phrases)."""
        found: list[int] = []

        def _handler(hwnd: int, _extra: object) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            _, owner_pid = win32process.GetWindowThreadProcessId(hwnd)
            if owner_pid == process_id:
                found.append(hwnd)

        win32gui.EnumWindows(_handler, None)
        return found[0] if found else None

    def _handle_launch(self, request: ActionRequest) -> ActionResult:
        executable_path = request.parameters.get("executable_path")
        if not executable_path:
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Missing required parameter: executable_path",
            )
        if len(self._tracked) >= self._config.max_tracked_applications:
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message=(
                    f"max_tracked_applications ({self._config.max_tracked_applications}) reached"
                ),
            )
        args = request.parameters.get("args")
        tracked = self.launch(
            executable_path, requested_by=request.context.requested_by, args=args
        )
        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
            output=tracked,
        )

    def _handle_close(self, request: ActionRequest) -> ActionResult:
        process_id = request.parameters.get("process_id")
        if process_id is None:
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Missing required parameter: process_id",
            )
        if process_id not in self._tracked:
            return ActionResult(
                request=request,
                status=ActionStatus.DENIED,
                completed_at=datetime.now(UTC),
                error_message=f"Refusing to close untracked process: {process_id}",
            )
        closed = self.close(process_id)
        status = ActionStatus.SUCCEEDED if closed else ActionStatus.FAILED
        return ActionResult(request=request, status=status, completed_at=datetime.now(UTC))

    def _handle_focus(self, request: ActionRequest) -> ActionResult:
        process_id = request.parameters.get("process_id")
        if process_id is None:
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Missing required parameter: process_id",
            )
        if process_id not in self._tracked:
            return ActionResult(
                request=request,
                status=ActionStatus.DENIED,
                completed_at=datetime.now(UTC),
                error_message=f"Refusing to focus untracked process: {process_id}",
            )
        focused = self.focus(process_id)
        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED if focused else ActionStatus.FAILED,
            completed_at=datetime.now(UTC),
            error_message=None if focused else "No focusable window found for this process.",
        )

    def _handle_list(self, request: ActionRequest) -> ActionResult:
        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
            output=self.list_tracked(),
        )
