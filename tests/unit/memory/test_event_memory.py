"""Unit tests for memory.event_memory.

Uses a real MemoryStore (real temp-file SqliteClient + real temp-dir
ChromaMemoryClient), matching every other Sprint 3.1+ memory test's "real
save, real reload" convention.
"""

from datetime import UTC, datetime

import pytest

from config.schema import DatabaseConfig, MemoryConfig
from database.sqlite_client import SqliteClient
from memory.chroma_client import ChromaMemoryClient
from memory.event_memory import EventMemory
from memory.memory_store import MemoryStore
from memory.models import MemoryRecord, MemoryType


@pytest.fixture
def database_config(tmp_path):
    return DatabaseConfig(
        sqlite_path=str(tmp_path / "memory.db"), chroma_path=str(tmp_path / "chroma")
    )


@pytest.fixture
def memory_config():
    return MemoryConfig(chroma_collection_prefix="test_memory")


@pytest.fixture
def store(database_config, memory_config):
    sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)
    memory_store = MemoryStore(sqlite_client, chroma_client)
    memory_store.start()
    yield memory_store
    memory_store.stop()


@pytest.fixture
def event_memory(store):
    return EventMemory(store)


def test_record_milestone_always_sets_permanent_and_max_confidence(event_memory, store):
    record_id = event_memory.record_milestone("finished my degree", category="career")

    record = store.get_by_id(record_id)
    assert record.is_permanent is True
    assert record.confidence_score == 100.0
    assert record.memory_type == MemoryType.EVENT


def test_record_milestone_stores_occurred_at_separately_from_created_at(event_memory, store):
    occurred = datetime(2026, 5, 1, tzinfo=UTC)

    record_id = event_memory.record_milestone(
        "finished my degree", category="career", occurred_at=occurred
    )

    record = store.get_by_id(record_id)
    assert record.occurred_at == occurred
    assert record.created_at != occurred


def test_record_milestone_occurred_at_defaults_to_none(event_memory, store):
    record_id = event_memory.record_milestone("shipped a project", category="project")

    record = store.get_by_id(record_id)
    assert record.occurred_at is None


def test_list_milestones_unfiltered_returns_all(event_memory):
    event_memory.record_milestone("finished my degree", category="career")
    event_memory.record_milestone("shipped JARMINEI v1.0", category="project")

    results = event_memory.list_milestones()

    assert len(results) == 2


def test_list_milestones_filters_by_category(event_memory):
    event_memory.record_milestone("finished my degree", category="career")
    event_memory.record_milestone("shipped JARMINEI v1.0", category="project")

    results = event_memory.list_milestones(category="career")

    assert len(results) == 1
    assert results[0].content == "finished my degree"


def test_list_milestones_only_returns_event_records(event_memory, store):
    event_memory.record_milestone("a real milestone", category="career")
    store.store(MemoryRecord(memory_type=MemoryType.SHARED, content="not a milestone"))

    results = event_memory.list_milestones()

    assert all(record.memory_type == MemoryType.EVENT for record in results)


def test_search_milestones_scoped_to_event_only(event_memory, store):
    event_memory.record_milestone("finished my computer science degree", category="career")
    store.store(
        MemoryRecord(
            memory_type=MemoryType.SHARED, content="finished my computer science degree"
        )
    )

    results = event_memory.search_milestones("computer science degree", n_results=5)

    assert all(record.memory_type == MemoryType.EVENT for record in results)
    assert len(results) == 1


def test_search_milestones_scored_keeps_distance(event_memory):
    """Sprint 3.9 addition: search_milestones_scored() must expose each
    result's Chroma distance (search_milestones() itself still discards
    it — see this method's own docstring)."""
    event_memory.record_milestone("finished my computer science degree", category="career")

    results = event_memory.search_milestones_scored("computer science degree", n_results=5)

    assert len(results) == 1
    record, distance = results[0]
    assert record.memory_type == MemoryType.EVENT
    assert isinstance(distance, float)


def test_event_memory_has_no_deletion_method():
    """Defensive check against a bug class: EventMemory must never grow a
    convenience method that makes deleting a permanent milestone look
    routine — only MemoryStore.delete() (Sprint 3.1) may do that, and
    nothing in Level 3 calls it."""
    for forbidden in ("delete", "forget", "expire", "remove"):
        assert not hasattr(EventMemory, forbidden)
