"""Window Management — Level 4's third real ActionExecutor: enumerate,
focus, move, resize, minimize, maximize, and close windows. See
docs/sprint_book/sprint_4_4.md.

Window identification is always by a real, stable HWND — resolved once
per execute() call, before any operation runs, and never re-resolved
mid-operation. Title/process-id lookups (find_by_title/find_for_process)
are convenience paths that resolve to an HWND up front, never a
substitute for one.

Operates on *any* visible window, not only ones ApplicationManager
(Sprint 4.2) itself launched — unlike ApplicationManager's stricter
"only ever touch what it tracked" boundary, a window move/resize/
minimize/maximize is a far more reversible, lower-consequence action.
WINDOW_CLOSE (sent as a polite WM_CLOSE, not a forced termination) is
the one operation here with a real, if usually reversible, destructive
shape.

There is no ActionType.WINDOW_MAXIMIZE — action_engine.py's ActionType
enum (Sprint 4.1) only declares WINDOW_FOCUS/MOVE/RESIZE/MINIMIZE/CLOSE,
and this sprint's own Files to Modify excludes that file. Minimize and
maximize are both dispatched under ActionType.WINDOW_MINIMIZE via
parameters["operation"], mirroring ApplicationManager's own established
"operation string, not the ActionType, is the real dispatch key"
pattern for its focus/list sub-operations.

execute() only ever catches pywintypes.error (a failed native Win32
call) and TimeoutError (a call that exceeded
window_operation_timeout_seconds) — never a bare except, per
docs/CODING_STANDARDS.md. Every native call is routed through
_call_with_timeout(), since SetForegroundWindow/MoveWindow/ShowWindow
can block on an unresponsive target window's own message queue.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pywintypes
import win32con
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

_HANDLED_TYPES = frozenset(
    {
        ActionType.WINDOW_FOCUS,
        ActionType.WINDOW_MOVE,
        ActionType.WINDOW_RESIZE,
        ActionType.WINDOW_MINIMIZE,
        ActionType.WINDOW_CLOSE,
    }
)


@dataclass
class WindowInfo:
    """handle is the real HWND (pywin32's native window identifier).
    bounds is (left, top, right, bottom), matching win32gui.GetWindowRect's
    own return shape directly rather than reformatting it."""

    handle: int
    title: str
    process_id: int
    is_minimized: bool
    is_maximized: bool
    bounds: tuple[int, int, int, int]


class WindowManager:
    """Constructor DI: (device_control_config). Handles
    ActionType.WINDOW_FOCUS/WINDOW_MOVE/WINDOW_RESIZE/WINDOW_MINIMIZE/
    WINDOW_CLOSE — parameters["operation"] (one of "focus", "move",
    "resize", "minimize", "maximize", "close") is the real dispatch
    key, matching ApplicationManager's own precedent.

    Every request resolves its target window once via
    parameters["handle"], parameters["title_contains"], or
    parameters["process_id"] (checked in that order) before any
    operation runs.
    """

    def __init__(self, device_control_config: DeviceControlConfig) -> None:
        self._config = device_control_config

    def can_handle(self, action_type: ActionType) -> bool:
        return action_type in _HANDLED_TYPES

    def execute(self, request: ActionRequest) -> ActionResult:
        operation = request.parameters.get("operation")
        try:
            target = self._resolve_target(request.parameters)
            if target is None:
                return ActionResult(
                    request=request,
                    status=ActionStatus.FAILED,
                    completed_at=datetime.now(UTC),
                    error_message=(
                        "No matching window found for the given handle/"
                        "title_contains/process_id (stale, closed, or no match)."
                    ),
                )
            if operation == "focus":
                return self._handle_focus(request, target)
            if operation == "move":
                return self._handle_move(request, target)
            if operation == "resize":
                return self._handle_resize(request, target)
            if operation == "minimize":
                return self._handle_minimize(request, target)
            if operation == "maximize":
                return self._handle_maximize(request, target)
            if operation == "close":
                return self._handle_close(request, target)
        except (pywintypes.error, TimeoutError) as exc:
            logger.exception("Window operation %r failed", operation)
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

    def list_windows(self) -> list[WindowInfo]:
        handles: list[int] = []

        def _collect(hwnd: int, _extra: object) -> None:
            if win32gui.IsWindowVisible(hwnd):
                handles.append(hwnd)

        win32gui.EnumWindows(_collect, None)
        return [self._window_info(hwnd) for hwnd in handles]

    def find_by_title(self, title_contains: str) -> WindowInfo | None:
        """Case-insensitive substring match over list_windows(); returns
        the first match — "first match," not "best match," matching
        this project's consistent plain-substring-match discipline
        (e.g. PersonaManager's trigger phrases)."""
        needle = title_contains.lower()
        for info in self.list_windows():
            if needle in info.title.lower():
                return info
        return None

    def find_for_process(self, process_id: int) -> WindowInfo | None:
        """The TrackedApplication (Sprint 4.2) convenience path — first
        visible window owned by process_id, or None."""
        for info in self.list_windows():
            if info.process_id == process_id:
                return info
        return None

    def _resolve_target(self, parameters: dict[str, object]) -> WindowInfo | None:
        handle = parameters.get("handle")
        if handle is not None:
            if not win32gui.IsWindow(handle):
                return None
            return self._window_info(int(handle))
        title_contains = parameters.get("title_contains")
        if title_contains:
            return self.find_by_title(str(title_contains))
        process_id = parameters.get("process_id")
        if process_id is not None:
            return self.find_for_process(int(process_id))
        return None

    def _window_info(self, handle: int) -> WindowInfo:
        _, process_id = win32process.GetWindowThreadProcessId(handle)
        show_cmd = win32gui.GetWindowPlacement(handle)[1]
        bounds = win32gui.GetWindowRect(handle)
        return WindowInfo(
            handle=handle,
            title=win32gui.GetWindowText(handle),
            process_id=process_id,
            is_minimized=show_cmd == win32con.SW_SHOWMINIMIZED,
            is_maximized=show_cmd == win32con.SW_SHOWMAXIMIZED,
            bounds=bounds,
        )

    def _handle_focus(self, request: ActionRequest, target: WindowInfo) -> ActionResult:
        """Windows' focus-stealing restriction means SetForegroundWindow
        can be silently ignored — the call itself not erroring proves
        nothing, so success is verified via GetForegroundWindow()
        afterward, never assumed optimistically."""
        self._call_with_timeout(lambda: win32gui.SetForegroundWindow(target.handle))
        focused = win32gui.GetForegroundWindow() == target.handle
        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED if focused else ActionStatus.FAILED,
            completed_at=datetime.now(UTC),
            output=self._window_info(target.handle) if focused else None,
            error_message=(
                None
                if focused
                else (
                    "SetForegroundWindow did not change the foreground window "
                    "(likely blocked by a Windows focus-stealing restriction)."
                )
            ),
        )

    def _handle_move(self, request: ActionRequest, target: WindowInfo) -> ActionResult:
        x = request.parameters.get("x")
        y = request.parameters.get("y")
        if x is None or y is None:
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Missing required parameter(s): x, y",
            )
        left, top, right, bottom = target.bounds
        self._call_with_timeout(
            lambda: win32gui.MoveWindow(
                target.handle, int(x), int(y), right - left, bottom - top, True
            )
        )
        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
            output=self._window_info(target.handle),
        )

    def _handle_resize(self, request: ActionRequest, target: WindowInfo) -> ActionResult:
        width = request.parameters.get("width")
        height = request.parameters.get("height")
        if width is None or height is None:
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Missing required parameter(s): width, height",
            )
        left, top, _, _ = target.bounds
        self._call_with_timeout(
            lambda: win32gui.MoveWindow(target.handle, left, top, int(width), int(height), True)
        )
        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
            output=self._window_info(target.handle),
        )

    def _handle_minimize(self, request: ActionRequest, target: WindowInfo) -> ActionResult:
        self._call_with_timeout(lambda: win32gui.ShowWindow(target.handle, win32con.SW_MINIMIZE))
        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
            output=self._window_info(target.handle),
        )

    def _handle_maximize(self, request: ActionRequest, target: WindowInfo) -> ActionResult:
        self._call_with_timeout(lambda: win32gui.ShowWindow(target.handle, win32con.SW_MAXIMIZE))
        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
            output=self._window_info(target.handle),
        )

    def _handle_close(self, request: ActionRequest, target: WindowInfo) -> ActionResult:
        """WM_CLOSE is a polite request, not a guaranteed termination —
        an app with unsaved changes may show its own prompt and never
        actually close. SUCCEEDED here means "the close message was
        sent," not "the window is confirmed gone" — an honest claim
        for Sprint 4.8's audit log to record, not an overstated one."""
        self._call_with_timeout(
            lambda: win32gui.PostMessage(target.handle, win32con.WM_CLOSE, 0, 0)
        )
        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
        )

    def _call_with_timeout(self, func: Callable[[], object]) -> object:
        """Runs func() on a daemon thread, bounded by
        window_operation_timeout_seconds — a real Windows API call can
        block indefinitely on an unresponsive target window's own
        message queue. A daemon thread (never joined at interpreter
        exit) is used deliberately: a genuinely hung native call cannot
        be forcibly cancelled from Python, so the best available
        behavior is to abandon it and report failure rather than block
        this class, or process shutdown, on it."""
        result: dict[str, object] = {}
        error: dict[str, Exception] = {}

        def _run() -> None:
            try:
                result["value"] = func()
            except Exception as exc:  # re-raised on the calling thread below
                error["value"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=self._config.window_operation_timeout_seconds)
        if thread.is_alive():
            raise TimeoutError(
                "Window operation did not complete within "
                f"{self._config.window_operation_timeout_seconds}s"
            )
        if "value" in error:
            raise error["value"]
        return result.get("value")
