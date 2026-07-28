"""Unit tests for workflow.workflow_store."""

from datetime import UTC, datetime

import pytest

from config.schema import WorkflowConfig
from database.sqlite_client import SqliteClient
from device_control.action_engine import ActionType
from workflow.workflow_model import WorkflowDefinition, WorkflowStep
from workflow.workflow_store import WorkflowStore


def make_definition(workflow_id: str = "wf-1", step_count: int = 3) -> WorkflowDefinition:
    steps = []
    for i in range(step_count):
        if i == 0:
            action_type = ActionType.LAUNCH_APPLICATION
            parameters = {"executable_path": "code.exe"}
        else:
            action_type = ActionType.FILE_MOVE
            parameters = {"source": "a", "destination": "b"}
        steps.append(
            WorkflowStep(
                step_index=i,
                action_type=action_type,
                parameters=parameters,
                description=f"Step {i}",
                continue_on_failure=(i % 2 == 0),
            )
        )
    return WorkflowDefinition(
        workflow_id=workflow_id,
        name="Continue Project JARMINEI",
        steps=steps,
        created_by="user_voice",
        created_at=datetime(2026, 7, 21, 10, 0, 0, tzinfo=UTC),
        is_enabled=True,
    )


@pytest.fixture
def store(tmp_path) -> WorkflowStore:
    client = SqliteClient(str(tmp_path / "workflow.db"))
    workflow_store = WorkflowStore(client, WorkflowConfig())
    workflow_store.start()
    yield workflow_store
    workflow_store.stop()


# --- save()/get() round trip -----------------------------------------------------


def test_save_get_round_trip_preserves_every_field(store):
    definition = make_definition()

    store.save(definition)
    fetched = store.get(definition.workflow_id)

    assert fetched is not None
    assert fetched.workflow_id == definition.workflow_id
    assert fetched.name == definition.name
    assert fetched.created_by == definition.created_by
    assert fetched.created_at == definition.created_at
    assert fetched.is_enabled == definition.is_enabled
    assert len(fetched.steps) == len(definition.steps)
    for original, restored in zip(definition.steps, fetched.steps, strict=True):
        assert restored.step_index == original.step_index
        assert restored.action_type == original.action_type
        assert restored.parameters == original.parameters
        assert restored.description == original.description
        assert restored.continue_on_failure == original.continue_on_failure


def test_save_get_preserves_step_order(store):
    definition = make_definition(step_count=5)

    store.save(definition)
    fetched = store.get(definition.workflow_id)

    assert [step.step_index for step in fetched.steps] == [0, 1, 2, 3, 4]


def test_get_nonexistent_workflow_returns_none(store):
    assert store.get("does-not-exist") is None


def test_save_overwrites_existing_workflow_outright(store):
    definition = make_definition(step_count=3)
    store.save(definition)

    updated = make_definition(step_count=1)
    updated.name = "Renamed"
    store.save(updated)

    fetched = store.get(definition.workflow_id)
    assert fetched.name == "Renamed"
    assert len(fetched.steps) == 1


# --- list_all() --------------------------------------------------------------------


def test_list_all_reflects_save_and_delete(store):
    assert store.list_all() == []

    store.save(make_definition("wf-a"))
    store.save(make_definition("wf-b"))
    assert {d.workflow_id for d in store.list_all()} == {"wf-a", "wf-b"}

    store.delete("wf-a")
    assert {d.workflow_id for d in store.list_all()} == {"wf-b"}


# --- max_steps_per_workflow --------------------------------------------------------


def test_save_exceeding_max_steps_raises_value_error_and_persists_nothing(tmp_path):
    client = SqliteClient(str(tmp_path / "small.db"))
    store = WorkflowStore(client, WorkflowConfig(max_steps_per_workflow=2))
    store.start()
    try:
        definition = make_definition(step_count=3)

        with pytest.raises(ValueError, match="max_steps_per_workflow"):
            store.save(definition)

        assert store.get(definition.workflow_id) is None
        assert store.list_all() == []
    finally:
        store.stop()


# --- set_enabled() -----------------------------------------------------------------


def test_set_enabled_persists_and_is_readable(store):
    definition = make_definition()
    store.save(definition)

    result = store.set_enabled(definition.workflow_id, False)

    assert result is True
    assert store.get(definition.workflow_id).is_enabled is False


def test_set_enabled_nonexistent_workflow_returns_false(store):
    assert store.set_enabled("does-not-exist", False) is False


# --- delete() ------------------------------------------------------------------------


def test_delete_nonexistent_workflow_returns_false(store):
    assert store.delete("does-not-exist") is False


def test_delete_removes_workflow_and_its_steps(store, tmp_path):
    definition = make_definition()
    store.save(definition)

    assert store.delete(definition.workflow_id) is True
    assert store.get(definition.workflow_id) is None

    # Directly confirm no orphaned step rows remain.
    client = SqliteClient(str(tmp_path / "workflow.db"))
    client.connect()
    rows = client.query(
        "SELECT COUNT(*) FROM workflow_steps WHERE workflow_id = ?", (definition.workflow_id,)
    )
    assert rows[0][0] == 0
    client.close()


# --- real persistence across close()/reopen ----------------------------------------


def test_persistence_survives_close_and_reopen(tmp_path):
    db_path = str(tmp_path / "persist.db")
    definition = make_definition()

    client1 = SqliteClient(db_path)
    store1 = WorkflowStore(client1, WorkflowConfig())
    store1.start()
    store1.save(definition)
    store1.stop()

    client2 = SqliteClient(db_path)
    store2 = WorkflowStore(client2, WorkflowConfig())
    store2.start()
    fetched = store2.get(definition.workflow_id)
    store2.stop()

    assert fetched is not None
    assert fetched.name == definition.name
    assert len(fetched.steps) == len(definition.steps)


# --- health_check() ------------------------------------------------------------------


def test_health_check_false_before_start(tmp_path):
    client = SqliteClient(str(tmp_path / "hc.db"))
    store = WorkflowStore(client, WorkflowConfig())
    assert store.health_check() is False


def test_health_check_true_after_start(store):
    assert store.health_check() is True


# --- Sprint 4.13 hardening: SQLite failure handling (adversarial re-read) -----------
# get()/list_all() are this class's only two methods with a real, live production
# caller today (WorkflowExecutor.run(), CommunicationPipeline._resolve_workflow_
# by_name()) — see workflow_store.py's own docstring and docs/backlog/
# technical_debt.md item 27 for why save()/delete()/set_enabled() are not
# hardened here.


class _RaisingSqliteClient(SqliteClient):
    """Matches the project's established "_Raising*-style local test double"
    pattern (tests/unit/memory/test_memory_store.py, Sprint 3.14) — a real
    SqliteClient whose query() can be switched to fail on demand, after
    start() has already succeeded."""

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.raise_on_query = False

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self.raise_on_query:
            raise RuntimeError("sqlite query exploded")
        return super().query(sql, params)


def _make_raising_store(tmp_path) -> tuple[WorkflowStore, _RaisingSqliteClient]:
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    store = WorkflowStore(client, WorkflowConfig())
    store.start()  # succeeds — failure is switched on only afterward
    return store, client


def test_get_degrades_to_none_on_a_sqlite_read_failure(tmp_path):
    store, client = _make_raising_store(tmp_path)
    try:
        store.save(make_definition())
        client.raise_on_query = True

        assert store.get("wf-1") is None
    finally:
        client.raise_on_query = False
        store.stop()


def test_list_all_degrades_to_empty_list_on_a_sqlite_read_failure(tmp_path):
    store, client = _make_raising_store(tmp_path)
    try:
        store.save(make_definition())
        client.raise_on_query = True

        assert store.list_all() == []
    finally:
        client.raise_on_query = False
        store.stop()
