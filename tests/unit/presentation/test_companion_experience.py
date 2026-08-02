"""Unit tests for presentation.companion_experience (Sprint 5.13).

Real SqliteClient (temp file) + real ChromaMemoryClient (temp directory)
backing real EmotionalMemory/EventMemory instances — mirrors
test_emotional_memory.py's/test_event_memory.py's own "real save, real
reload" precedent, since this module's whole point is reading real
persisted memory.
"""

from datetime import UTC, datetime, timedelta

import pytest

from config.schema import DatabaseConfig, MemoryConfig, PresentationConfig
from database.sqlite_client import SqliteClient
from emotion.state_manager import EmotionalState
from memory.chroma_client import ChromaMemoryClient
from memory.emotional_memory import EmotionalMemory
from memory.event_memory import EventMemory
from memory.memory_store import MemoryStore
from memory.models import MemoryType
from presentation.companion_experience import (
    CompanionExperienceEngine,
    CompanionMomentType,
)


def _state_with_significance(value: float) -> EmotionalState:
    """abs(stress - 50) / 50 == value for value in [0.0, 1.0] — the same
    _score_significance() formula memory/emotional_memory.py itself
    uses, driven purely through stress to keep this deterministic."""
    return EmotionalState(stress=50.0 + 50.0 * value)


@pytest.fixture
def database_config(tmp_path):
    return DatabaseConfig(
        sqlite_path=str(tmp_path / "memory.db"), chroma_path=str(tmp_path / "chroma")
    )


@pytest.fixture
def memory_config():
    return MemoryConfig(chroma_collection_prefix="test_companion_experience")


@pytest.fixture
def store(database_config, memory_config):
    sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)
    memory_store = MemoryStore(sqlite_client, chroma_client)
    memory_store.start()
    yield memory_store
    memory_store.stop()


@pytest.fixture
def emotional_memory(store, memory_config) -> EmotionalMemory:
    return EmotionalMemory(store, memory_config)


@pytest.fixture
def event_memory(store) -> EventMemory:
    return EventMemory(store)


@pytest.fixture
def config() -> PresentationConfig:
    return PresentationConfig(
        greeting_idle_threshold_seconds=3600.0, celebration_significance_threshold=0.75
    )


@pytest.fixture
def engine(emotional_memory, event_memory, config) -> CompanionExperienceEngine:
    return CompanionExperienceEngine(emotional_memory, event_memory, config)


# --- never raises, including when both stores are empty (Acceptance Criteria) -


def test_check_for_greeting_never_raises_when_everything_is_empty(engine):
    engine.check_for_greeting(10000.0)  # must not raise


def test_check_for_celebration_never_raises_when_everything_is_empty(engine):
    engine.check_for_celebration()  # must not raise


def test_check_for_continuity_callback_never_raises_when_everything_is_empty(engine):
    engine.check_for_continuity_callback()  # must not raise


def test_check_for_celebration_returns_none_when_everything_is_empty(engine):
    assert engine.check_for_celebration() is None


def test_check_for_continuity_callback_returns_none_when_everything_is_empty(engine):
    assert engine.check_for_continuity_callback() is None


# --- check_for_greeting() threshold behavior (Acceptance Criteria) -----------


def test_check_for_greeting_below_threshold_returns_none(engine):
    assert engine.check_for_greeting(3599.0) is None


def test_check_for_greeting_at_threshold_fires(engine):
    assert engine.check_for_greeting(3600.0) is not None


def test_check_for_greeting_above_threshold_fires(engine):
    moment = engine.check_for_greeting(7200.0)
    assert moment is not None
    assert moment.moment_type is CompanionMomentType.GREETING


def test_check_for_greeting_with_nothing_to_reference_has_no_content(engine):
    moment = engine.check_for_greeting(7200.0)
    assert moment.referenced_content is None
    assert moment.referenced_at is None


# --- combined greeting + continuity callback (Acceptance Criteria) -----------


def test_check_for_greeting_folds_in_a_continuity_callback_when_one_exists(
    engine, emotional_memory
):
    emotional_memory.record_significant_moment(
        "started a new job", MemoryType.SHARED, "career", _state_with_significance(0.65)
    )

    moment = engine.check_for_greeting(7200.0)

    assert moment is not None
    assert moment.moment_type is CompanionMomentType.GREETING
    assert moment.referenced_content == "started a new job"
    assert moment.referenced_at is not None


def test_greeting_with_continuity_never_produces_two_separate_moments(engine, emotional_memory):
    """The exact Acceptance Criteria scenario: a single call to
    check_for_greeting() returns exactly one CompanionMoment, not a
    GREETING plus a separate CONTINUITY_CALLBACK."""
    emotional_memory.record_significant_moment(
        "adopted a puppy", MemoryType.SHARED, "life", _state_with_significance(0.7)
    )

    moment = engine.check_for_greeting(7200.0)

    assert moment.moment_type is CompanionMomentType.GREETING
    assert moment.referenced_content == "adopted a puppy"


# --- check_for_celebration() threshold behavior (Testing Checklist) ----------


def test_celebration_below_threshold_returns_none(engine, emotional_memory):
    emotional_memory.record_significant_moment(
        "a mildly nice day", MemoryType.SHARED, "general", _state_with_significance(0.5)
    )
    assert engine.check_for_celebration() is None


def test_celebration_at_threshold_fires(engine, emotional_memory):
    emotional_memory.record_significant_moment(
        "passed the certification exam", MemoryType.SHARED, "career", _state_with_significance(0.75)
    )
    moment = engine.check_for_celebration()
    assert moment is not None
    assert moment.moment_type is CompanionMomentType.CELEBRATION
    assert moment.referenced_content == "passed the certification exam"


def test_celebration_above_threshold_fires(engine, emotional_memory):
    emotional_memory.record_significant_moment(
        "got the promotion", MemoryType.SHARED, "career", _state_with_significance(0.95)
    )
    moment = engine.check_for_celebration()
    assert moment is not None
    assert moment.referenced_content == "got the promotion"


def test_celebration_from_event_memory_milestone(engine, event_memory):
    event_memory.record_milestone("graduated college", "milestone")

    moment = engine.check_for_celebration()

    assert moment is not None
    assert moment.moment_type is CompanionMomentType.CELEBRATION
    assert moment.referenced_content == "graduated college"


# --- EmotionalMemory vs EventMemory preference ordering (Testing Checklist) --


def test_celebration_prefers_the_more_recent_of_emotional_and_event_memory(
    engine, emotional_memory, event_memory
):
    now = datetime.now(UTC)
    emotional_memory.record_significant_moment(
        "an older significant moment",
        MemoryType.SHARED,
        "general",
        _state_with_significance(0.9),
        occurred_at=now - timedelta(days=30),
    )
    event_memory.record_milestone(
        "a recent milestone", "milestone", occurred_at=now - timedelta(days=1)
    )

    moment = engine.check_for_celebration()

    assert moment.referenced_content == "a recent milestone"


def test_celebration_prefers_recent_emotional_memory_over_older_milestone(
    engine, emotional_memory, event_memory
):
    now = datetime.now(UTC)
    event_memory.record_milestone(
        "an older milestone", "milestone", occurred_at=now - timedelta(days=30)
    )
    emotional_memory.record_significant_moment(
        "a recent significant moment",
        MemoryType.SHARED,
        "general",
        _state_with_significance(0.9),
        occurred_at=now - timedelta(days=1),
    )

    moment = engine.check_for_celebration()

    assert moment.referenced_content == "a recent significant moment"


def test_celebration_falls_back_to_event_memory_alone_when_emotional_memory_has_nothing(
    engine, event_memory
):
    event_memory.record_milestone("only a milestone exists", "milestone")
    moment = engine.check_for_celebration()
    assert moment.referenced_content == "only a milestone exists"


def test_celebration_falls_back_to_emotional_memory_alone_when_event_memory_has_nothing(
    engine, emotional_memory
):
    emotional_memory.record_significant_moment(
        "only an emotional memory exists",
        MemoryType.SHARED,
        "general",
        _state_with_significance(0.9),
    )
    moment = engine.check_for_celebration()
    assert moment.referenced_content == "only an emotional memory exists"


# --- check_for_continuity_callback() against a real fixture (Testing Checklist) -


def test_continuity_callback_uses_the_ordinary_not_celebration_threshold(engine, emotional_memory):
    """A record below celebration_significance_threshold (0.75) but above
    MemoryConfig.emotional_moment_recall_threshold (0.6 by default) must
    still surface via check_for_continuity_callback(), even though
    check_for_celebration() would reject it."""
    emotional_memory.record_significant_moment(
        "a genuine but modest moment",
        MemoryType.SHARED,
        "general",
        _state_with_significance(0.65),
    )

    assert engine.check_for_celebration() is None
    callback = engine.check_for_continuity_callback()
    assert callback is not None
    assert callback.moment_type is CompanionMomentType.CONTINUITY_CALLBACK
    assert callback.referenced_content == "a genuine but modest moment"


def test_continuity_callback_never_references_event_memory(engine, event_memory):
    """Only EmotionalMemory feeds check_for_continuity_callback() — a
    milestone alone must not produce a continuity callback."""
    event_memory.record_milestone("a real milestone", "milestone")
    assert engine.check_for_continuity_callback() is None


def test_continuity_callback_picks_the_most_significant_across_persona_scopes(
    engine, emotional_memory
):
    emotional_memory.record_significant_moment(
        "a jarvis-scoped moment", MemoryType.JARVIS, "general", _state_with_significance(0.65)
    )
    emotional_memory.record_significant_moment(
        "a more significant minie-scoped moment",
        MemoryType.MINIE,
        "general",
        _state_with_significance(0.9),
    )

    callback = engine.check_for_continuity_callback()

    assert callback.referenced_content == "a more significant minie-scoped moment"


def test_continuity_callback_referenced_at_uses_occurred_at_when_given(engine, emotional_memory):
    occurred = datetime.now(UTC) - timedelta(days=10)
    emotional_memory.record_significant_moment(
        "a dated moment",
        MemoryType.SHARED,
        "general",
        _state_with_significance(0.65),
        occurred_at=occurred,
    )

    callback = engine.check_for_continuity_callback()

    assert callback.referenced_at == occurred
