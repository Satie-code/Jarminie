"""Unit tests for memory.short_term_memory.

Uses a real MemoryStore (real temp-file SqliteClient + real temp-dir
ChromaMemoryClient), matching every other Sprint 3.1+ memory test's "real
save, real reload" convention.
"""

from datetime import UTC, datetime

import pytest

from config.schema import DatabaseConfig, MemoryConfig
from database.sqlite_client import SqliteClient
from memory.chroma_client import ChromaMemoryClient
from memory.memory_store import MemoryStore
from memory.models import MemoryType
from memory.short_term_memory import ShortTermMemory
from voice.conversation_store import ConversationTurn


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
def short_term_memory(store, memory_config):
    return ShortTermMemory(store, memory_config)


def make_turn(session_id="session-1", user_text="hello there", **overrides):
    defaults = dict(
        session_id=session_id,
        persona_name="jarvis",
        timestamp=datetime.now(UTC),
        user_text=user_text,
        response_text="a reply",
    )
    defaults.update(overrides)
    return ConversationTurn(**defaults)


def test_promote_from_turn_matches_trigger_and_creates_record(short_term_memory, store):
    turn = make_turn(user_text="don't forget I have a dentist appointment Friday")

    record_id = short_term_memory.promote_from_turn(turn)

    assert record_id is not None
    record = store.get_by_id(record_id)
    assert record.memory_type == MemoryType.SHORT_TERM
    assert record.confidence_score == 15.0
    assert record.source_session_id == "session-1"
    assert record.content == turn.user_text


def test_promote_from_turn_match_is_case_insensitive(short_term_memory):
    turn = make_turn(user_text="REMIND ME to call the dentist")

    record_id = short_term_memory.promote_from_turn(turn)

    assert record_id is not None


def test_promote_from_turn_no_match_returns_none_and_creates_nothing(short_term_memory, store):
    turn = make_turn(user_text="what's the weather like today")

    record_id = short_term_memory.promote_from_turn(turn)

    assert record_id is None
    assert store.recent(MemoryType.SHORT_TERM, limit=10) == []


def test_active_context_memories_scoped_to_session(short_term_memory):
    short_term_memory.promote_from_turn(
        make_turn(session_id="session-a", user_text="remember that the meeting is at 3pm")
    )
    short_term_memory.promote_from_turn(
        make_turn(session_id="session-b", user_text="note that the report is due Monday")
    )

    session_a_memories = short_term_memory.active_context_memories("session-a")

    assert len(session_a_memories) == 1
    assert session_a_memories[0].source_session_id == "session-a"


def test_active_context_memories_empty_for_unknown_session(short_term_memory):
    assert short_term_memory.active_context_memories("no-such-session") == []


def test_default_memory_config_salience_triggers_and_confidence():
    config = MemoryConfig()
    assert config.short_term_default_confidence == 15.0
    assert "remind me" in config.short_term_salience_triggers
