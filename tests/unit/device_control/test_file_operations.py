"""Unit tests for device_control.file_operations.

Every test operates exclusively within a tmp_path-scoped
allowed_file_roots — never the real filesystem outside a test's own
temp directory, given the destructive potential of this executor.
"""

import os
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from config.schema import DeviceControlConfig
from device_control.action_engine import ActionContext, ActionRequest, ActionStatus, ActionType
from device_control.file_operations import FileOperationsManager


def make_request(action_type: ActionType, **parameters) -> ActionRequest:
    return ActionRequest(
        action_type=action_type,
        parameters=parameters,
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )


@pytest.fixture
def manager(tmp_path):
    config = DeviceControlConfig(allowed_file_roots=[str(tmp_path)])
    return FileOperationsManager(config)


# --- can_handle() ---------------------------------------------------------------


def test_can_handle_every_file_and_folder_action_type(manager):
    for action_type in (
        ActionType.FILE_CREATE,
        ActionType.FILE_MOVE,
        ActionType.FILE_COPY,
        ActionType.FILE_RENAME,
        ActionType.FILE_DELETE,
        ActionType.FOLDER_CREATE,
        ActionType.FOLDER_DELETE,
    ):
        assert manager.can_handle(action_type) is True


def test_cannot_handle_unrelated_action_type(manager):
    assert manager.can_handle(ActionType.LAUNCH_APPLICATION) is False


# --- FILE_CREATE / FOLDER_CREATE --------------------------------------------------


def test_file_create_succeeds_within_scope(manager, tmp_path):
    target = tmp_path / "note.txt"
    result = manager.execute(
        make_request(ActionType.FILE_CREATE, path=str(target), content="hello")
    )

    assert result.status is ActionStatus.SUCCEEDED
    assert target.read_text(encoding="utf-8") == "hello"
    assert result.output == {"path": str(target), "operation": "file_create"}


def test_file_create_already_exists_fails(manager, tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("existing")

    result = manager.execute(make_request(ActionType.FILE_CREATE, path=str(target)))

    assert result.status is ActionStatus.FAILED
    assert "already exists" in result.error_message


def test_file_create_missing_parent_fails(manager, tmp_path):
    target = tmp_path / "no_such_dir" / "note.txt"

    result = manager.execute(make_request(ActionType.FILE_CREATE, path=str(target)))

    assert result.status is ActionStatus.FAILED
    assert not target.exists()


def test_folder_create_succeeds_within_scope_and_creates_parents(manager, tmp_path):
    target = tmp_path / "a" / "b" / "c"

    result = manager.execute(make_request(ActionType.FOLDER_CREATE, path=str(target)))

    assert result.status is ActionStatus.SUCCEEDED
    assert target.is_dir()


def test_file_create_missing_path_parameter_fails(manager):
    result = manager.execute(make_request(ActionType.FILE_CREATE))
    assert result.status is ActionStatus.FAILED
    assert "path" in result.error_message


# --- FILE_MOVE / FILE_COPY / FILE_RENAME ------------------------------------------


def test_file_move_succeeds_within_scope(manager, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("content")
    destination = tmp_path / "moved.txt"

    result = manager.execute(
        make_request(ActionType.FILE_MOVE, source=str(source), destination=str(destination))
    )

    assert result.status is ActionStatus.SUCCEEDED
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "content"


def test_folder_move_succeeds_within_scope(manager, tmp_path):
    source = tmp_path / "source_dir"
    source.mkdir()
    (source / "inner.txt").write_text("x")
    destination = tmp_path / "moved_dir"

    result = manager.execute(
        make_request(ActionType.FILE_MOVE, source=str(source), destination=str(destination))
    )

    assert result.status is ActionStatus.SUCCEEDED
    assert not source.exists()
    assert (destination / "inner.txt").exists()


def test_file_copy_succeeds_and_preserves_source(manager, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("content")
    destination = tmp_path / "copied.txt"

    result = manager.execute(
        make_request(ActionType.FILE_COPY, source=str(source), destination=str(destination))
    )

    assert result.status is ActionStatus.SUCCEEDED
    assert source.read_text(encoding="utf-8") == "content"
    assert destination.read_text(encoding="utf-8") == "content"


def test_folder_copy_succeeds_and_preserves_source(manager, tmp_path):
    source = tmp_path / "source_dir"
    source.mkdir()
    (source / "inner.txt").write_text("x")
    destination = tmp_path / "copied_dir"

    result = manager.execute(
        make_request(ActionType.FILE_COPY, source=str(source), destination=str(destination))
    )

    assert result.status is ActionStatus.SUCCEEDED
    assert (source / "inner.txt").exists()
    assert (destination / "inner.txt").exists()


def test_move_or_copy_missing_source_fails(manager, tmp_path):
    result = manager.execute(
        make_request(
            ActionType.FILE_MOVE,
            source=str(tmp_path / "does_not_exist.txt"),
            destination=str(tmp_path / "dest.txt"),
        )
    )
    assert result.status is ActionStatus.FAILED


def test_move_destination_already_exists_fails(manager, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("x")
    destination = tmp_path / "dest.txt"
    destination.write_text("already here")

    result = manager.execute(
        make_request(ActionType.FILE_MOVE, source=str(source), destination=str(destination))
    )

    assert result.status is ActionStatus.FAILED
    assert source.exists()  # untouched


# --- partial-move detection (Sprint 4.12 hardening, scenario b) --------------------


def test_move_reports_a_clear_error_when_the_original_cannot_be_removed(manager, tmp_path):
    """Real, induced failure — a read-only source file genuinely cannot
    be deleted on Windows once copied, not a mocked exception. Proves
    the destination copy is left intact and honestly reported, rather
    than a generic FAILED hiding a real, silently-duplicated file."""
    source = tmp_path / "source.txt"
    source.write_text("real content")
    destination = tmp_path / "dest.txt"
    source.chmod(0o444)  # read-only: Windows refuses to delete this

    try:
        result = manager.execute(
            make_request(ActionType.FILE_MOVE, source=str(source), destination=str(destination))
        )
    finally:
        source.chmod(0o666)  # restore so tmp_path's own cleanup can remove it

    assert result.status is ActionStatus.FAILED
    assert "could not remove the original" in result.error_message
    assert destination.exists()
    assert destination.read_text(encoding="utf-8") == "real content"
    assert source.exists()  # nothing lost — both copies still present


def test_file_rename_succeeds_within_scope(manager, tmp_path):
    source = tmp_path / "old_name.txt"
    source.write_text("content")

    result = manager.execute(
        make_request(ActionType.FILE_RENAME, path=str(source), new_name="new_name.txt")
    )

    assert result.status is ActionStatus.SUCCEEDED
    assert not source.exists()
    assert (tmp_path / "new_name.txt").read_text(encoding="utf-8") == "content"


def test_folder_rename_succeeds_within_scope(manager, tmp_path):
    source = tmp_path / "old_dir"
    source.mkdir()

    result = manager.execute(
        make_request(ActionType.FILE_RENAME, path=str(source), new_name="new_dir")
    )

    assert result.status is ActionStatus.SUCCEEDED
    assert (tmp_path / "new_dir").is_dir()


def test_rename_missing_new_name_fails(manager, tmp_path):
    source = tmp_path / "file.txt"
    source.write_text("x")

    result = manager.execute(make_request(ActionType.FILE_RENAME, path=str(source)))

    assert result.status is ActionStatus.FAILED
    assert source.exists()


# --- FILE_DELETE / FOLDER_DELETE (recycle-bin only) --------------------------------


def test_file_delete_removes_the_file(manager, tmp_path):
    target = tmp_path / "delete_me.txt"
    target.write_text("bye")

    result = manager.execute(make_request(ActionType.FILE_DELETE, path=str(target)))

    assert result.status is ActionStatus.SUCCEEDED
    assert not target.exists()


def test_folder_delete_removes_the_folder(manager, tmp_path):
    target = tmp_path / "delete_dir"
    target.mkdir()
    (target / "inner.txt").write_text("x")

    result = manager.execute(make_request(ActionType.FOLDER_DELETE, path=str(target)))

    assert result.status is ActionStatus.SUCCEEDED
    assert not target.exists()


def test_delete_routes_through_send2trash_not_direct_os_delete(manager, tmp_path):
    target = tmp_path / "delete_me.txt"
    target.write_text("bye")

    with patch("device_control.file_operations.send2trash.send2trash") as send2trash_mock:
        manager.execute(make_request(ActionType.FILE_DELETE, path=str(target)))

    send2trash_mock.assert_called_once_with(str(target))


def test_delete_nonexistent_path_fails(manager, tmp_path):
    result = manager.execute(
        make_request(ActionType.FILE_DELETE, path=str(tmp_path / "ghost.txt"))
    )
    assert result.status is ActionStatus.FAILED


def test_delete_with_recycle_bin_disabled_refuses_and_fails(tmp_path):
    config = DeviceControlConfig(
        allowed_file_roots=[str(tmp_path)], use_recycle_bin_for_delete=False
    )
    manager = FileOperationsManager(config)
    target = tmp_path / "delete_me.txt"
    target.write_text("bye")

    result = manager.execute(make_request(ActionType.FILE_DELETE, path=str(target)))

    assert result.status is ActionStatus.FAILED
    assert "use_recycle_bin_for_delete" in result.error_message
    assert target.exists()  # never touched -- delete() refused before send2trash ran


def test_delete_public_method_raises_directly_when_recycle_bin_disabled(tmp_path):
    config = DeviceControlConfig(
        allowed_file_roots=[str(tmp_path)], use_recycle_bin_for_delete=False
    )
    manager = FileOperationsManager(config)

    with pytest.raises(RuntimeError, match="use_recycle_bin_for_delete"):
        manager.delete(str(tmp_path / "anything.txt"))


# --- Path-scope enforcement --------------------------------------------------------


def test_operation_outside_allowed_root_is_denied(manager, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    target = outside / "note.txt"

    result = manager.execute(make_request(ActionType.FILE_CREATE, path=str(target)))

    assert result.status is ActionStatus.DENIED
    assert not target.exists()


def test_dot_dot_traversal_escaping_the_root_is_denied(manager, tmp_path):
    escaping_path = str(tmp_path / ".." / (tmp_path.name + "_sibling") / "note.txt")

    result = manager.execute(make_request(ActionType.FILE_CREATE, path=escaping_path))

    assert result.status is ActionStatus.DENIED


def test_symlink_escape_is_denied(manager, tmp_path, tmp_path_factory):
    """A real Windows symlink inside the allowed root pointing outside
    it must not let an operation escape scope -- Path.resolve() follows
    the symlink before the containment check runs."""
    outside = tmp_path_factory.mktemp("outside")
    secret = outside / "secret.txt"
    secret.write_text("do not touch")

    link_path = tmp_path / "escape_link"
    try:
        os.symlink(str(outside), str(link_path), target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Could not create a real symlink in this environment: {exc}")

    result = manager.execute(
        make_request(ActionType.FILE_DELETE, path=str(link_path / "secret.txt"))
    )

    assert result.status is ActionStatus.DENIED
    assert secret.exists()


def test_path_scope_check_never_reaches_the_filesystem_operation(manager, tmp_path_factory):
    """A denied path must be rejected before any operation-specific
    filesystem call — verified by mocking send2trash and confirming
    it's never called for an out-of-scope delete."""
    outside = tmp_path_factory.mktemp("outside")
    target = outside / "secret.txt"
    target.write_text("do not touch")

    with patch("device_control.file_operations.send2trash.send2trash") as send2trash_mock:
        result = manager.execute(make_request(ActionType.FILE_DELETE, path=str(target)))

    assert result.status is ActionStatus.DENIED
    send2trash_mock.assert_not_called()
    assert target.exists()
