"""Unit tests for memory.memory_store.

Real SqliteClient (temp file) + real ChromaMemoryClient (temp directory) for
every persistence-focused test — this module's whole point is dual-backend
persistence, so it gets the same "real save, real reload" treatment as
ConversationSessionStore (Sprint 2.7). A small local double covers the one
failure-injection scenario (a Chroma write failure) a real client can't
easily simulate, matching that same sprint's established pattern.
"""

from datetime import UTC, datetime, timedelta

import pytest

from config.schema import DatabaseConfig, MemoryConfig
from database.sqlite_client import SqliteClient
from memory.chroma_client import ChromaMemoryClient
from memory.errors import MemoryStoreError
from memory.memory_store import MemoryStore
from memory.models import MemoryRecord, MemoryType


class _EmbeddingFailingChromaClient(ChromaMemoryClient):
    """A real ChromaMemoryClient whose add_embedding() always fails —
    everything else (connect/query/delete/health_check) behaves normally."""

    def add_embedding(self, memory_type, record_id, content) -> None:
        raise RuntimeError("chroma exploded")


class _RaisingSqliteClient(SqliteClient):
    """Sprint 3.14 hardening: a real SqliteClient whose execute()/query()
    can be switched to fail on demand, after connect()/start() have
    already succeeded — matching the project's established "_Raising*-
    style local test double" pattern (per sprint_3_13.md's own Potential
    Risks). Flags are plain mutable attributes rather than constructor
    args specifically so a test can call store.start() (which itself
    calls execute() for CREATE TABLE) before switching failure on."""

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.raise_on_execute = False
        self.raise_on_query = False

    def execute(self, sql: str, params: tuple = ()) -> None:
        if self.raise_on_execute:
            raise RuntimeError("sqlite execute exploded")
        super().execute(sql, params)

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self.raise_on_query:
            raise RuntimeError("sqlite query exploded")
        return super().query(sql, params)


class _QueryFailingChromaClient(ChromaMemoryClient):
    """Sprint 3.13 hardening (scenario b): a real ChromaMemoryClient whose
    query() always fails — simulates ChromaDB being entirely unreachable
    or corrupted for the read/search path specifically, distinct from
    _EmbeddingFailingChromaClient's write-path failure above."""

    def query(self, memory_type, query_text, n_results):
        raise RuntimeError("chroma query exploded")


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "memory.db")


@pytest.fixture
def chroma_path(tmp_path):
    return str(tmp_path / "chroma")


@pytest.fixture
def database_config(db_path, chroma_path):
    return DatabaseConfig(sqlite_path=db_path, chroma_path=chroma_path)


@pytest.fixture
def memory_config():
    return MemoryConfig(chroma_collection_prefix="test_memory")


def make_store(database_config, memory_config, chroma_client_cls=ChromaMemoryClient):
    sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = chroma_client_cls(memory_config, database_config)
    return MemoryStore(sqlite_client, chroma_client)


def make_record(**overrides):
    defaults = dict(
        memory_type=MemoryType.SHARED,
        content="the user's favorite project is JARMINEI",
        category="project",
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)


def test_starting_creates_table_and_collections_and_store_is_healthy(
    database_config, memory_config
):
    store = make_store(database_config, memory_config)

    store.start()
    try:
        assert store.health_check() is True
    finally:
        store.stop()


def test_starting_is_idempotent(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        now = datetime.now(UTC).isoformat()
        store._sqlite_client.execute(
            "INSERT INTO memory_records "
            "(id, memory_type, content, category, confidence_score, is_permanent, "
            "user_override, source_session_id, created_at, last_accessed_at, "
            "band_entered_at, access_count) "
            "VALUES ('probe', 'shared', 'x', NULL, 0.0, 0, 0, NULL, ?, ?, ?, 0)",
            (now, now, now),
        )
        store.start()  # must not raise or drop the table
        assert store.get_by_id("probe") is not None
    finally:
        store.stop()


def test_health_check_false_before_start(database_config, memory_config):
    store = make_store(database_config, memory_config)

    assert store.health_check() is False


def test_store_and_get_by_id_round_trip(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        record = make_record()
        record_id = store.store(record)

        fetched = store.get_by_id(record_id)
    finally:
        store.stop()

    assert fetched is not None
    assert fetched.content == record.content
    assert fetched.memory_type == MemoryType.SHARED
    assert fetched.category == "project"


def test_records_survive_a_simulated_restart(database_config, memory_config):
    first = make_store(database_config, memory_config)
    first.start()
    record_id = first.store(make_record())
    first.stop()

    second = make_store(database_config, memory_config)
    second.start()
    try:
        fetched = second.get_by_id(record_id)
    finally:
        second.stop()

    assert fetched is not None
    assert fetched.id == record_id


def test_occurred_at_round_trips_when_set(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        occurred = datetime(2026, 6, 1, tzinfo=UTC)
        record_id = store.store(make_record(occurred_at=occurred))

        fetched = store.get_by_id(record_id)
    finally:
        store.stop()

    assert fetched.occurred_at == occurred


def test_occurred_at_defaults_to_none(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        record_id = store.store(make_record())

        fetched = store.get_by_id(record_id)
    finally:
        store.stop()

    assert fetched.occurred_at is None


def test_get_by_id_returns_none_for_unknown_id(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        assert store.get_by_id("does-not-exist") is None
    finally:
        store.stop()


def test_get_by_id_bumps_access_count_and_last_accessed_at(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        record_id = store.store(make_record())

        first_read = store.get_by_id(record_id)
        second_read = store.get_by_id(record_id)
    finally:
        store.stop()

    assert first_read.access_count == 1
    assert second_read.access_count == 2
    assert second_read.last_accessed_at >= first_read.last_accessed_at


def test_recent_returns_newest_first_scoped_to_memory_type(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        older = make_record(
            memory_type=MemoryType.EVENT,
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
        newer = make_record(memory_type=MemoryType.EVENT)
        store.store(older)
        store.store(newer)
        store.store(make_record(memory_type=MemoryType.SHARED))  # different type

        results = store.recent(MemoryType.EVENT, limit=10)
    finally:
        store.stop()

    assert [r.memory_type for r in results] == [MemoryType.EVENT, MemoryType.EVENT]
    assert results[0].id == newer.id


def test_recent_respects_limit(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        for _ in range(3):
            store.store(make_record(memory_type=MemoryType.EVENT))

        results = store.recent(MemoryType.EVENT, limit=2)
    finally:
        store.stop()

    assert len(results) == 2


def test_semantic_search_ranks_relevant_content_first(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        store.store(
            make_record(content="the user's favorite programming language is Python")
        )
        store.store(make_record(content="the user drinks coffee every morning"))

        results = store.semantic_search(
            MemoryType.SHARED, "what language does the user like to code in", n_results=2
        )
    finally:
        store.stop()

    assert len(results) == 2
    top_record, top_distance = results[0]
    assert "Python" in top_record.content
    assert isinstance(top_distance, float)
    # results are sorted nearest-first (ascending distance)
    assert results[0][1] <= results[1][1]


def test_semantic_search_on_empty_store_returns_empty_list(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        results = store.semantic_search(MemoryType.SHARED, "anything", n_results=5)
    finally:
        store.stop()

    assert results == []


def test_update_confidence_persists_new_score(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        record_id = store.store(make_record())

        store.update_confidence(record_id, 85.0)

        fetched = store.get_by_id(record_id)
    finally:
        store.stop()

    assert fetched.confidence_score == 85.0
    assert fetched.user_override is False


def test_update_confidence_can_also_set_user_override(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        record_id = store.store(make_record())

        store.update_confidence(record_id, 100.0, user_override=True)

        fetched = store.get_by_id(record_id)
    finally:
        store.stop()

    assert fetched.confidence_score == 100.0
    assert fetched.user_override is True


def test_delete_removes_from_sqlite_and_chroma(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        record_id = store.store(make_record(content="delete me please"))

        store.delete(record_id)

        assert store.get_by_id(record_id) is None
        assert store.semantic_search(MemoryType.SHARED, "delete me please", n_results=5) == []
    finally:
        store.stop()


def test_delete_of_unknown_id_does_not_raise(database_config, memory_config):
    store = make_store(database_config, memory_config)
    store.start()
    try:
        store.delete("does-not-exist")  # must not raise
    finally:
        store.stop()


def test_store_swallows_and_logs_a_chroma_embedding_failure(database_config, memory_config):
    store = make_store(
        database_config, memory_config, chroma_client_cls=_EmbeddingFailingChromaClient
    )
    store.start()
    try:
        record_id = store.store(make_record())  # must not raise

        fetched = store.get_by_id(record_id)
    finally:
        store.stop()

    assert fetched is not None
    assert fetched.content == "the user's favorite project is JARMINEI"


def test_semantic_search_returns_empty_list_on_a_chroma_query_failure(
    database_config, memory_config
):
    """Sprint 3.13 hardening (scenario b): a degraded/unreachable Chroma
    backend must not raise out of semantic_search() — an empty result is
    a normal "nothing relevant found" outcome to every caller (Persona
    ScopedMemory, EventMemory, MemoryRetrievalEngine), not a
    distinguishable error state, per the Fail Gracefully Rule."""
    store = make_store(database_config, memory_config, chroma_client_cls=_QueryFailingChromaClient)
    store.start()
    try:
        store.store(make_record())  # SQLite write still succeeds

        results = store.semantic_search(MemoryType.SHARED, "anything", n_results=5)
    finally:
        store.stop()

    assert results == []


# --- Sprint 3.14 hardening: SQLite failure handling (adversarial re-read) ---
# Every SQLite operation below previously had no failure handling at all,
# unlike this class's own Chroma-failure handling (Sprint 3.1/3.13) and its
# Level 2 sibling ConversationSessionStore's SQLite handling (Sprint 2.13).


def _make_raising_store(database_config, memory_config):
    sqlite_client = _RaisingSqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)
    store = MemoryStore(sqlite_client, chroma_client)
    store.start()  # succeeds — failure is switched on only afterward
    return store, sqlite_client


def test_store_raises_memory_store_error_on_a_sqlite_write_failure(
    database_config, memory_config
):
    store, sqlite_client = _make_raising_store(database_config, memory_config)
    try:
        sqlite_client.raise_on_execute = True

        with pytest.raises(MemoryStoreError, match="Failed to store"):
            store.store(make_record())
    finally:
        sqlite_client.raise_on_execute = False
        store.stop()


def test_get_by_id_returns_none_on_a_sqlite_read_failure(database_config, memory_config):
    store, sqlite_client = _make_raising_store(database_config, memory_config)
    try:
        record_id = store.store(make_record())
        sqlite_client.raise_on_query = True

        assert store.get_by_id(record_id) is None
    finally:
        sqlite_client.raise_on_query = False
        store.stop()


def test_recent_returns_empty_list_on_a_sqlite_read_failure(database_config, memory_config):
    store, sqlite_client = _make_raising_store(database_config, memory_config)
    try:
        store.store(make_record(memory_type=MemoryType.EVENT))
        sqlite_client.raise_on_query = True

        assert store.recent(MemoryType.EVENT, limit=10) == []
    finally:
        sqlite_client.raise_on_query = False
        store.stop()


def test_update_confidence_swallows_a_sqlite_write_failure(database_config, memory_config):
    store, sqlite_client = _make_raising_store(database_config, memory_config)
    try:
        record_id = store.store(make_record())
        sqlite_client.raise_on_execute = True

        store.update_confidence(record_id, 90.0)  # must not raise
    finally:
        sqlite_client.raise_on_execute = False
        store.stop()


def test_delete_swallows_a_sqlite_failure(database_config, memory_config):
    store, sqlite_client = _make_raising_store(database_config, memory_config)
    try:
        record_id = store.store(make_record())
        sqlite_client.raise_on_query = True

        store.delete(record_id)  # must not raise
    finally:
        sqlite_client.raise_on_query = False
        store.stop()
