"""Command Execution Engine — Level 4's fourth real ActionExecutor:
controlled execution of approved system commands. See
docs/sprint_book/sprint_4_5.md.

The highest-risk executor in Level 4 Part A — an arbitrary shell command
is a strictly more powerful (and more dangerous) primitive than any
single file or window operation. Two hard, structural invariants:

- A default-deny allowlist checked against command[0] (the executable
  name, basename-only, case-insensitive) — never the full command line.
  DeviceControlConfig.approved_commands ships empty, so this executor
  is fully inert until deliberately configured — mirroring
  AuthorityEvaluator.approved_emergency_procedures's own "structurally
  unreachable by design" treatment (Sprint 3.11).
- No shell string interpolation, ever — subprocess.run() is always
  called with shell=False and an argv-shaped list (parameters["command"]
  must already be pre-split; this class never parses or splits a raw
  string itself). There is no config override for this.

Captured stdout/stderr may contain sensitive data if a future approved
command happens to echo secrets — CommandResult carries it in full
(a caller/workflow needs the real output to act on), but any
redaction/truncation policy before persisting it to disk is Sprint
4.8's (Action Logging & Recovery) responsibility, not this module's.

Sprint 4.12 hardening (scenario c): no code change was needed here —
_run_subprocess()'s use of subprocess.run(timeout=...) already
guarantees the underlying process is killed (Popen.kill(), per
CPython's own documented TimeoutExpired handling) before
TimeoutExpired is re-raised, never left as an orphaned process. Sprint
4.5's own test suite verified CommandResult.timed_out=True was
reported correctly but never verified the real OS process was actually
gone afterward — closed by a dedicated adversarial regression test in
tests/unit/device_control/test_command_executor.py instead, matching
Sprint 3.13's own "verify under adversarial conditions rather than
assume the earlier design holds" precedent.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PureWindowsPath

from config.schema import DeviceControlConfig
from core.logging_setup import get_logger
from device_control.action_engine import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)

logger = get_logger(__name__)

_HANDLED_TYPES = frozenset({ActionType.SYSTEM_COMMAND})


@dataclass
class CommandResult:
    """exit_code is None only when timed_out is True — the process never
    reached a real exit code."""

    command: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float


def _basename(executable_name: str) -> str:
    return PureWindowsPath(executable_name).name.lower()


class CommandExecutionEngine:
    """Constructor DI: (device_control_config). Handles SYSTEM_COMMAND.

    execute() only ever catches OSError (covers FileNotFoundError — an
    executable that passed the allowlist check by name but isn't
    actually present on PATH) — never a bare except, per
    docs/CODING_STANDARDS.md.
    """

    def __init__(self, device_control_config: DeviceControlConfig) -> None:
        self._config = device_control_config

    def can_handle(self, action_type: ActionType) -> bool:
        return action_type in _HANDLED_TYPES

    def is_approved(self, executable_name: str) -> bool:
        """Public so Sprint 4.7's Permission & Confirmation System can
        pre-check approval status without triggering an actual run."""
        approved_basenames = {_basename(name) for name in self._config.approved_commands}
        return _basename(executable_name) in approved_basenames

    def execute(self, request: ActionRequest) -> ActionResult:
        command = request.parameters.get("command")
        if not command:
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message="Missing required parameter: command",
            )
        if not self.is_approved(command[0]):
            logger.info("Command denied — not on approved_commands: %s", command[0])
            return ActionResult(
                request=request,
                status=ActionStatus.DENIED,
                completed_at=datetime.now(UTC),
                error_message=f"Executable is not on the approved command list: {command[0]}",
            )
        try:
            result = self._run_subprocess(command)
        except OSError as exc:
            logger.exception("Command execution failed: %s", command)
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message=str(exc),
            )
        return ActionResult(
            request=request,
            status=ActionStatus.FAILED if result.timed_out else ActionStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
            output=result,
            error_message=(
                f"Command timed out after {self._config.command_timeout_seconds}s."
                if result.timed_out
                else None
            ),
        )

    def _run_subprocess(self, command: list[str]) -> CommandResult:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                shell=False,
                capture_output=True,
                timeout=self._config.command_timeout_seconds,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=command,
                exit_code=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                timed_out=True,
                duration_seconds=time.monotonic() - started,
            )
        return CommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
            duration_seconds=time.monotonic() - started,
        )
