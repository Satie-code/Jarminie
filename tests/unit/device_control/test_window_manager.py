"""Unit tests for device_control.window_manager.

Real test windows are created in-process via win32gui.CreateWindow,
never by spawning an external process (e.g. notepad.exe) -- verified
empirically during Sprint 4.4 implementation that, on this environment,
an external process's window is unreliable to discover (the same
"packaged-app host" flakiness ApplicationManager's own tests hit and
moved away from in Sprint 4.2).

_TestWindow gives each spawned window its own dedicated thread running
a real Win32 message loop (win32gui.PumpMessages()) -- not a
convenience, a correctness requirement found during this sprint's own
implementation: a window only responds to synchronous calls
(SetForegroundWindow/MoveWindow/ShowWindow) issued from a *different*
thread than its owner if that owner's message queue is actually being
pumped; an unpumped synthetic window hung every such call issued via
WindowManager._call_with_timeout's own worker thread. Every real
target window WindowManager will ever operate on in production belongs
to some other already-running, already-message-pumping application, so
this only ever mattered for this test double -- but simulating it
faithfully is what makes these tests actually exercise
_call_with_timeout's real cross-thread path, not a same-thread special
case that would never occur in production.

SetForegroundWindow itself cannot be verified as *actually* succeeding
in this specific automation environment (confirmed empirically: it
raises a real pywintypes.error here, the same class of real-desktop-
session restriction ApplicationManager's own focus test already
documented) -- so the "focus succeeds" test mocks the underlying call
and asserts on the resolved target + call arguments, exactly like
test_application_manager.py's own
test_focus_tracked_process_with_a_window_calls_set_foreground_window.
"""

import threading
import time
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import pywintypes
import win32api
import win32con
import win32gui
import win32process

from config.schema import DeviceControlConfig
from device_control.action_engine import ActionContext, ActionRequest, ActionStatus, ActionType
from device_control.window_manager import WindowInfo, WindowManager

_WINDOW_CLASS_NAME = "JarminieTestWindow_WindowManager"


def _register_test_window_class() -> None:
    wc = win32gui.WNDCLASS()
    wc.lpszClassName = _WINDOW_CLASS_NAME
    wc.lpfnWndProc = {}
    try:
        win32gui.RegisterClass(wc)
    except pywintypes.error as exc:
        if exc.winerror != 1410:  # "Class already exists" -- fine to reuse
            raise


_register_test_window_class()


class _TestWindow:
    """A real win32 window, created and message-pumped on its own
    dedicated thread for the lifetime of one test. close() posts
    WM_CLOSE (processed on the owning thread's own loop, so
    DestroyWindow is correctly called by the thread that created the
    window) then WM_QUIT to stop the pump loop."""

    def __init__(self, title: str = "Jarminie Test Window") -> None:
        self.hwnd = 0
        self._thread_id = 0
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(title,), daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("Test window did not become ready in time")

    def _run(self, title: str) -> None:
        self._thread_id = win32api.GetCurrentThreadId()
        self.hwnd = win32gui.CreateWindow(
            _WINDOW_CLASS_NAME,
            title,
            win32con.WS_OVERLAPPEDWINDOW,
            0,
            0,
            300,
            200,
            0,
            0,
            0,
            None,
        )
        win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW)
        self._ready.set()
        win32gui.PumpMessages()

    def close(self) -> None:
        if win32gui.IsWindow(self.hwnd):
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
        win32api.PostThreadMessage(self._thread_id, win32con.WM_QUIT, 0, 0)
        self._thread.join(timeout=2.0)


def make_request(operation: str, **parameters) -> ActionRequest:
    return ActionRequest(
        action_type=ActionType.WINDOW_FOCUS,
        parameters={"operation": operation, **parameters},
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )


@pytest.fixture
def manager():
    return WindowManager(DeviceControlConfig())


@pytest.fixture
def test_window():
    window = _TestWindow()
    time.sleep(0.1)
    yield window.hwnd
    window.close()


# --- can_handle() ---------------------------------------------------------------


def test_can_handle_every_window_action_type(manager):
    for action_type in (
        ActionType.WINDOW_FOCUS,
        ActionType.WINDOW_MOVE,
        ActionType.WINDOW_RESIZE,
        ActionType.WINDOW_MINIMIZE,
        ActionType.WINDOW_CLOSE,
    ):
        assert manager.can_handle(action_type) is True


def test_cannot_handle_unrelated_action_type(manager):
    assert manager.can_handle(ActionType.FILE_DELETE) is False


# --- list_windows() / find_by_title() / find_for_process() ------------------------


def test_list_windows_includes_real_spawned_test_window(manager, test_window):
    infos = manager.list_windows()

    matching = [info for info in infos if info.handle == test_window]
    assert len(matching) == 1
    info = matching[0]
    assert info.title == "Jarminie Test Window"
    assert info.is_minimized is False
    assert info.is_maximized is False
    assert info.bounds == win32gui.GetWindowRect(test_window)


def test_find_by_title_case_insensitive_substring_match(manager, test_window):
    info = manager.find_by_title("jarminie test")
    assert info is not None
    assert info.handle == test_window


def test_find_by_title_no_match_returns_none(manager):
    assert manager.find_by_title("definitely_not_a_real_window_title_xyz") is None


def test_find_for_process_matches_owning_pid(manager, test_window):
    _, pid = win32process.GetWindowThreadProcessId(test_window)

    info = manager.find_for_process(pid)

    assert info is not None
    assert info.handle == test_window


def test_find_for_process_no_match_returns_none(manager):
    assert manager.find_for_process(999_999_999) is None


# --- focus ---------------------------------------------------------------------


def test_execute_focus_succeeds_and_calls_set_foreground_window(manager, test_window):
    """Real SetForegroundWindow success cannot be verified in this
    automation environment (see module docstring) -- mocks both the
    call and its own success-verification read, matching
    test_application_manager.py's established precedent for the same
    class of environment restriction."""
    with (
        patch("device_control.window_manager.win32gui.SetForegroundWindow") as set_fg_mock,
        patch(
            "device_control.window_manager.win32gui.GetForegroundWindow",
            return_value=test_window,
        ),
    ):
        result = manager.execute(make_request("focus", handle=test_window))

    assert result.status is ActionStatus.SUCCEEDED
    assert isinstance(result.output, WindowInfo)
    set_fg_mock.assert_called_once_with(test_window)


def test_execute_focus_reports_failed_when_focus_did_not_actually_change(manager, test_window):
    with (
        patch("device_control.window_manager.win32gui.SetForegroundWindow"),
        patch(
            "device_control.window_manager.win32gui.GetForegroundWindow",
            return_value=test_window + 1,
        ),
    ):
        result = manager.execute(make_request("focus", handle=test_window))

    assert result.status is ActionStatus.FAILED
    assert "focus" in result.error_message.lower()


# --- move / resize ---------------------------------------------------------------


def test_execute_move_succeeds_and_preserves_size(manager, test_window):
    original_rect = win32gui.GetWindowRect(test_window)
    width = original_rect[2] - original_rect[0]
    height = original_rect[3] - original_rect[1]

    result = manager.execute(make_request("move", handle=test_window, x=50, y=60))

    assert result.status is ActionStatus.SUCCEEDED
    new_rect = win32gui.GetWindowRect(test_window)
    assert new_rect[0] == 50
    assert new_rect[1] == 60
    assert new_rect[2] - new_rect[0] == width
    assert new_rect[3] - new_rect[1] == height


def test_execute_move_missing_params_fails(manager, test_window):
    result = manager.execute(make_request("move", handle=test_window))
    assert result.status is ActionStatus.FAILED
    assert "x" in result.error_message


def test_execute_resize_succeeds_and_preserves_position(manager, test_window):
    original_rect = win32gui.GetWindowRect(test_window)

    result = manager.execute(make_request("resize", handle=test_window, width=400, height=250))

    assert result.status is ActionStatus.SUCCEEDED
    new_rect = win32gui.GetWindowRect(test_window)
    assert new_rect[0] == original_rect[0]
    assert new_rect[1] == original_rect[1]
    assert new_rect[2] - new_rect[0] == 400
    assert new_rect[3] - new_rect[1] == 250


def test_execute_resize_missing_params_fails(manager, test_window):
    result = manager.execute(make_request("resize", handle=test_window))
    assert result.status is ActionStatus.FAILED
    assert "width" in result.error_message


# --- minimize / maximize ---------------------------------------------------------


def test_execute_minimize_succeeds_against_real_window(manager, test_window):
    result = manager.execute(make_request("minimize", handle=test_window))

    assert result.status is ActionStatus.SUCCEEDED
    assert win32gui.IsIconic(test_window)
    assert result.output.is_minimized is True


def test_execute_maximize_succeeds_against_real_window(manager, test_window):
    result = manager.execute(make_request("maximize", handle=test_window))

    assert result.status is ActionStatus.SUCCEEDED
    placement = win32gui.GetWindowPlacement(test_window)
    assert placement[1] == win32con.SW_SHOWMAXIMIZED
    assert result.output.is_maximized is True


# --- close -------------------------------------------------------------------------


def test_execute_close_sends_wm_close_and_window_is_destroyed(manager, test_window):
    result = manager.execute(make_request("close", handle=test_window))

    assert result.status is ActionStatus.SUCCEEDED
    for _ in range(40):
        if not win32gui.IsWindow(test_window):
            break
        time.sleep(0.05)
    assert not win32gui.IsWindow(test_window)


# --- stale/missing target ----------------------------------------------------------


def test_execute_against_stale_handle_degrades_to_failed(manager, test_window):
    """Closes the window directly (not via the fixture) so the handle
    is genuinely stale by the time execute() resolves it; the
    fixture's own teardown IsWindow() check on an already-gone handle
    is a safe no-op."""
    win32gui.PostMessage(test_window, win32con.WM_CLOSE, 0, 0)
    for _ in range(40):
        if not win32gui.IsWindow(test_window):
            break
        time.sleep(0.05)

    result = manager.execute(make_request("focus", handle=test_window))

    assert result.status is ActionStatus.FAILED
    assert result.error_message


def test_execute_missing_target_parameters_fails(manager):
    result = manager.execute(make_request("focus"))
    assert result.status is ActionStatus.FAILED


def test_execute_unknown_operation_fails(manager, test_window):
    result = manager.execute(make_request("teleport", handle=test_window))
    assert result.status is ActionStatus.FAILED
    assert "teleport" in result.error_message


# --- timeout bound -------------------------------------------------------------------


def test_window_operation_timeout_bound_is_respected(test_window):
    """Simulated via a mocked slow pywin32 call, since a real hang
    isn't reproducible on demand -- matching this sprint's own Testing
    Checklist. The mocked call keeps sleeping on its own daemon thread
    after the test returns; harmless since it never blocks process
    exit or later tests."""
    manager = WindowManager(DeviceControlConfig(window_operation_timeout_seconds=0.2))

    def _slow_set_foreground_window(_hwnd: int) -> None:
        time.sleep(2.0)

    started = time.monotonic()
    with patch(
        "device_control.window_manager.win32gui.SetForegroundWindow",
        side_effect=_slow_set_foreground_window,
    ):
        result = manager.execute(make_request("focus", handle=test_window))
    elapsed = time.monotonic() - started

    assert result.status is ActionStatus.FAILED
    assert "timed out" in result.error_message.lower() or "did not complete" in (
        result.error_message.lower()
    )
    assert elapsed < 1.0
