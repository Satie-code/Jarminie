"""Unit tests for device_control.command_executor.

Real subprocesses use sys.executable running a short inline script, not
a Windows-only shell builtin (e.g. "echo" isn't a real standalone
executable on Windows) -- matching test_application_manager.py's own
"genuinely harmless, universally present" testing precedent (Python is
already the interpreter running these tests).
"""

import sys
import time
from datetime import UTC, datetime
from pathlib import PureWindowsPath
from unittest.mock import patch

import psutil

from config.schema import DeviceControlConfig
from device_control.action_engine import ActionContext, ActionRequest, ActionStatus, ActionType
from device_control.command_executor import CommandExecutionEngine, CommandResult

_PY_BASENAME = PureWindowsPath(sys.executable).name


def make_request(command: list[str] | None) -> ActionRequest:
    parameters: dict[str, object] = {} if command is None else {"command": command}
    return ActionRequest(
        action_type=ActionType.SYSTEM_COMMAND,
        parameters=parameters,
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )


def _engine(**config_overrides) -> CommandExecutionEngine:
    config = DeviceControlConfig(approved_commands=[sys.executable], **config_overrides)
    return CommandExecutionEngine(config)


# --- can_handle() ---------------------------------------------------------------


def test_can_handle_system_command():
    engine = _engine()
    assert engine.can_handle(ActionType.SYSTEM_COMMAND) is True


def test_cannot_handle_unrelated_action_type():
    engine = _engine()
    assert engine.can_handle(ActionType.FILE_DELETE) is False


# --- default ships empty -----------------------------------------------------------


def test_default_approved_commands_is_empty():
    assert DeviceControlConfig().approved_commands == []


def test_empty_allowlist_denies_everything():
    engine = CommandExecutionEngine(DeviceControlConfig())
    result = engine.execute(make_request([sys.executable, "-c", "pass"]))
    assert result.status is ActionStatus.DENIED


# --- is_approved() ----------------------------------------------------------------


def test_is_approved_matches_configured_executable_case_insensitively():
    engine = _engine()
    assert engine.is_approved(sys.executable.upper()) is True
    assert engine.is_approved(_PY_BASENAME.upper()) is True


def test_is_approved_rejects_unconfigured_executable():
    engine = _engine()
    assert engine.is_approved("definitely_not_a_real_executable_xyz.exe") is False


def test_is_approved_matches_execute_own_internal_check():
    engine = _engine()

    assert engine.is_approved(sys.executable) is True
    approved_result = engine.execute(make_request([sys.executable, "-c", "pass"]))
    assert approved_result.status is not ActionStatus.DENIED

    unapproved_name = "definitely_not_a_real_executable_xyz.exe"
    assert engine.is_approved(unapproved_name) is False
    unapproved_result = engine.execute(make_request([unapproved_name]))
    assert unapproved_result.status is ActionStatus.DENIED


# --- approved command runs and returns accurate output ------------------------------


def test_approved_command_runs_and_returns_accurate_result():
    engine = _engine()

    result = engine.execute(
        make_request([sys.executable, "-c", "import sys; print('hello'); sys.exit(3)"])
    )

    assert result.status is ActionStatus.SUCCEEDED
    assert isinstance(result.output, CommandResult)
    assert result.output.exit_code == 3
    assert result.output.stdout.strip() == "hello"
    assert result.output.timed_out is False
    assert result.output.duration_seconds >= 0


def test_unapproved_command_is_denied_and_subprocess_never_spawned():
    engine = _engine()

    with patch("device_control.command_executor.subprocess.run") as run_mock:
        result = engine.execute(make_request(["definitely_not_a_real_executable_xyz.exe"]))

    assert result.status is ActionStatus.DENIED
    run_mock.assert_not_called()


def test_missing_command_parameter_fails():
    engine = _engine()
    result = engine.execute(make_request(None))
    assert result.status is ActionStatus.FAILED
    assert "command" in result.error_message


# --- timeout -----------------------------------------------------------------------


def test_command_exceeding_timeout_is_reported_timed_out():
    engine = _engine(command_timeout_seconds=0.3)

    result = engine.execute(
        make_request([sys.executable, "-c", "import time; time.sleep(5)"])
    )

    assert result.status is ActionStatus.FAILED
    assert isinstance(result.output, CommandResult)
    assert result.output.timed_out is True
    assert result.output.exit_code is None


def test_command_exceeding_timeout_leaves_no_orphaned_process(tmp_path):
    """Sprint 4.12 hardening (scenario c): CommandResult.timed_out=True
    was already correctly reported (Sprint 4.5's own designed behavior,
    via subprocess.run()'s documented timeout handling, which calls
    Popen.kill() internally before re-raising TimeoutExpired) — this is
    a real, adversarial regression test proving that guarantee actually
    holds, not just that the result is reported timed_out. The hanging
    script writes its own real OS pid to a file before sleeping, so this
    test can verify via psutil that the process is genuinely gone
    afterward, independent of anything CommandResult itself reports."""
    engine = _engine(command_timeout_seconds=0.3)
    pid_file = tmp_path / "pid.txt"
    script = (
        f"import os, time\n"
        f"with open(r'{pid_file}', 'w') as f:\n"
        f"    f.write(str(os.getpid()))\n"
        f"time.sleep(5)\n"
    )

    result = engine.execute(make_request([sys.executable, "-c", script]))

    assert result.output.timed_out is True
    spawned_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2.0
    while psutil.pid_exists(spawned_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not psutil.pid_exists(spawned_pid), "Timed-out subprocess was left running (orphaned)."


# --- nonexistent executable (approved by name, absent in reality) -------------------


def test_approved_but_nonexistent_executable_degrades_to_failed():
    config = DeviceControlConfig(approved_commands=["definitely_not_a_real_executable_xyz.exe"])
    engine = CommandExecutionEngine(config)

    result = engine.execute(make_request(["definitely_not_a_real_executable_xyz.exe"]))

    assert result.status is ActionStatus.FAILED
    assert result.error_message


# --- shell-injection resistance (real subprocess, not mocked) -----------------------


def test_shell_metacharacters_are_passed_as_one_literal_argument():
    engine = _engine()
    injection_shaped = "hello; rm -rf / && echo pwned | cat"

    result = engine.execute(
        make_request([sys.executable, "-c", "import sys; print(sys.argv[1])", injection_shaped])
    )

    assert result.status is ActionStatus.SUCCEEDED
    assert result.output.stdout.strip() == injection_shaped


def test_run_subprocess_never_passes_shell_true():
    engine = _engine()

    with patch("device_control.command_executor.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = ""
        run_mock.return_value.stderr = ""
        engine.execute(make_request([sys.executable, "-c", "pass"]))

    assert run_mock.call_args.kwargs["shell"] is False
