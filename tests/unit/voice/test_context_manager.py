"""Unit tests for voice.context_manager.

Uses a real ConversationSessionStore (backed by a real SQLite file under
tmp_path, per Sprint 2.7's own established pattern) rather than a fake —
ContextManager's whole job is aggregating exactly what the store returns,
so exercising the real store's bounded-window/ordering contract together
with ContextManager's own logic is the most faithful test of this
sprint's Acceptance Criteria ("reflects exactly... from the store").
"""

from datetime import UTC, datetime, timedelta

import pytest

from config.schema import DatabaseConfig
from database.sqlite_client import SqliteClient
from voice.context_manager import ContextManager
from voice.conversation_store import ConversationSessionStore, ConversationTurn


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "conversations.db")
    database_config = DatabaseConfig(sqlite_path=db_path)
    session_store = ConversationSessionStore(SqliteClient(db_path), database_config)
    session_store.start()
    yield session_store
    session_store.stop()


def record_turns(store, session_id, count, start=None):
    """Insert `count` turns for session_id, one minute apart, oldest first."""
    base = start if start is not None else datetime.now(UTC) - timedelta(minutes=count)
    for i in range(count):
        store.record_turn(
            ConversationTurn(
                session_id=session_id,
                persona_name="jarvis",
                timestamp=base + timedelta(minutes=i),
                user_text=f"user-{i}",
                response_text=f"reply-{i}",
            )
        )


def test_empty_session_returns_context_with_no_turns(store):
    manager = ContextManager(store)

    context = manager.current_context("session-1", "jarvis")

    assert context.session_id == "session-1"
    assert context.active_persona_name == "jarvis"
    assert context.recent_turns == []


def test_returns_bounded_window_oldest_first(store):
    record_turns(store, "session-1", count=8)
    manager = ContextManager(store, recent_turn_window=6)

    context = manager.current_context("session-1", "jarvis")

    assert [t.user_text for t in context.recent_turns] == [f"user-{i}" for i in range(2, 8)]


def test_recent_turn_window_boundary_exactly_at_limit(store):
    record_turns(store, "session-1", count=6)
    manager = ContextManager(store, recent_turn_window=6)

    context = manager.current_context("session-1", "jarvis")

    assert [t.user_text for t in context.recent_turns] == [f"user-{i}" for i in range(6)]


def test_recent_turn_window_boundary_one_over(store):
    record_turns(store, "session-1", count=7)
    manager = ContextManager(store, recent_turn_window=6)

    context = manager.current_context("session-1", "jarvis")

    assert len(context.recent_turns) == 6
    assert context.recent_turns[0].user_text == "user-1"  # oldest turn (user-0) dropped


def test_default_recent_turn_window_is_six(store):
    record_turns(store, "session-1", count=8)
    manager = ContextManager(store)

    context = manager.current_context("session-1", "jarvis")

    assert len(context.recent_turns) == 6


def test_only_returns_turns_for_the_requested_session(store):
    record_turns(store, "session-a", count=2)
    record_turns(store, "session-b", count=2)
    manager = ContextManager(store)

    context = manager.current_context("session-a", "jarvis")

    assert all(t.session_id == "session-a" for t in context.recent_turns)
    assert len(context.recent_turns) == 2


def test_timing_metadata_derived_from_recent_turns(store):
    base = datetime.now(UTC) - timedelta(minutes=10)
    record_turns(store, "session-1", count=3, start=base)
    manager = ContextManager(store)

    context = manager.current_context("session-1", "jarvis")

    assert context.session_started_at == base
    assert context.last_activity_at == base + timedelta(minutes=2)


def test_empty_session_timing_metadata_defaults_to_now(store):
    manager = ContextManager(store)

    before = datetime.now(UTC)
    context = manager.current_context("session-1", "jarvis")
    after = datetime.now(UTC)

    assert before <= context.session_started_at <= after
    assert before <= context.last_activity_at <= after


def test_calling_twice_with_unchanged_store_returns_equal_context(store):
    record_turns(store, "session-1", count=3)
    manager = ContextManager(store)

    first = manager.current_context("session-1", "jarvis")
    second = manager.current_context("session-1", "jarvis")

    assert first == second


def test_reflects_a_newly_recorded_turn_on_the_next_call(store):
    record_turns(store, "session-1", count=1)
    manager = ContextManager(store)
    first = manager.current_context("session-1", "jarvis")

    store.record_turn(
        ConversationTurn(
            session_id="session-1",
            persona_name="jarvis",
            timestamp=datetime.now(UTC),
            user_text="a brand new turn",
            response_text="a brand new reply",
        )
    )
    second = manager.current_context("session-1", "jarvis")

    assert len(first.recent_turns) == 1
    assert len(second.recent_turns) == 2
    assert second.recent_turns[-1].user_text == "a brand new turn"
