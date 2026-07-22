"""Unit tests for device_control.action_log.

Recovery tests are real, not mocked: a real FileOperationsManager
delete() (through execute(), for a real ActionResult shape) really
routes a real temp file through the real OS Recycle Bin, and
attempt_recovery() really restores it — verified during this sprint's
own implementation that the "obvious" Shell.Application InvokeVerb
approach silently no-ops in this environment, which is exactly why this
module reads the Recycle Bin's own on-disk $I/$R structure directly;
these tests are what actually proves that mechanism works, not just
that it compiles. Similarly, LAUNCH_APPLICATION recovery spawns a real
sys.executable sleeper process (matching test_application_manager.py's
own precedent) and confirms it is really no longer running afterward.
"""

import sys
import time
from datetime import UTC, datetime, timedelta

import psutil
import pytest

from config.schema import DeviceControlConfig
from database.sqlite_client import SqliteClient
from device_control.action_engine import ActionContext, ActionRequest, ActionStatus, ActionType
from device_control.action_log import (
    ActionAuditLog,
    ActionAuditRecord,
    ActionRecoveryManager,
    RecoveryOutcome,
)
from device_control.application_manager import ApplicationManager
from device_control.file_operations import FileOperationsManager
from security.permission_gate import PermissionDecision
from security.policy_engine import RiskLevel

_SLEEP_ARGS = ["-c", "import time; time.sleep(30)"]


def make_request(action_type: ActionType, **parameters) -> ActionRequest:
    return ActionRequest(
        action_type=action_type,
        parameters=parameters,
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )


@pytest.fixture
def device_control_config(tmp_path) -> DeviceControlConfig:
    return DeviceControlConfig(allowed_file_roots=[str(tmp_path)])


@pytest.fixture
def audit_log(tmp_path, device_control_config) -> ActionAuditLog:
    client = SqliteClient(str(tmp_path / "audit.db"))
    log = ActionAuditLog(client, device_control_config)
    log.start()
    yield log
    log.stop()


# --- record() ----------------------------------------------------------------------


def test_record_persists_a_succeeded_result(audit_log):
    result_request = make_request(ActionType.WINDOW_FOCUS, handle=123)
    result = type(
        "Result", (), {"request": result_request, "status": ActionStatus.SUCCEEDED,
                        "output": None, "error_message": None}
    )()

    record = audit_log.record(result, PermissionDecision.ALLOW, RiskLevel.LOW)

    assert record.status == "succeeded"
    assert record.permission_decision == "allow"
    assert record.risk_level == "low"
    assert record.is_reversible is False

    fetched = audit_log.query(action_type=ActionType.WINDOW_FOCUS)
    assert len(fetched) == 1
    assert fetched[0].status == "succeeded"


def test_record_persists_a_denied_result(audit_log):
    request = make_request(ActionType.SYSTEM_COMMAND, command=["del", "/f"])
    result = type(
        "Result", (), {"request": request, "status": ActionStatus.DENIED,
                        "output": None, "error_message": "Denied by permission policy."}
    )()

    audit_log.record(result, PermissionDecision.DENY, None)

    fetched = audit_log.query(action_type=ActionType.SYSTEM_COMMAND)
    assert fetched[0].status == "denied"
    assert fetched[0].risk_level is None


def test_record_persists_a_failed_result(audit_log):
    request = make_request(ActionType.FILE_DELETE, path="C:/nope.txt")
    result = type(
        "Result", (), {"request": request, "status": ActionStatus.FAILED,
                        "output": None, "error_message": "Path does not exist"}
    )()

    audit_log.record(result, PermissionDecision.ALLOW, RiskLevel.HIGH)

    fetched = audit_log.query(action_type=ActionType.FILE_DELETE)
    assert fetched[0].status == "failed"
    assert fetched[0].error_message == "Path does not exist"
    assert fetched[0].is_reversible is True


def test_record_id_is_none_before_persistence_and_set_after_query(audit_log):
    request = make_request(ActionType.WINDOW_FOCUS)
    result = type(
        "Result", (), {"request": request, "status": ActionStatus.SUCCEEDED,
                        "output": None, "error_message": None}
    )()

    record = audit_log.record(result, PermissionDecision.ALLOW, RiskLevel.LOW)
    assert record.record_id is None

    fetched = audit_log.query(action_type=ActionType.WINDOW_FOCUS)
    assert fetched[0].record_id is not None


# --- redaction -----------------------------------------------------------------------


def test_password_parameter_is_redacted():
    request = make_request(
        ActionType.SYSTEM_COMMAND, command=["curl"], password="hunter2", token="abc123"
    )
    result = type(
        "Result", (), {"request": request, "status": ActionStatus.SUCCEEDED,
                        "output": None, "error_message": None}
    )()
    client = SqliteClient(":memory:")
    log = ActionAuditLog(client, DeviceControlConfig())
    log.start()
    try:
        record = log.record(result, PermissionDecision.ALLOW, RiskLevel.HIGH)
        assert "hunter2" not in record.parameters_summary
        assert "abc123" not in record.parameters_summary
        assert "password=[REDACTED]" in record.parameters_summary
        assert "token=[REDACTED]" in record.parameters_summary
    finally:
        log.stop()


def test_long_parameter_value_is_truncated():
    request = make_request(ActionType.FILE_CREATE, path="a.txt", content="x" * 500)
    result = type(
        "Result", (), {"request": request, "status": ActionStatus.SUCCEEDED,
                        "output": None, "error_message": None}
    )()
    client = SqliteClient(":memory:")
    log = ActionAuditLog(client, DeviceControlConfig())
    log.start()
    try:
        record = log.record(result, PermissionDecision.ALLOW, RiskLevel.LOW)
        assert "...(truncated)" in record.parameters_summary
        assert "x" * 500 not in record.parameters_summary
    finally:
        log.stop()


def test_launch_application_success_includes_process_id_in_summary():
    request = make_request(ActionType.LAUNCH_APPLICATION, executable_path="notepad.exe")
    output = type("TrackedApplication", (), {"process_id": 4242})()
    result = type(
        "Result", (), {"request": request, "status": ActionStatus.SUCCEEDED,
                        "output": output, "error_message": None}
    )()
    client = SqliteClient(":memory:")
    log = ActionAuditLog(client, DeviceControlConfig())
    log.start()
    try:
        record = log.record(result, PermissionDecision.ALLOW, RiskLevel.LOW)
        assert "process_id=4242" in record.parameters_summary
    finally:
        log.stop()


# --- query() filtering -----------------------------------------------------------------


def test_query_filters_by_action_type(audit_log):
    for action_type in (ActionType.WINDOW_FOCUS, ActionType.FILE_CREATE):
        request = make_request(action_type)
        result = type(
            "Result", (), {"request": request, "status": ActionStatus.SUCCEEDED,
                            "output": None, "error_message": None}
        )()
        audit_log.record(result, PermissionDecision.ALLOW, RiskLevel.LOW)

    fetched = audit_log.query(action_type=ActionType.WINDOW_FOCUS)
    assert len(fetched) == 1
    assert fetched[0].action_type == "window_focus"


def test_query_filters_by_since(audit_log):
    request = make_request(ActionType.WINDOW_FOCUS)
    result = type(
        "Result", (), {"request": request, "status": ActionStatus.SUCCEEDED,
                        "output": None, "error_message": None}
    )()
    audit_log.record(result, PermissionDecision.ALLOW, RiskLevel.LOW)

    future_cutoff = datetime.now(UTC) + timedelta(days=1)
    assert audit_log.query(since=future_cutoff) == []
    assert len(audit_log.query(since=datetime.now(UTC) - timedelta(minutes=1))) == 1


def test_query_respects_limit(audit_log):
    for _ in range(5):
        request = make_request(ActionType.WINDOW_FOCUS)
        result = type(
            "Result", (), {"request": request, "status": ActionStatus.SUCCEEDED,
                            "output": None, "error_message": None}
        )()
        audit_log.record(result, PermissionDecision.ALLOW, RiskLevel.LOW)

    assert len(audit_log.query(limit=2)) == 2


# --- purge_older_than() / real caller from start() --------------------------------------


def test_purge_older_than_deletes_only_older_records(tmp_path, device_control_config):
    client = SqliteClient(str(tmp_path / "purge.db"))
    log = ActionAuditLog(client, device_control_config)
    log.start()
    try:
        old_request = make_request(ActionType.WINDOW_FOCUS)
        old_result = type(
            "Result", (), {"request": old_request, "status": ActionStatus.SUCCEEDED,
                            "output": None, "error_message": None}
        )()
        log.record(old_result, PermissionDecision.ALLOW, RiskLevel.LOW)
        # Directly backdate the just-inserted row's recorded_at.
        client.execute(
            "UPDATE action_audit_log SET recorded_at = ?",
            ((datetime.now(UTC) - timedelta(days=100)).isoformat(),),
        )

        new_request = make_request(ActionType.FILE_CREATE)
        new_result = type(
            "Result", (), {"request": new_request, "status": ActionStatus.SUCCEEDED,
                            "output": None, "error_message": None}
        )()
        log.record(new_result, PermissionDecision.ALLOW, RiskLevel.LOW)

        removed = log.purge_older_than(90)

        assert removed == 1
        remaining = log.query(limit=50)
        assert len(remaining) == 1
        assert remaining[0].action_type == "file_create"
    finally:
        log.stop()


def test_start_calls_purge_older_than_for_real(tmp_path, device_control_config, monkeypatch):
    client = SqliteClient(str(tmp_path / "startpurge.db"))
    log = ActionAuditLog(client, device_control_config)
    calls = []
    monkeypatch.setattr(log, "purge_older_than", lambda days: calls.append(days) or 0)

    log.start()

    assert calls == [device_control_config.audit_log_retention_days]
    log.stop()


# --- ActionRecoveryManager: real recycle-bin restore --------------------------------------


@pytest.fixture
def recovery_manager(audit_log, device_control_config):
    file_ops = FileOperationsManager(device_control_config)
    app_manager = ApplicationManager(device_control_config)
    manager = ActionRecoveryManager(audit_log, file_ops, app_manager)
    yield manager, file_ops, app_manager
    for tracked in app_manager.list_tracked():
        try:
            psutil.Process(tracked.process_id).kill()
        except psutil.Error:
            pass


def test_real_file_delete_is_genuinely_recoverable(tmp_path, audit_log, recovery_manager):
    manager, file_ops, _ = recovery_manager
    target = tmp_path / "recoverable.txt"
    target.write_text("real content to recover", encoding="utf-8")

    delete_request = make_request(ActionType.FILE_DELETE, path=str(target))
    delete_result = file_ops.execute(delete_request)
    assert delete_result.status is ActionStatus.SUCCEEDED
    assert not target.exists()

    record = audit_log.record(delete_result, PermissionDecision.ALLOW, RiskLevel.HIGH)

    outcome = manager.attempt_recovery(record)

    assert outcome is RecoveryOutcome.RECOVERED
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "real content to recover"


def test_real_folder_delete_is_genuinely_recoverable(tmp_path, audit_log, recovery_manager):
    manager, file_ops, _ = recovery_manager
    target = tmp_path / "recoverable_dir"
    target.mkdir()
    (target / "inner.txt").write_text("inner content", encoding="utf-8")

    delete_request = make_request(ActionType.FOLDER_DELETE, path=str(target))
    delete_result = file_ops.execute(delete_request)
    assert delete_result.status is ActionStatus.SUCCEEDED
    assert not target.exists()

    record = audit_log.record(delete_result, PermissionDecision.ALLOW, RiskLevel.HIGH)

    outcome = manager.attempt_recovery(record)

    assert outcome is RecoveryOutcome.RECOVERED
    assert target.is_dir()
    assert (target / "inner.txt").read_text(encoding="utf-8") == "inner content"


def test_recovery_for_a_record_with_no_matching_recycle_bin_entry_fails_honestly(
    audit_log, recovery_manager
):
    manager, _, _ = recovery_manager
    fake_record = ActionAuditRecord(
        action_type="file_delete",
        parameters_summary="path=C:/definitely/not/a/real/deleted/path_xyz.txt",
        requested_by="test",
        risk_level="high",
        permission_decision="allow",
        status="succeeded",
        error_message=None,
        is_reversible=True,
        recorded_at=datetime.now(UTC),
    )

    outcome = manager.attempt_recovery(fake_record)

    assert outcome is RecoveryOutcome.RECOVERY_FAILED


# --- ActionRecoveryManager: non-reversible action types --------------------------------


def test_system_command_is_not_reversible_immediately(recovery_manager):
    manager, _, _ = recovery_manager
    record = ActionAuditRecord(
        action_type="system_command",
        parameters_summary="command=ping localhost",
        requested_by="test",
        risk_level="high",
        permission_decision="allow",
        status="succeeded",
        error_message=None,
        is_reversible=False,
        recorded_at=datetime.now(UTC),
    )

    outcome = manager.attempt_recovery(record)

    assert outcome is RecoveryOutcome.NOT_REVERSIBLE


def test_window_focus_is_not_reversible_immediately(recovery_manager):
    manager, _, _ = recovery_manager
    record = ActionAuditRecord(
        action_type="window_focus",
        parameters_summary="handle=123",
        requested_by="test",
        risk_level="low",
        permission_decision="allow",
        status="succeeded",
        error_message=None,
        is_reversible=False,
        recorded_at=datetime.now(UTC),
    )

    assert manager.attempt_recovery(record) is RecoveryOutcome.NOT_REVERSIBLE


# --- ActionRecoveryManager: real launch_application recovery ----------------------------


def test_real_launched_application_is_genuinely_recoverable(recovery_manager):
    manager, _, app_manager = recovery_manager

    tracked = app_manager.launch(sys.executable, requested_by="test", args=_SLEEP_ARGS)
    time.sleep(0.3)
    assert psutil.pid_exists(tracked.process_id)

    record = ActionAuditRecord(
        action_type="launch_application",
        parameters_summary=f"executable_path={sys.executable}, process_id={tracked.process_id}",
        requested_by="test",
        risk_level="low",
        permission_decision="allow",
        status="succeeded",
        error_message=None,
        is_reversible=True,
        recorded_at=datetime.now(UTC),
    )

    outcome = manager.attempt_recovery(record)

    assert outcome is RecoveryOutcome.RECOVERED
    assert not psutil.pid_exists(tracked.process_id)


def test_launch_application_recovery_with_untracked_process_id_fails_honestly(recovery_manager):
    manager, _, _ = recovery_manager
    record = ActionAuditRecord(
        action_type="launch_application",
        parameters_summary="executable_path=x, process_id=999999999",
        requested_by="test",
        risk_level="low",
        permission_decision="allow",
        status="succeeded",
        error_message=None,
        is_reversible=True,
        recorded_at=datetime.now(UTC),
    )

    outcome = manager.attempt_recovery(record)

    assert outcome is RecoveryOutcome.RECOVERY_FAILED


def test_launch_application_recovery_with_no_process_id_in_summary_fails_honestly(
    recovery_manager,
):
    manager, _, _ = recovery_manager
    record = ActionAuditRecord(
        action_type="launch_application",
        parameters_summary="executable_path=x",
        requested_by="test",
        risk_level="low",
        permission_decision="allow",
        status="succeeded",
        error_message=None,
        is_reversible=True,
        recorded_at=datetime.now(UTC),
    )

    assert manager.attempt_recovery(record) is RecoveryOutcome.RECOVERY_FAILED
