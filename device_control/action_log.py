"""Action Logging & Recovery — a persistent, queryable audit trail for
every ActionRegistry.dispatch() call, plus a best-effort recovery path
for the action types that are actually reversible. See
docs/sprint_book/sprint_4_8.md.

ActionAuditRecord.parameters_summary is a redacted, truncated,
"key=value, key2=value2"-joined rendering of ActionRequest.parameters
(plus, for a SUCCEEDED LAUNCH_APPLICATION, the resulting process_id
from ActionResult.output) — never the raw dict verbatim. Deliberately
kept parseable (not free-form prose) rather than only human-readable:
ActionAuditRecord's own declared fields (this sprint's own Expected
Classes) have no separate, unredacted copy of the original request, so
a parseable summary is the only way ActionRecoveryManager.attempt_recovery()
can extract what it needs (a file path, a process id) from an
already-persisted record, potentially long after the original
ActionRequest object is gone. A value under a key named password/token/
secret/credential is replaced with "[REDACTED]"; this is a simple
keyword heuristic, not a guarantee — a sensitive value under an
unexpected key name would not be caught, the same honest limitation
already acknowledged for ShortTermMemory's salience triggers and
PersonaManager's trigger phrases.

Recycle-bin restore does NOT use Shell.Application's own "Restore"
context-menu verb (Namespace(10).Items()...InvokeVerb("Restore")) —
verified empirically during this sprint's implementation that verb
invocation silently no-ops in this environment (the item stays in the
Recycle Bin, completely untouched, no exception raised at all) — the
same class of automation-environment restriction already found for
WindowManager's SetForegroundWindow (Sprint 4.4). Instead, this reads
the Recycle Bin's own per-item "$I" metadata file directly (a real,
verified-working, if undocumented and Windows-version-dependent binary
format: 8-byte version marker, 8-byte original file size, 8-byte
FILETIME deletion timestamp, 4-byte path length, then a UTF-16LE
original path — the version=2 layout used since Windows 10) to find
the matching item and its paired "$R" data file, then moves that data
file back to its original location directly — no shell/Explorer
mediation at all. Falls back to RECOVERY_FAILED, never an optimistic
RECOVERED, if the Recycle Bin structure isn't what's expected (a
different Windows version, a non-NTFS volume, or the item already
purged/emptied) — matching this sprint's own explicit Potential Risks
language that restore must never claim success optimistically.

file_operations_manager is accepted by ActionRecoveryManager's
constructor per this sprint's own Expected Classes signature, but is
not yet consulted by attempt_recovery()'s own logic — the verified
Recycle Bin restore mechanism above works directly against the Recycle
Bin's own on-disk structure and needs no FileOperationsManager
involvement (its own allowed_file_roots scope check would, in any
case, reject the Recycle Bin's own path as a source). Kept as a stored
dependency for future use rather than removed, the same "field present,
not yet used for its ultimate purpose" discipline already established
for PermissionGate.authority_evaluator (Sprint 4.7).
"""

from __future__ import annotations

import os
import shutil
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import win32api
import win32security

from config.schema import DeviceControlConfig
from core.logging_setup import get_logger
from database.sqlite_client import SqliteClient

if TYPE_CHECKING:
    from device_control.action_engine import ActionResult, ActionType
    from device_control.application_manager import ApplicationManager
    from device_control.file_operations import FileOperationsManager
    from security.permission_gate import PermissionDecision
    from security.policy_engine import RiskLevel

logger = get_logger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS action_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    parameters_summary TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    risk_level TEXT,
    permission_decision TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    is_reversible INTEGER NOT NULL,
    recorded_at TEXT NOT NULL
)
"""

_REDACTED_KEYS = frozenset({"password", "token", "secret", "credential"})
_MAX_SUMMARY_VALUE_LENGTH = 200
_REVERSIBLE_ACTION_TYPES = frozenset({"file_delete", "folder_delete", "launch_application"})


def _redact_and_truncate(key: str, value: object) -> str:
    if key.lower() in _REDACTED_KEYS:
        return "[REDACTED]"
    rendered = " ".join(str(part) for part in value) if isinstance(value, list) else str(value)
    if len(rendered) > _MAX_SUMMARY_VALUE_LENGTH:
        rendered = rendered[:_MAX_SUMMARY_VALUE_LENGTH] + "...(truncated)"
    return rendered


def _build_parameters_summary(result: ActionResult) -> str:
    parts = [
        f"{key}={_redact_and_truncate(key, value)}"
        for key, value in result.request.parameters.items()
    ]
    if result.request.action_type.value == "launch_application" and result.output is not None:
        process_id = getattr(result.output, "process_id", None)
        if process_id is not None:
            parts.append(f"process_id={process_id}")
    return ", ".join(parts)


def _extract_summary_value(parameters_summary: str, key: str) -> str | None:
    """Best-effort extraction from a "key=value, key2=value2" summary —
    a value itself containing ", " (e.g. a path with a literal comma)
    would not round-trip correctly; a known, accepted limitation given
    parameters_summary is a display/audit rendering, not a lossless
    serialization format."""
    prefix = f"{key}="
    for part in parameters_summary.split(", "):
        if part.startswith(prefix):
            return part[len(prefix) :]
    return None


@dataclass
class ActionAuditRecord:
    action_type: str
    parameters_summary: str
    requested_by: str
    risk_level: str | None
    permission_decision: str
    status: str
    error_message: str | None
    is_reversible: bool
    recorded_at: datetime
    record_id: int | None = None


class ActionAuditLog:
    """Constructor DI: (sqlite_client, device_control_config). Owns its
    own action_audit_log table DDL against the shared SqliteClient,
    following ConversationSessionStore's (2.7) and MemoryStore's (3.1)
    own "caller owns its own DDL" precedent — no second database-access
    layer invented.

    purge_older_than() is called for real, once, from start() itself —
    the same one-time-at-startup compromise Sprint 3.12 already
    established for MemoryLifecycleManager, honestly scoped the same
    way, not overstated as a real recurring schedule. A true periodic
    cadence remains Level 4 Part B's Scheduler's job, same as
    backlog/technical_debt.md items 11/15/17.
    """

    def __init__(
        self, sqlite_client: SqliteClient, device_control_config: DeviceControlConfig
    ) -> None:
        self._sqlite_client = sqlite_client
        self._config = device_control_config
        self._started = False

    def start(self) -> None:
        self._sqlite_client.connect()
        self._sqlite_client.execute(_CREATE_TABLE_SQL)
        self._started = True
        purged = self.purge_older_than(self._config.audit_log_retention_days)
        logger.info(
            "Action audit log started; purged %d record(s) older than %d days.",
            purged,
            self._config.audit_log_retention_days,
        )

    def stop(self) -> None:
        self._sqlite_client.close()
        self._started = False
        logger.info("Action audit log stopped.")

    def health_check(self) -> bool:
        if not self._started:
            return False
        try:
            self._sqlite_client.query("SELECT 1")
            return True
        except Exception:
            logger.exception("Action audit log health check query failed.")
            return False

    def record(
        self,
        result: ActionResult,
        permission_decision: PermissionDecision,
        risk_level: RiskLevel | None,
    ) -> ActionAuditRecord:
        """Never raises out to the caller — ActionRegistry.dispatch()
        must not fail an otherwise-successful action just because the
        audit write itself failed (same discipline as
        ConversationSessionStore.record_turn())."""
        action_type_value = result.request.action_type.value
        record = ActionAuditRecord(
            action_type=action_type_value,
            parameters_summary=_build_parameters_summary(result),
            requested_by=result.request.context.requested_by,
            risk_level=risk_level.value if risk_level is not None else None,
            permission_decision=permission_decision.value,
            status=result.status.value,
            error_message=result.error_message,
            is_reversible=action_type_value in _REVERSIBLE_ACTION_TYPES,
            recorded_at=datetime.now(UTC),
        )
        try:
            self._sqlite_client.execute(
                "INSERT INTO action_audit_log "
                "(action_type, parameters_summary, requested_by, risk_level, "
                "permission_decision, status, error_message, is_reversible, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.action_type,
                    record.parameters_summary,
                    record.requested_by,
                    record.risk_level,
                    record.permission_decision,
                    record.status,
                    record.error_message,
                    int(record.is_reversible),
                    record.recorded_at.isoformat(),
                ),
            )
        except Exception:
            logger.exception("Failed to persist action audit record for %s.", action_type_value)
        return record

    def query(
        self,
        action_type: ActionType | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[ActionAuditRecord]:
        sql = (
            "SELECT id, action_type, parameters_summary, requested_by, risk_level, "
            "permission_decision, status, error_message, is_reversible, recorded_at "
            "FROM action_audit_log WHERE 1=1"
        )
        params: list[object] = []
        if action_type is not None:
            sql += " AND action_type = ?"
            params.append(action_type.value)
        if since is not None:
            sql += " AND recorded_at >= ?"
            params.append(since.isoformat())
        sql += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)
        try:
            rows = self._sqlite_client.query(sql, tuple(params))
        except Exception:
            logger.exception("Failed to query action audit log.")
            return []
        return [
            ActionAuditRecord(
                record_id=row[0],
                action_type=row[1],
                parameters_summary=row[2],
                requested_by=row[3],
                risk_level=row[4],
                permission_decision=row[5],
                status=row[6],
                error_message=row[7],
                is_reversible=bool(row[8]),
                recorded_at=datetime.fromisoformat(row[9]),
            )
            for row in rows
        ]

    def purge_older_than(self, days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        try:
            removed = self._sqlite_client.query(
                "SELECT COUNT(*) FROM action_audit_log WHERE recorded_at < ?", (cutoff,)
            )[0][0]
            self._sqlite_client.execute(
                "DELETE FROM action_audit_log WHERE recorded_at < ?", (cutoff,)
            )
        except Exception:
            logger.exception("Failed to purge action audit records older than %d days.", days)
            return 0
        return removed


class RecoveryOutcome(Enum):
    RECOVERED = "recovered"
    NOT_REVERSIBLE = "not_reversible"
    RECOVERY_FAILED = "recovery_failed"


@dataclass
class _RecycleBinEntry:
    info_file: Path
    data_file: Path
    deleted_at: datetime


def _get_current_user_sid() -> str:
    username = win32api.GetUserName()
    sid, _domain, _sid_type = win32security.LookupAccountName(None, username)
    return win32security.ConvertSidToStringSid(sid)


def _parse_recycle_bin_info_file(info_path: Path) -> tuple[datetime, str] | None:
    """Returns (deleted_at, original_path) for a version-2 (Windows 10+)
    "$I" metadata file, or None for anything that doesn't match —
    never raises; an unparseable/unexpected format degrades to "no
    match" rather than aborting the whole recovery attempt."""
    try:
        data = info_path.read_bytes()
        version = struct.unpack("<q", data[0:8])[0]
        if version != 2:
            return None
        filetime = struct.unpack("<q", data[16:24])[0]
        deleted_at = datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=filetime / 10)
        path_len = struct.unpack("<i", data[24:28])[0]
        path_bytes = data[28 : 28 + path_len * 2]
        original_path = path_bytes.decode("utf-16le").rstrip("\x00")
        return deleted_at, original_path
    except Exception:
        return None


def _find_recycle_bin_entry(original_path: Path, recorded_at: datetime) -> _RecycleBinEntry | None:
    """Searches the current user's own per-volume Recycle Bin folder
    (derived from original_path's own drive, not hardcoded to C:\\, since
    Recycle Bin data is stored per-volume) for the "$I" metadata file
    whose parsed original path matches. If more than one historical
    deletion of the same path exists, prefers whichever deletion
    timestamp is closest to recorded_at, disambiguating repeated
    delete/recreate/delete cycles of the same filename."""
    try:
        sid = _get_current_user_sid()
    except Exception:
        logger.exception("Failed to resolve the current user's SID for Recycle Bin lookup.")
        return None
    recycle_dir = Path(f"{original_path.drive}\\$Recycle.Bin") / sid
    if not recycle_dir.is_dir():
        return None

    normalized_target = os.path.normcase(os.path.normpath(str(original_path)))
    candidates: list[_RecycleBinEntry] = []
    for info_file in recycle_dir.glob("$I*"):
        parsed = _parse_recycle_bin_info_file(info_file)
        if parsed is None:
            continue
        deleted_at, parsed_path = parsed
        if os.path.normcase(os.path.normpath(parsed_path)) != normalized_target:
            continue
        data_file = info_file.with_name("$R" + info_file.name[2:])
        if not data_file.exists():
            continue
        candidates.append(
            _RecycleBinEntry(info_file=info_file, data_file=data_file, deleted_at=deleted_at)
        )
    if not candidates:
        return None
    candidates.sort(key=lambda c: abs((c.deleted_at - recorded_at).total_seconds()))
    return candidates[0]


class ActionRecoveryManager:
    """Constructor DI: (audit_log, file_operations_manager,
    application_manager). Not a ManagedModule — no lifecycle of its own.

    attempt_recovery()'s three-outcome model (RECOVERED/NOT_REVERSIBLE/
    RECOVERY_FAILED) deliberately has no "partially recovered" state —
    a recovery attempt's outcome is stated plainly, matching the
    Explainability Rule, not hedged.
    """

    def __init__(
        self,
        audit_log: ActionAuditLog,
        file_operations_manager: FileOperationsManager,
        application_manager: ApplicationManager,
    ) -> None:
        self._audit_log = audit_log
        self._file_operations_manager = file_operations_manager
        self._application_manager = application_manager

    def attempt_recovery(self, record: ActionAuditRecord) -> RecoveryOutcome:
        if not record.is_reversible:
            return RecoveryOutcome.NOT_REVERSIBLE

        if record.action_type in ("file_delete", "folder_delete"):
            return self._recover_deleted_path(record)

        if record.action_type == "launch_application":
            return self._recover_launched_application(record)

        return RecoveryOutcome.NOT_REVERSIBLE

    def _recover_deleted_path(self, record: ActionAuditRecord) -> RecoveryOutcome:
        original_path_str = _extract_summary_value(record.parameters_summary, "path")
        if not original_path_str:
            logger.warning("No 'path' found in audit record summary; cannot recover.")
            return RecoveryOutcome.RECOVERY_FAILED
        original_path = Path(original_path_str)
        try:
            entry = _find_recycle_bin_entry(original_path, record.recorded_at)
            if entry is None:
                logger.info("No matching Recycle Bin entry found for %s.", original_path_str)
                return RecoveryOutcome.RECOVERY_FAILED
            original_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entry.data_file), str(original_path))
            entry.info_file.unlink(missing_ok=True)
        except Exception:
            logger.exception("Recycle Bin restore failed for %s.", original_path_str)
            return RecoveryOutcome.RECOVERY_FAILED
        logger.info("Recovered %s from the Recycle Bin.", original_path_str)
        return RecoveryOutcome.RECOVERED

    def _recover_launched_application(self, record: ActionAuditRecord) -> RecoveryOutcome:
        process_id_str = _extract_summary_value(record.parameters_summary, "process_id")
        if not process_id_str:
            return RecoveryOutcome.RECOVERY_FAILED
        try:
            process_id = int(process_id_str)
        except ValueError:
            return RecoveryOutcome.RECOVERY_FAILED
        try:
            closed = self._application_manager.close(process_id)
        except Exception:
            logger.exception("Failed to close launched application pid=%d.", process_id)
            return RecoveryOutcome.RECOVERY_FAILED
        return RecoveryOutcome.RECOVERED if closed else RecoveryOutcome.RECOVERY_FAILED
