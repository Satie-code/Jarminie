"""Unit tests for device_control.application_manager.

Real process launches use `sys.executable` running a short `time.sleep()`
script, not a GUI app like notepad.exe — verified empirically during
Sprint 4.2 implementation that on this environment/Windows version,
notepad.exe is redirected through a packaged-app host whose own PID
exits almost immediately, making it an unreliable, flaky test target.
A python child process needs no console/desktop station to stay alive,
so it is a genuinely "harmless and universally present" (Python is
already the interpreter running these tests) target that behaves
deterministically. See this file's own fixtures for cleanup discipline:
every real spawned process is force-killed in teardown even if a test's
own assertions fail first.
"""

import sys
import time
from datetime import UTC, datetime
from unittest.mock import patch

import psutil
import pytest

from config.schema import DeviceControlConfig
from device_control.action_engine import ActionContext, ActionRequest, ActionStatus, ActionType
from device_control.application_manager import ApplicationManager, TrackedApplication

_SLEEP_ARGS = ["-c", "import time; time.sleep(30)"]


def make_request(operation: str, **parameters) -> ActionRequest:
    return ActionRequest(
        action_type=ActionType.LAUNCH_APPLICATION,
        parameters={"operation": operation, **parameters},
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )


@pytest.fixture
def manager():
    mgr = ApplicationManager(DeviceControlConfig())
    yield mgr
    # Force-kill anything still tracked, even if a test's own assertions
    # failed mid-way -- real spawned processes must never leak past a
    # test run.
    for tracked in mgr.list_tracked():
        try:
            psutil.Process(tracked.process_id).kill()
        except psutil.Error:
            pass


def _spawn_sleeper(manager: ApplicationManager, requested_by: str = "test") -> TrackedApplication:
    tracked = manager.launch(sys.executable, requested_by=requested_by, args=_SLEEP_ARGS)
    time.sleep(0.3)  # let the child process actually start
    return tracked


# --- can_handle() ---------------------------------------------------------------


def test_can_handle_launch_and_close(manager):
    assert manager.can_handle(ActionType.LAUNCH_APPLICATION) is True
    assert manager.can_handle(ActionType.CLOSE_APPLICATION) is True


def test_cannot_handle_unrelated_action_type(manager):
    assert manager.can_handle(ActionType.FILE_DELETE) is False


# --- launch() / _handle_launch ---------------------------------------------------


def test_launch_succeeds_and_tracks_application(manager):
    tracked = _spawn_sleeper(manager)

    assert isinstance(tracked, TrackedApplication)
    assert tracked.process_id > 0
    assert psutil.pid_exists(tracked.process_id)
    assert tracked in manager.list_tracked()
    assert tracked.launched_via == "test"


def test_launch_bad_path_raises_and_execute_degrades_to_failed(manager):
    with pytest.raises(OSError):
        manager.launch("definitely_not_a_real_executable_xyz.exe", requested_by="test")

    result = manager.execute(
        make_request("launch", executable_path="definitely_not_a_real_executable_xyz.exe")
    )
    assert result.status is ActionStatus.FAILED
    assert result.error_message


def test_execute_launch_missing_executable_path_fails(manager):
    result = manager.execute(make_request("launch"))
    assert result.status is ActionStatus.FAILED
    assert "executable_path" in result.error_message


def test_execute_launch_succeeds_and_returns_tracked_application(manager):
    result = manager.execute(
        make_request("launch", executable_path=sys.executable, args=_SLEEP_ARGS)
    )
    time.sleep(0.3)

    assert result.status is ActionStatus.SUCCEEDED
    assert isinstance(result.output, TrackedApplication)
    assert result.output in manager.list_tracked()


def test_max_tracked_applications_bound_enforced():
    manager = ApplicationManager(DeviceControlConfig(max_tracked_applications=1))
    try:
        _spawn_sleeper(manager)
        result = manager.execute(
            make_request("launch", executable_path=sys.executable, args=_SLEEP_ARGS)
        )
        assert result.status is ActionStatus.FAILED
        assert "max_tracked_applications" in result.error_message
        assert len(manager.list_tracked()) == 1
    finally:
        for tracked in manager.list_tracked():
            try:
                psutil.Process(tracked.process_id).kill()
            except psutil.Error:
                pass


# --- close() / _handle_close ------------------------------------------------------


def test_close_tracked_process_succeeds(manager):
    tracked = _spawn_sleeper(manager)

    closed = manager.close(tracked.process_id)

    assert closed is True
    assert tracked not in manager.list_tracked()
    assert not psutil.pid_exists(tracked.process_id)


def test_close_untracked_process_returns_false(manager):
    assert manager.close(999_999_999) is False


def test_close_already_exited_process_is_still_a_successful_close(manager):
    """A process that exits on its own between launch() and close() is a
    real, legitimate case (found during Sprint 4.2 implementation, not
    hypothetical) -- must not be treated as a failure."""
    tracked = manager.launch(sys.executable, requested_by="test", args=["-c", "pass"])
    # Give the short-lived process time to exit on its own.
    for _ in range(20):
        if not psutil.pid_exists(tracked.process_id):
            break
        time.sleep(0.1)

    closed = manager.close(tracked.process_id)

    assert closed is True
    assert tracked not in manager.list_tracked()


def test_execute_close_untracked_process_is_denied(manager):
    result = manager.execute(make_request("close", process_id=999_999_999))
    assert result.status is ActionStatus.DENIED
    assert "untracked" in result.error_message


def test_execute_close_missing_process_id_fails(manager):
    result = manager.execute(make_request("close"))
    assert result.status is ActionStatus.FAILED
    assert "process_id" in result.error_message


def test_execute_close_succeeds(manager):
    tracked = _spawn_sleeper(manager)

    result = manager.execute(make_request("close", process_id=tracked.process_id))

    assert result.status is ActionStatus.SUCCEEDED
    assert not psutil.pid_exists(tracked.process_id)


# --- list_tracked() / _handle_list -------------------------------------------------


def test_list_tracked_reflects_launch_and_close(manager):
    assert manager.list_tracked() == []

    tracked = _spawn_sleeper(manager)
    assert manager.list_tracked() == [tracked]

    manager.close(tracked.process_id)
    assert manager.list_tracked() == []


def test_execute_list_returns_current_tracked_applications(manager):
    tracked = _spawn_sleeper(manager)

    result = manager.execute(make_request("list"))

    assert result.status is ActionStatus.SUCCEEDED
    assert result.output == [tracked]


# --- focus() / _handle_focus --------------------------------------------------------


def test_focus_untracked_process_returns_false(manager):
    assert manager.focus(999_999_999) is False


def test_execute_focus_untracked_process_is_denied(manager):
    result = manager.execute(make_request("focus", process_id=999_999_999))
    assert result.status is ActionStatus.DENIED


def test_focus_tracked_process_with_no_window_returns_false(manager):
    """A launched CLI/background process (this test's own sleeper) has
    no visible top-level window -- a real, expected case, not an error.
    Also verified empirically during Sprint 4.2 implementation: real
    spawned windows are not reliably discoverable via win32gui.EnumWindows
    in this specific automation environment (no attached interactive
    desktop/window station) -- the same "headless/CI environment"
    caveat this sprint's own Testing Checklist anticipated."""
    tracked = _spawn_sleeper(manager)

    assert manager.focus(tracked.process_id) is False


def test_focus_tracked_process_with_a_window_calls_set_foreground_window(manager):
    """Mocks window discovery to prove the "window found" path actually
    calls SetForegroundWindow -- the real OS-level integration a normal
    interactive desktop session would exercise for real; unreliable to
    assert on a real window in this automation environment (see module
    docstring), so verified at this boundary instead."""
    tracked = _spawn_sleeper(manager)
    fake_hwnd = 424242

    with (
        patch.object(manager, "_find_window_for_process", return_value=fake_hwnd) as find_mock,
        patch("device_control.application_manager.win32gui.SetForegroundWindow") as focus_mock,
    ):
        focused = manager.focus(tracked.process_id)

    assert focused is True
    find_mock.assert_called_once_with(tracked.process_id)
    focus_mock.assert_called_once_with(fake_hwnd)


def test_execute_focus_missing_process_id_fails(manager):
    result = manager.execute(make_request("focus"))
    assert result.status is ActionStatus.FAILED
    assert "process_id" in result.error_message


# --- unknown/missing operation ------------------------------------------------------


def test_execute_unknown_operation_fails(manager):
    result = manager.execute(make_request("teleport"))
    assert result.status is ActionStatus.FAILED
    assert "teleport" in result.error_message


def test_execute_missing_operation_fails(manager):
    request = ActionRequest(
        action_type=ActionType.LAUNCH_APPLICATION,
        parameters={},
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )
    result = manager.execute(request)
    assert result.status is ActionStatus.FAILED
