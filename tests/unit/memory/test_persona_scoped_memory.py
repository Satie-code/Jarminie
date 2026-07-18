"""Unit tests for memory.persona_scoped_memory.

Uses a real MemoryStore (real temp-file SqliteClient + real temp-dir
ChromaMemoryClient) — this module's whole point is the read-scoping
guarantee built on top of MemoryStore's real semantic search, so the
"real save, real reload" convention established since Sprint 2.7 applies
here too.
"""

import pytest

from config.schema import DatabaseConfig, MemoryConfig
from database.sqlite_client import SqliteClient
from memory.chroma_client import ChromaMemoryClient
from memory.memory_store import MemoryStore
from memory.models import MemoryRecord, MemoryType
from memory.persona_scoped_memory import PersonaScopedMemory, _merge_by_distance


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
def persona_memory(store):
    return PersonaScopedMemory(store)


def test_remember_accepts_shared_jarvis_and_minie(persona_memory):
    for owner in (MemoryType.SHARED, MemoryType.JARVIS, MemoryType.MINIE):
        record_id = persona_memory.remember(owner, f"content for {owner.value}")
        assert record_id


@pytest.mark.parametrize("owner", [MemoryType.EVENT, MemoryType.SHORT_TERM])
def test_remember_rejects_event_and_short_term(persona_memory, owner):
    with pytest.raises(ValueError, match="remember"):
        persona_memory.remember(owner, "should not be allowed")


def test_recall_for_persona_rejects_unknown_persona_name(persona_memory):
    with pytest.raises(ValueError, match="recall_for_persona"):
        persona_memory.recall_for_persona("not-a-real-persona", "query")


def test_jarvis_recall_never_returns_minie_only_content(persona_memory):
    persona_memory.remember(MemoryType.MINIE, "casual chat about favorite movies")
    persona_memory.remember(MemoryType.JARVIS, "refactoring the authentication module")

    results = persona_memory.recall_for_persona("jarvis", "favorite movies", n_results=10)

    assert all(r.memory_type != MemoryType.MINIE for r in results)


def test_minie_recall_never_returns_jarvis_only_content(persona_memory):
    persona_memory.remember(MemoryType.JARVIS, "refactoring the authentication module")
    persona_memory.remember(MemoryType.MINIE, "casual chat about favorite movies")

    results = persona_memory.recall_for_persona("minie", "authentication module", n_results=10)

    assert all(r.memory_type != MemoryType.JARVIS for r in results)


def test_shared_memory_visible_to_both_personas(persona_memory):
    persona_memory.remember(MemoryType.SHARED, "the user's long-term goal is to launch JARMINEI")

    jarvis_results = persona_memory.recall_for_persona("jarvis", "long-term goal", n_results=5)
    minie_results = persona_memory.recall_for_persona("minie", "long-term goal", n_results=5)

    assert any(r.memory_type == MemoryType.SHARED for r in jarvis_results)
    assert any(r.memory_type == MemoryType.SHARED for r in minie_results)


def test_recall_for_persona_respects_n_results(persona_memory):
    for i in range(5):
        persona_memory.remember(MemoryType.SHARED, f"shared fact number {i}")
    for i in range(5):
        persona_memory.remember(MemoryType.JARVIS, f"jarvis fact number {i}")

    results = persona_memory.recall_for_persona("jarvis", "fact number", n_results=3)

    assert len(results) == 3


def test_merge_by_distance_genuinely_sorts_across_both_sources():
    """Deterministic proof that the merge is a real distance sort, not an
    interleave — decoupled from the real embedding model's nondeterminism
    by using synthetic (record, distance) pairs with fully controlled
    values. A shared-source result with worse (higher) distance than a
    persona-source result must end up ranked AFTER it, even though
    interleaving would have placed the shared-source result first."""
    close_persona = MemoryRecord(memory_type=MemoryType.JARVIS, content="close persona match")
    far_shared = MemoryRecord(memory_type=MemoryType.SHARED, content="far shared match")
    closer_shared = MemoryRecord(memory_type=MemoryType.SHARED, content="closer shared match")

    shared_results = [(closer_shared, 0.1), (far_shared, 0.9)]
    persona_results = [(close_persona, 0.5)]

    merged = _merge_by_distance(shared_results, persona_results)

    assert [record.content for record in merged] == [
        "closer shared match",
        "close persona match",
        "far shared match",
    ]


def test_recall_for_persona_scored_keeps_distance(persona_memory):
    """Sprint 3.9 addition: recall_for_persona_scored() must expose each
    result's Chroma distance (recall_for_persona() itself still discards
    it — see this method's own docstring)."""
    persona_memory.remember(MemoryType.JARVIS, "refactoring the authentication module")

    results = persona_memory.recall_for_persona_scored("jarvis", "authentication module")

    assert len(results) == 1
    record, distance = results[0]
    assert record.memory_type == MemoryType.JARVIS
    assert isinstance(distance, float)


def test_recall_for_persona_and_scored_variant_return_the_same_record_ids(persona_memory):
    """Each call independently bumps access_count via MemoryStore.
    get_by_id() (a real, working-as-designed read signal for Sprint 3.5's
    Dynamic Memory Formula), so full record equality isn't meaningful
    across two separate calls — comparing ids proves the same underlying
    records were found regardless.

    Compared as sets, not ordered lists: two independent real Chroma
    queries (one per call) use an approximate-nearest-neighbor index
    (HNSW), which is not guaranteed to return near-tied distances in a
    strictly identical order across repeated queries — observed as a
    rare, real flake in this exact test before switching to set
    comparison. The property this test actually needs (the scored
    variant finds the same records as the unscored one) doesn't depend
    on cross-call order stability; only a single call's own internal
    ordering does, which _merge_by_distance_scored()'s own dedicated
    test already covers deterministically with synthetic distances."""
    persona_memory.remember(MemoryType.SHARED, "shared fact one")
    persona_memory.remember(MemoryType.JARVIS, "jarvis-only fact")

    plain = persona_memory.recall_for_persona("jarvis", "fact", n_results=10)
    scored = persona_memory.recall_for_persona_scored("jarvis", "fact", n_results=10)

    assert {record.id for record in plain} == {record.id for record, _distance in scored}


def test_recall_shared_only_never_includes_persona_specific_content(persona_memory):
    persona_memory.remember(MemoryType.JARVIS, "a jarvis-only technical note")
    persona_memory.remember(MemoryType.SHARED, "a shared project note")

    results = persona_memory.recall_shared_only("note", n_results=10)

    assert all(r.memory_type == MemoryType.SHARED for r in results)
    assert any("shared project" in r.content for r in results)
