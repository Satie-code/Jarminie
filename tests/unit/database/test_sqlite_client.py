"""Unit tests for database.sqlite_client.

Uses a real SQLite file under pytest's tmp_path for every test — no
in-memory (":memory:") database, since a real file is what lets
"connect, close, reopen" simulate an actual restart, matching this
project's established "real save, real reload" discipline (Sprint 1.8's
ConfigLoader tests, Sprint 2.7's own conversation-store restart test).
"""

import threading

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


def test_concurrent_execute_and_query_from_multiple_threads_never_corrupts(db_path):
    """Regression test (Sprint 4.18 Post-Sprint Fix): before this class's
    own threading.Lock existed, several real threads hammering execute()/
    query() on the same connection concurrently produced genuine
    sqlite3 errors (InterfaceError "bad parameter or other API misuse",
    DatabaseError "another row available") — check_same_thread=False
    only disables Python's OWN same-thread check, it does not make a
    single Connection object safe for concurrent multi-threaded use on
    its own. Confirmed reproducible via this exact shape (multiple
    threads, hundreds of real operations each) before the fix; this
    test must stay green after it."""
    client = SqliteClient(db_path)
    client.connect()
    client.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    for i in range(20):
        client.execute("INSERT INTO widgets (name) VALUES (?)", (f"n{i}",))

    errors: list[BaseException] = []

    def hammer_query() -> None:
        for _ in range(200):
            try:
                rows = client.query("SELECT id, name FROM widgets")
                for row in rows:
                    _ = row[0], row[1]
            except Exception as exc:
                errors.append(exc)

    def hammer_write() -> None:
        for i in range(200):
            try:
                client.execute("UPDATE widgets SET name = ? WHERE id = 1", (f"x{i}",))
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=hammer_query) for _ in range(4)]
    threads += [threading.Thread(target=hammer_write) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    client.close()

    assert errors == []
