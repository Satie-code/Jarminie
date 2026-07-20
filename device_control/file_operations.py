"""File & Folder Operations — Level 4's second real ActionExecutor:
create, move, copy, rename, and delete for both files and folders, with
real safeguards. See docs/sprint_book/sprint_4_3.md.

Two hard, structural invariants, not configurable overrides:

- Every target path must resolve inside a configured allowed root
  (path-scoping), checked once per handler before any filesystem call
  runs — there is no "admin override" parameter anywhere in this class.
- delete() always routes through the OS recycle bin (Send2Trash),
  never a permanent os.remove()/shutil.rmtree() call. There is no
  permanent-delete fallback: if use_recycle_bin_for_delete is ever
  False (not intended for any shipped config — see
  config/schema.py's DeviceControlConfig docstring), delete() refuses
  to run at all rather than silently downgrading safety.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import send2trash

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
        ActionType.FILE_CREATE,
        ActionType.FILE_MOVE,
        ActionType.FILE_COPY,
        ActionType.FILE_RENAME,
        ActionType.FILE_DELETE,
        ActionType.FOLDER_CREATE,
        ActionType.FOLDER_DELETE,
    }
)


class PathScopeError(Exception):
    """Raised internally when a target path resolves outside every
    configured allowed root. Always caught at execute()'s own
    boundary — never propagates past this module."""


@dataclass
class _OperationOutcome:
    """Internal result shape a handler hands back to execute() before
    it's wrapped in an ActionResult — keeps every handler's own return
    statement free of ActionResult/ActionStatus boilerplate."""

    path: str
    operation: str


class FileOperationsManager:
    """Constructor DI: (device_control_config). Handles FILE_CREATE,
    FILE_MOVE, FILE_COPY, FILE_RENAME, FILE_DELETE, FOLDER_CREATE,
    FOLDER_DELETE.

    execute() only ever catches PathScopeError (-> DENIED) and
    OSError/RuntimeError (-> FAILED) — errors this class can
    meaningfully interpret and report — never a bare except, per
    docs/CODING_STANDARDS.md.
    """

    def __init__(self, device_control_config: DeviceControlConfig) -> None:
        self._config = device_control_config

    def can_handle(self, action_type: ActionType) -> bool:
        return action_type in _HANDLED_TYPES

    def execute(self, request: ActionRequest) -> ActionResult:
        try:
            outcome = self._dispatch(request)
        except PathScopeError as exc:
            logger.warning("Path scope violation: %s", exc)
            return ActionResult(
                request=request,
                status=ActionStatus.DENIED,
                completed_at=datetime.now(UTC),
                error_message=str(exc),
            )
        except (OSError, RuntimeError) as exc:
            logger.exception("File operation failed: %s", request.action_type.value)
            return ActionResult(
                request=request,
                status=ActionStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message=str(exc),
            )

        return ActionResult(
            request=request,
            status=ActionStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
            output={"path": outcome.path, "operation": outcome.operation},
        )

    def delete(self, path: str) -> None:
        """Routes through the OS recycle bin (Send2Trash), always —
        see this module's own docstring for why there is no permanent-
        delete fallback."""
        if not self._config.use_recycle_bin_for_delete:
            raise RuntimeError(
                "device_control.use_recycle_bin_for_delete is False — "
                "refusing to delete without recycle-bin recovery. "
                "FileOperationsManager never performs a permanent delete."
            )
        send2trash.send2trash(path)
        logger.info("Deleted via recycle bin: %s", path)

    def _dispatch(self, request: ActionRequest) -> _OperationOutcome:
        action_type = request.action_type
        if action_type is ActionType.FILE_CREATE:
            return self._handle_create(request, is_folder=False)
        if action_type is ActionType.FOLDER_CREATE:
            return self._handle_create(request, is_folder=True)
        if action_type is ActionType.FILE_MOVE:
            return self._handle_move(request)
        if action_type is ActionType.FILE_COPY:
            return self._handle_copy(request)
        if action_type is ActionType.FILE_RENAME:
            return self._handle_rename(request)
        if action_type is ActionType.FILE_DELETE:
            return self._handle_delete(request, "file_delete")
        if action_type is ActionType.FOLDER_DELETE:
            return self._handle_delete(request, "folder_delete")
        raise RuntimeError(f"Unhandled action type: {action_type.value}")

    def _validate_path_scope(self, raw_path: str) -> Path:
        """Resolves raw_path (following symlinks/junctions) and checks
        it is the same as, or a descendant of, at least one configured
        allowed_file_roots entry. Non-strict resolve() — a target that
        doesn't exist yet (e.g. a file about to be created) still
        resolves correctly for scope-checking purposes."""
        candidate = Path(raw_path).resolve()
        for root in self._config.allowed_file_roots:
            root_resolved = Path(root).resolve()
            if candidate == root_resolved or root_resolved in candidate.parents:
                return candidate
        raise PathScopeError(f"Path is outside every configured allowed root: {candidate}")

    def _handle_create(self, request: ActionRequest, *, is_folder: bool) -> _OperationOutcome:
        path_param = request.parameters.get("path")
        if not path_param:
            raise RuntimeError("Missing required parameter: path")
        target = self._validate_path_scope(path_param)
        if target.exists():
            raise OSError(f"Path already exists: {target}")
        if is_folder:
            target.mkdir(parents=True)
            return _OperationOutcome(path=str(target), operation="folder_create")
        if not target.parent.exists():
            raise OSError(f"Parent directory does not exist: {target.parent}")
        content = request.parameters.get("content", "")
        target.write_text(content, encoding="utf-8")
        return _OperationOutcome(path=str(target), operation="file_create")

    def _handle_move(self, request: ActionRequest) -> _OperationOutcome:
        source, destination = self._resolve_source_and_destination(request)
        if destination.exists():
            raise OSError(f"Destination already exists: {destination}")
        shutil.move(str(source), str(destination))
        return _OperationOutcome(path=str(destination), operation="file_move")

    def _handle_copy(self, request: ActionRequest) -> _OperationOutcome:
        source, destination = self._resolve_source_and_destination(request)
        if destination.exists():
            raise OSError(f"Destination already exists: {destination}")
        if source.is_dir():
            shutil.copytree(str(source), str(destination))
        else:
            shutil.copy2(str(source), str(destination))
        return _OperationOutcome(path=str(destination), operation="file_copy")

    def _handle_rename(self, request: ActionRequest) -> _OperationOutcome:
        path_param = request.parameters.get("path")
        new_name = request.parameters.get("new_name")
        if not path_param or not new_name:
            raise RuntimeError("Missing required parameter(s): path, new_name")
        source = self._validate_path_scope(path_param)
        if not source.exists():
            raise OSError(f"Path does not exist: {source}")
        destination = self._validate_path_scope(str(source.parent / new_name))
        if destination.exists():
            raise OSError(f"Destination already exists: {destination}")
        source.rename(destination)
        return _OperationOutcome(path=str(destination), operation="rename")

    def _handle_delete(self, request: ActionRequest, operation_label: str) -> _OperationOutcome:
        path_param = request.parameters.get("path")
        if not path_param:
            raise RuntimeError("Missing required parameter: path")
        target = self._validate_path_scope(path_param)
        if not target.exists():
            raise OSError(f"Path does not exist: {target}")
        self.delete(str(target))
        return _OperationOutcome(path=str(target), operation=operation_label)

    def _resolve_source_and_destination(self, request: ActionRequest) -> tuple[Path, Path]:
        source_param = request.parameters.get("source")
        destination_param = request.parameters.get("destination")
        if not source_param or not destination_param:
            raise RuntimeError("Missing required parameter(s): source, destination")
        source = self._validate_path_scope(source_param)
        destination = self._validate_path_scope(destination_param)
        if not source.exists():
            raise OSError(f"Source path does not exist: {source}")
        return source, destination
