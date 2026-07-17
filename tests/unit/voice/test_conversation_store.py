"""Unit tests for voice.conversation_store.

Uses a real SqliteClient against a temp file for the persistence-focused
tests (round-trip, restart simulation, purge boundaries) — this module's
whole point is persistence across a session boundary, so it gets the same
"real save, real reload" treatment Sprint 1.8 established for ConfigLoader.
A small local RaisingSqliteClient double (not a project-wide fake, since
it's specific to this one failure-injection scenario) covers the one
failure-path test that a real client can't easily simulate.
"""

from datetime import UTC, datetime, timedelta

import pytest

from config.schema import DatabaseConfig
from database.sqlite_client import SqliteClient
from voice.conversation_store import ConversationSessionStore, ConversationTurn
from voice.errors import ConversationStoreError


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "conversations.db")


@pytest.fixture
def database_config(db_path):
    return DatabaseConfig(sqlite_path=db_path, conversation_retention_days=30)


def make_turn(session_id="session-1", **overrides):
    defaults = dict(
        session_id=session_id,
        persona_name="jarvis",
        timestamp=datetime.now(UTC),
        user_text="what's the weather",
        response_text="sunny and 72 degrees",
    )
    defaults.update(overrides)
    return ConversationTurn(**defaults)


def test_starting_creates_table_and_store_is_healthy(db_path, database_config):
    store = ConversationSessionStore(SqliteClient(db_path), database_config)

    store.start()
    try:
        assert store.health_check() is True
    finally:
        store.stop()


def test_health_check_false_before_start(db_path, database_config):
    store = ConversationSessionStore(SqliteClient(db_path), database_config)

    assert store.health_check() is False


def test_health_check_false_after_stop(db_path, database_config):
    store = ConversationSessionStore(SqliteClient(db_path), database_config)
    store.start()
    store.stop()

    assert store.health_check() is False


def test_record_and_get_recent_turns_round_trip(db_path, database_config):
    store = ConversationSessionStore(SqliteClient(db_path), database_config)
    store.start()
    try:
        turn = make_turn(user_text="hello", response_text="hi there")
        store.record_turn(turn)

        recent = store.get_recent_turns("session-1", limit=10)
    finally:
        store.stop()

    assert len(recent) == 1
    assert recent[0].user_text == "hello"
    assert recent[0].response_text == "hi there"
    assert recent[0].session_id == "session-1"
    assert recent[0].persona_name == "jarvis"


def test_get_recent_turns_returns_oldest_first_within_limit(db_path, database_config):
    store = ConversationSessionStore(SqliteClient(db_path), database_config)
    store.start()
    try:
        base = datetime.now(UTC) - timedelta(minutes=10)
        for i in range(3):
            store.record_turn(
                make_turn(user_text=f"turn-{i}", timestamp=base + timedelta(minutes=i))
            )

        recent = store.get_recent_turns("session-1", limit=2)
    finally:
        store.stop()

    # limit=2 keeps the two most recent (turn-1, turn-2), returned oldest-first.
    assert [t.user_text for t in recent] == ["turn-1", "turn-2"]


def test_get_recent_turns_only_returns_matching_session(db_path, database_config):
    store = ConversationSessionStore(SqliteClient(db_path), database_config)
    store.start()
    try:
        store.record_turn(make_turn(session_id="session-a", user_text="a-turn"))
        store.record_turn(make_turn(session_id="session-b", user_text="b-turn"))

        recent = store.get_recent_turns("session-a", limit=10)
    finally:
        store.stop()

    assert [t.user_text for t in recent] == ["a-turn"]


def test_turns_survive_a_simulated_restart(db_path, database_config):
    first_store = ConversationSessionStore(SqliteClient(db_path), database_config)
    first_store.start()
    first_store.record_turn(make_turn(user_text="before restart"))
    first_store.stop()

    # New SqliteClient + ConversationSessionStore instances, same file.
    second_store = ConversationSessionStore(SqliteClient(db_path), database_config)
    second_store.start()
    try:
        recent = second_store.get_recent_turns("session-1", limit=10)
    finally:
        second_store.stop()

    assert [t.user_text for t in recent] == ["before restart"]


class _RaisingSqliteClient:
    """Local double: connects/creates the table via a real SqliteClient,
    then fails every subsequent execute()/query() call — simulates a
    write or read failure (e.g. a locked/read-only or disconnected
    database) without needing to actually lock a file cross-platform.
    should_raise gates execute() (Sprint 2.7); should_raise_on_query
    gates query() separately (Sprint 2.13 hardening, scenario f) since a
    read failure and a write failure are independent, real scenarios."""

    def __init__(self, real_client: SqliteClient) -> None:
        self._real = real_client
        self.should_raise = False
        self.should_raise_on_query = False

    def connect(self) -> None:
        self._real.connect()

    def execute(self, sql: str, params: tuple = ()) -> None:
        if self.should_raise:
            raise RuntimeError("simulated write failure (locked/read-only database)")
        self._real.execute(sql, params)

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self.should_raise_on_query:
            raise RuntimeError("simulated read failure (disconnected database)")
        return self._real.query(sql, params)

    def close(self) -> None:
        self._real.close()


def test_record_turn_swallows_and_logs_a_write_failure(db_path, database_config):
    raising_client = _RaisingSqliteClient(SqliteClient(db_path))
    store = ConversationSessionStore(raising_client, database_config)
    store.start()
    try:
        raising_client.should_raise = True
        store.record_turn(make_turn())  # must not raise
        raising_client.should_raise = False
        remaining = store.get_recent_turns("session-1", limit=10)
    finally:
        store.stop()

    assert remaining == []


def test_get_recent_turns_swallows_and_logs_a_read_failure(db_path, database_config):
    """Sprint 2.13 hardening (scenario f): a read failure — not just a
    write failure — must also degrade gracefully to "no history
    available" rather than raising out to Context Manager (Sprint 2.8),
    which would otherwise abort the caller's entire turn."""
    raising_client = _RaisingSqliteClient(SqliteClient(db_path))
    store = ConversationSessionStore(raising_client, database_config)
    store.start()
    try:
        store.record_turn(make_turn())
        raising_client.should_raise_on_query = True

        recent = store.get_recent_turns("session-1", limit=10)  # must not raise
    finally:
        raising_client.should_raise_on_query = False
        store.stop()

    assert recent == []


def test_start_raises_conversation_store_error_on_connect_failure(database_config):
    class _AlwaysFailsToConnect:
        def connect(self):
            raise RuntimeError("disk unavailable")

    store = ConversationSessionStore(_AlwaysFailsToConnect(), database_config)

    with pytest.raises(ConversationStoreError):
        store.start()


def test_purge_older_than_removes_only_strictly_older_turns(db_path, database_config):
    store = ConversationSessionStore(SqliteClient(db_path), database_config)
    store.start()
    try:
        now = datetime.now(UTC)
        # Margins are minutes wide (not seconds) so this assertion is robust
        # against normal test-execution timing jitter, while still sitting
        # close to the 1-day boundary being tested.
        store.record_turn(make_turn(user_text="well-within", timestamp=now - timedelta(hours=12)))
        store.record_turn(
            make_turn(
                user_text="just-under",
                timestamp=now - timedelta(days=1) + timedelta(minutes=1),
            )
        )
        store.record_turn(
            make_turn(
                user_text="just-over",
                timestamp=now - timedelta(days=1) - timedelta(minutes=1),
            )
        )

        removed = store.purge_older_than(days=1)
        remaining = store.get_recent_turns("session-1", limit=10)
    finally:
        store.stop()

    assert removed == 1
    assert sorted(t.user_text for t in remaining) == ["just-under", "well-within"]


def test_purge_older_than_defaults_to_configured_retention(db_path):
    database_config = DatabaseConfig(sqlite_path=db_path, conversation_retention_days=1)
    store = ConversationSessionStore(SqliteClient(db_path), database_config)
    store.start()
    try:
        now = datetime.now(UTC)
        store.record_turn(
            make_turn(user_text="old", timestamp=now - timedelta(days=1) - timedelta(minutes=1))
        )

        removed = store.purge_older_than()  # no explicit days -> config default
    finally:
        store.stop()

    assert removed == 1


def test_purge_older_than_swallows_and_logs_a_failure(db_path, database_config):
    """Sprint 2.14 hardening (found during the Level 2 adversarial
    re-read): purge_older_than() had no failure handling at all, unlike
    record_turn()/get_recent_turns() — no live caller exists yet
    (backlog/technical_debt.md item 11), but a future one shouldn't
    inherit an unprotected failure path."""
    raising_client = _RaisingSqliteClient(SqliteClient(db_path))
    store = ConversationSessionStore(raising_client, database_config)
    store.start()
    try:
        raising_client.should_raise_on_query = True
        removed = store.purge_older_than(days=1)  # must not raise
    finally:
        raising_client.should_raise_on_query = False
        store.stop()

    assert removed == 0
