"""Unit tests for memory.chroma_client.

Uses a real chromadb.PersistentClient against a temp directory — the whole
point of this module is real semantic search, so it gets the same "no
mocking of the persistence path itself" treatment established for
SqliteClient/ConversationSessionStore (Sprint 2.7).
"""

import pytest

from config.schema import DatabaseConfig, MemoryConfig
from memory.chroma_client import ChromaMemoryClient
from memory.models import MemoryType


@pytest.fixture
def database_config(tmp_path):
    return DatabaseConfig(chroma_path=str(tmp_path / "chroma"))


@pytest.fixture
def memory_config():
    return MemoryConfig(chroma_collection_prefix="test_memory")


@pytest.fixture
def client(database_config, memory_config):
    c = ChromaMemoryClient(memory_config, database_config)
    c.connect()
    yield c
    c.close()


def test_ensure_collections_is_idempotent(client):
    client.ensure_collections()
    client.ensure_collections()  # must not raise or duplicate


def test_add_and_query_returns_nearest_first(client):
    client.add_embedding(
        MemoryType.SHARED, "rec-1", "the user's favorite programming language is Python"
    )
    client.add_embedding(MemoryType.SHARED, "rec-2", "the user drinks coffee every morning")

    results = client.query(
        MemoryType.SHARED, "what language does the user like to code in", n_results=2
    )

    assert len(results) == 2
    ids = [record_id for record_id, _distance in results]
    assert ids[0] == "rec-1"


def test_query_on_empty_collection_returns_empty_list(client):
    assert client.query(MemoryType.JARVIS, "anything", n_results=5) == []


def test_query_with_non_positive_n_results_returns_empty_list(client):
    client.add_embedding(MemoryType.SHARED, "rec-1", "some content")

    assert client.query(MemoryType.SHARED, "some content", n_results=0) == []


def test_collections_are_isolated_per_memory_type(client):
    client.add_embedding(MemoryType.JARVIS, "jarvis-rec", "technical project notes")

    assert client.query(MemoryType.MINIE, "technical project notes", n_results=5) == []


def test_delete_embedding_removes_it_from_results(client):
    client.add_embedding(MemoryType.SHARED, "rec-1", "delete me please")

    client.delete_embedding(MemoryType.SHARED, "rec-1")

    assert client.query(MemoryType.SHARED, "delete me please", n_results=5) == []


def test_health_check_false_before_connect(database_config, memory_config):
    disconnected = ChromaMemoryClient(memory_config, database_config)

    assert disconnected.health_check() is False


def test_health_check_true_after_connect(client):
    assert client.health_check() is True


def test_health_check_false_after_close(client):
    client.close()

    assert client.health_check() is False


def test_operations_before_connect_raise_runtime_error(database_config, memory_config):
    disconnected = ChromaMemoryClient(memory_config, database_config)

    with pytest.raises(RuntimeError):
        disconnected.ensure_collections()
