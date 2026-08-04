"""Unit tests for learning.preference_learner.

Real SqliteClient (temp file) + real ChromaMemoryClient (temp directory)
for MemoryStore — mirrors tests/unit/memory/test_emotional_memory.py's
own "real save, real reload" precedent, since detect_conversation_style()'s
whole point is a real count over real persisted memory records.
PatternStore is likewise real (a separate temp-file SQLite database),
since this file also verifies detect_conversation_style() genuinely
upserts into it.
"""

import pytest

from config.schema import DatabaseConfig, LearningConfig, MemoryConfig
from database.sqlite_client import SqliteClient
from learning.pattern_model import PatternType
from learning.pattern_store import PatternStore
from learning.preference_learner import PreferenceLearner
from memory.chroma_client import ChromaMemoryClient
from memory.memory_store import MemoryStore
from memory.models import MemoryRecord, MemoryType


@pytest.fixture
def memory_store(tmp_path):
    database_config = DatabaseConfig(
        sqlite_path=str(tmp_path / "memory.db"), chroma_path=str(tmp_path / "chroma")
    )
    memory_config = MemoryConfig(chroma_collection_prefix="test_preference_learner")
    sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)
    store = MemoryStore(sqlite_client, chroma_client)
    store.start()
    yield store
    store.stop()


@pytest.fixture
def pattern_store(tmp_path):
    client = SqliteClient(str(tmp_path / "patterns.db"))
    store = PatternStore(client)
    store.start()
    yield store
    store.stop()


def _store_records(memory_store: MemoryStore, memory_type: MemoryType, count: int) -> None:
    for i in range(count):
        memory_store.store(MemoryRecord(memory_type=memory_type, content=f"content {i}"))


def _learner(memory_store, pattern_store, **config_overrides) -> PreferenceLearner:
    return PreferenceLearner(memory_store, pattern_store, LearningConfig(**config_overrides))


# --- gating on conversation_style_min_records -----------------------------------------------


def test_detect_conversation_style_returns_none_below_the_gate(memory_store, pattern_store):
    _store_records(memory_store, MemoryType.JARVIS, 4)
    _store_records(memory_store, MemoryType.MINIE, 4)
    learner = _learner(memory_store, pattern_store, conversation_style_min_records=10)

    assert learner.detect_conversation_style() is None
    assert pattern_store.list_all() == []


def test_detect_conversation_style_produces_a_pattern_at_the_gate(memory_store, pattern_store):
    _store_records(memory_store, MemoryType.JARVIS, 6)
    _store_records(memory_store, MemoryType.MINIE, 4)
    learner = _learner(memory_store, pattern_store, conversation_style_min_records=10)

    pattern = learner.detect_conversation_style()

    assert pattern is not None
    assert pattern.pattern_type is PatternType.CONVERSATION_STYLE


# --- SHARED exclusion -------------------------------------------------------------------------


def test_detect_conversation_style_excludes_shared_records_from_the_gate_and_the_count(
    memory_store, pattern_store
):
    _store_records(memory_store, MemoryType.SHARED, 50)
    _store_records(memory_store, MemoryType.JARVIS, 4)
    _store_records(memory_store, MemoryType.MINIE, 4)
    learner = _learner(memory_store, pattern_store, conversation_style_min_records=10)

    assert learner.detect_conversation_style() is None


def test_detect_conversation_style_shared_records_never_influence_the_subject(
    memory_store, pattern_store
):
    _store_records(memory_store, MemoryType.SHARED, 100)
    _store_records(memory_store, MemoryType.JARVIS, 8)
    _store_records(memory_store, MemoryType.MINIE, 2)
    learner = _learner(memory_store, pattern_store, conversation_style_min_records=10)

    pattern = learner.detect_conversation_style()

    assert pattern.subject == "jarvis"
    assert pattern.evidence_count == 10


# --- subject/confidence scaling ----------------------------------------------------------------


def test_detect_conversation_style_subject_is_the_majority_persona(memory_store, pattern_store):
    _store_records(memory_store, MemoryType.JARVIS, 2)
    _store_records(memory_store, MemoryType.MINIE, 8)
    learner = _learner(memory_store, pattern_store, conversation_style_min_records=10)

    pattern = learner.detect_conversation_style()

    assert pattern.subject == "minie"


def test_detect_conversation_style_confidence_is_low_for_a_near_even_split(
    memory_store, pattern_store
):
    _store_records(memory_store, MemoryType.JARVIS, 5)
    _store_records(memory_store, MemoryType.MINIE, 5)
    learner = _learner(memory_store, pattern_store, conversation_style_min_records=10)

    pattern = learner.detect_conversation_style()

    assert pattern.confidence == pytest.approx(0.0)


def test_detect_conversation_style_confidence_is_high_for_a_lopsided_split(
    memory_store, pattern_store
):
    _store_records(memory_store, MemoryType.JARVIS, 10)
    _store_records(memory_store, MemoryType.MINIE, 0)
    learner = _learner(memory_store, pattern_store, conversation_style_min_records=10)

    pattern = learner.detect_conversation_style()

    assert pattern.confidence == pytest.approx(1.0)


# --- upsert into PatternStore -------------------------------------------------------------------


def test_detect_conversation_style_upserts_into_pattern_store(memory_store, pattern_store):
    _store_records(memory_store, MemoryType.JARVIS, 7)
    _store_records(memory_store, MemoryType.MINIE, 3)
    learner = _learner(memory_store, pattern_store, conversation_style_min_records=10)

    learner.detect_conversation_style()

    stored = pattern_store.list_by_type(PatternType.CONVERSATION_STYLE)
    assert len(stored) == 1
    assert stored[0].subject == "jarvis"


def test_detect_conversation_style_re_running_does_not_duplicate_rows(memory_store, pattern_store):
    _store_records(memory_store, MemoryType.JARVIS, 7)
    _store_records(memory_store, MemoryType.MINIE, 3)
    learner = _learner(memory_store, pattern_store, conversation_style_min_records=10)

    learner.detect_conversation_style()
    learner.detect_conversation_style()

    assert len(pattern_store.list_all()) == 1
