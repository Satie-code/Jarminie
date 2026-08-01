"""Unit tests for scheduler.calendar_store."""

from datetime import UTC, datetime, timedelta

import pytest

from config.schema import SchedulerConfig
from database.sqlite_client import SqliteClient
from scheduler.calendar_store import CalendarStore
from scheduler.scheduler_model import ItemType, ScheduledItem

_NOW = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


def make_item(
    item_id: str = "item-1",
    item_type: ItemType = ItemType.EVENT,
    scheduled_at: datetime = _NOW + timedelta(hours=1),
    is_completed: bool = False,
) -> ScheduledItem:
    return ScheduledItem(
        item_id=item_id,
        item_type=item_type,
        title="Team standup",
        scheduled_at=scheduled_at,
        created_at=_NOW,
        description="Daily sync",
        is_completed=is_completed,
    )


@pytest.fixture
def store(tmp_path) -> CalendarStore:
    client = SqliteClient(str(tmp_path / "calendar.db"))
    calendar_store = CalendarStore(client, SchedulerConfig())
    calendar_store.start()
    yield calendar_store
    calendar_store.stop()


# --- save()/get() round trip -------------------------------------------------------


def test_save_get_round_trip_preserves_every_field(store):
    item = make_item()

    store.save(item)
    fetched = store.get(item.item_id)

    assert fetched is not None
    assert fetched.item_id == item.item_id
    assert fetched.item_type == item.item_type
    assert fetched.title == item.title
    assert fetched.scheduled_at == item.scheduled_at
    assert fetched.created_at == item.created_at
    assert fetched.description == item.description
    assert fetched.is_completed == item.is_completed


def test_save_get_preserves_deadline_type(store):
    item = make_item(item_type=ItemType.DEADLINE)
    store.save(item)
    assert store.get(item.item_id).item_type is ItemType.DEADLINE


def test_get_nonexistent_item_returns_none(store):
    assert store.get("does-not-exist") is None


def test_save_overwrites_existing_item_outright(store):
    item = make_item()
    store.save(item)

    updated = make_item()
    updated.title = "Renamed standup"
    store.save(updated)

    fetched = store.get(item.item_id)
    assert fetched.title == "Renamed standup"


# --- list_all() ----------------------------------------------------------------------


def test_list_all_reflects_save_and_delete(store):
    assert store.list_all() == []

    store.save(make_item("item-a"))
    store.save(make_item("item-b"))
    assert {i.item_id for i in store.list_all()} == {"item-a", "item-b"}

    store.delete("item-a")
    assert {i.item_id for i in store.list_all()} == {"item-b"}


# --- list_due_within() -----------------------------------------------------------


def test_list_due_within_returns_items_at_or_before_window_end_soonest_first(store):
    soon = make_item("soon", scheduled_at=_NOW + timedelta(minutes=5))
    later = make_item("later", scheduled_at=_NOW + timedelta(hours=2))
    far = make_item("far", scheduled_at=_NOW + timedelta(days=10))
    for item in (far, soon, later):
        store.save(item)

    due = store.list_due_within(_NOW + timedelta(hours=3))

    assert [i.item_id for i in due] == ["soon", "later"]


def test_list_due_within_includes_overdue_items(store):
    overdue = make_item("overdue", scheduled_at=_NOW - timedelta(days=1))
    store.save(overdue)

    due = store.list_due_within(_NOW)

    assert [i.item_id for i in due] == ["overdue"]


def test_list_due_within_excludes_completed_by_default(store):
    completed = make_item("done", scheduled_at=_NOW + timedelta(minutes=1), is_completed=True)
    store.save(completed)

    assert store.list_due_within(_NOW + timedelta(hours=1)) == []
    assert [
        i.item_id
        for i in store.list_due_within(_NOW + timedelta(hours=1), include_completed=True)
    ] == ["done"]


def test_list_due_within_exact_window_end_is_included(store):
    exact = make_item("exact", scheduled_at=_NOW)
    store.save(exact)
    assert [i.item_id for i in store.list_due_within(_NOW)] == ["exact"]


def test_list_due_within_just_past_window_end_is_excluded(store):
    just_after = make_item("just-after", scheduled_at=_NOW + timedelta(seconds=1))
    store.save(just_after)
    assert store.list_due_within(_NOW) == []


def test_list_due_within_beyond_max_lookahead_days_raises_value_error(tmp_path):
    client = SqliteClient(str(tmp_path / "small.db"))
    store = CalendarStore(client, SchedulerConfig(max_lookahead_days=1))
    store.start()
    try:
        with pytest.raises(ValueError, match="max_lookahead_days"):
            store.list_due_within(datetime.now(UTC) + timedelta(days=2))
    finally:
        store.stop()


# --- mark_completed() ---------------------------------------------------------------


def test_mark_completed_persists_and_is_readable(store):
    item = make_item()
    store.save(item)

    result = store.mark_completed(item.item_id)

    assert result is True
    assert store.get(item.item_id).is_completed is True


def test_mark_completed_nonexistent_item_returns_false(store):
    assert store.mark_completed("does-not-exist") is False


# --- delete() ------------------------------------------------------------------------


def test_delete_nonexistent_item_returns_false(store):
    assert store.delete("does-not-exist") is False


def test_delete_removes_item(store):
    item = make_item()
    store.save(item)

    assert store.delete(item.item_id) is True
    assert store.get(item.item_id) is None


# --- real persistence across close()/reopen ----------------------------------------


def test_persistence_survives_close_and_reopen(tmp_path):
    db_path = str(tmp_path / "persist.db")
    item = make_item()

    client1 = SqliteClient(db_path)
    store1 = CalendarStore(client1, SchedulerConfig())
    store1.start()
    store1.save(item)
    store1.stop()

    client2 = SqliteClient(db_path)
    store2 = CalendarStore(client2, SchedulerConfig())
    store2.start()
    fetched = store2.get(item.item_id)
    store2.stop()

    assert fetched is not None
    assert fetched.title == item.title


# --- Sprint 4.19 hardening (scenario e): Fail Gracefully -----------------------------


class _RaisingSqliteClient(SqliteClient):
    """Matches the project's established "_Raising*-style local test
    double" pattern (tests/unit/memory/test_memory_store.py, Sprint
    3.14; tests/unit/workflow/test_workflow_store.py, Sprint 4.13) — a
    real SqliteClient whose query() can be switched to fail on demand,
    after start() has already succeeded."""

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.raise_on_query = False

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self.raise_on_query:
            raise RuntimeError("sqlite query exploded")
        return super().query(sql, params)


def test_list_due_within_degrades_to_empty_list_on_a_sqlite_read_failure(tmp_path):
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    calendar_store = CalendarStore(client, SchedulerConfig())
    calendar_store.start()
    try:
        calendar_store.save(make_item(scheduled_at=_NOW))
        client.raise_on_query = True

        assert calendar_store.list_due_within(_NOW + timedelta(days=1)) == []
    finally:
        client.raise_on_query = False
        calendar_store.stop()


def test_list_due_within_max_lookahead_days_check_still_raises_even_while_query_fails(tmp_path):
    """The ValueError guard for an unreasonable window_end is a real
    caller-error signal, not a SQLite failure — it must never be
    silently swallowed into an empty-list degrade, even while the
    underlying query is also (independently) set to fail."""
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    calendar_store = CalendarStore(client, SchedulerConfig(max_lookahead_days=1))
    calendar_store.start()
    try:
        client.raise_on_query = True
        with pytest.raises(ValueError, match="max_lookahead_days"):
            calendar_store.list_due_within(_NOW + timedelta(days=365))
    finally:
        client.raise_on_query = False
        calendar_store.stop()


# --- health_check() ------------------------------------------------------------------


def test_health_check_false_before_start(tmp_path):
    client = SqliteClient(str(tmp_path / "hc.db"))
    store = CalendarStore(client, SchedulerConfig())
    assert store.health_check() is False


def test_health_check_true_after_start(store):
    assert store.health_check() is True
