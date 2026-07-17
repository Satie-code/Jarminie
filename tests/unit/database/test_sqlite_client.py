"""Unit tests for database.sqlite_client.

Uses a real SQLite file under pytest's tmp_path for every test — no
in-memory (":memory:") database, since a real file is what lets
"connect, close, reopen" simulate an actual restart, matching this
project's established "real save, real reload" discipline (Sprint 1.8's
ConfigLoader tests, Sprint 2.7's own conversation-store restart test).
"""

import pytest

from database.sqlite_client import SqliteClient


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "nested" / "test.db")


def test_execute_and_query_round_trip(db_path):
    client = SqliteClient(db_path)
    client.connect()
    try:
        client.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        client.execute("INSERT INTO widgets (name) VALUES (?)", ("gizmo",))
        client.execute("INSERT INTO widgets (name) VALUES (?)", ("gadget",))

        rows = client.query("SELECT name FROM widgets ORDER BY name")
    finally:
        client.close()

    assert rows == [("gadget",), ("gizmo",)]


def test_connect_creates_parent_directory(db_path):
    client = SqliteClient(db_path)

    client.connect()
    client.close()

    from pathlib import Path

    assert Path(db_path).parent.is_dir()


def test_wal_mode_enabled_on_connect(db_path):
    client = SqliteClient(db_path)
    client.connect()
    try:
        mode = client.query("PRAGMA journal_mode")
    finally:
        client.close()

    assert mode[0][0].lower() == "wal"


def test_execute_before_connect_raises(db_path):
    client = SqliteClient(db_path)

    with pytest.raises(RuntimeError, match="connect"):
        client.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY)")


def test_query_before_connect_raises(db_path):
    client = SqliteClient(db_path)

    with pytest.raises(RuntimeError, match="connect"):
        client.query("SELECT 1")


def test_data_survives_close_and_reopen_on_same_file(db_path):
    writer = SqliteClient(db_path)
    writer.connect()
    writer.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    writer.execute("INSERT INTO widgets (name) VALUES (?)", ("gizmo",))
    writer.close()

    reader = SqliteClient(db_path)
    reader.connect()
    try:
        rows = reader.query("SELECT name FROM widgets")
    finally:
        reader.close()

    assert rows == [("gizmo",)]


def test_close_is_idempotent(db_path):
    client = SqliteClient(db_path)
    client.connect()

    client.close()
    client.close()  # must not raise


def test_reconnect_after_close_works(db_path):
    client = SqliteClient(db_path)
    client.connect()
    client.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY)")
    client.close()

    client.connect()
    try:
        client.execute("INSERT INTO widgets DEFAULT VALUES")
        rows = client.query("SELECT COUNT(*) FROM widgets")
    finally:
        client.close()

    assert rows == [(1,)]
