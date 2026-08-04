"""Unit tests for learning.pattern_store."""

from datetime import UTC, datetime

import pytest

from database.sqlite_client import SqliteClient
from learning.pattern_model import LearnedPattern, PatternType
from learning.pattern_store import PatternStore


@pytest.fixture
def store(tmp_path) -> PatternStore:
    client = SqliteClient(str(tmp_path / "patterns.db"))
    pattern_store = PatternStore(client)
    pattern_store.start()
    yield pattern_store
    pattern_store.stop()


def _pattern(
    pattern_type=PatternType.FREQUENT_APPLICATION,
    subject="code.exe",
    confidence=0.8,
    evidence_count=5,
    first_observed_at=None,
    last_updated_at=None,
    description="Frequently uses code.exe",
) -> LearnedPattern:
    now = datetime.now(UTC)
    return LearnedPattern(
        pattern_type=pattern_type,
        description=description,
        subject=subject,
        confidence=confidence,
        evidence_count=evidence_count,
        first_observed_at=first_observed_at or now,
        last_updated_at=last_updated_at or now,
    )


# --- upsert() round trip and identity-based overwrite -------------------------------------


def test_upsert_then_list_all_round_trips_every_field(store):
    pattern = _pattern()

    store.upsert(pattern)
    results = store.list_all()

    assert len(results) == 1
    stored = results[0]
    assert stored.pattern_id == pattern.pattern_id
    assert stored.pattern_type == pattern.pattern_type
    assert stored.subject == pattern.subject
    assert stored.description == pattern.description
    assert stored.confidence == pattern.confidence
    assert stored.evidence_count == pattern.evidence_count
    assert stored.first_observed_at == pattern.first_observed_at
    assert stored.last_updated_at == pattern.last_updated_at


def test_upsert_with_same_identity_overwrites_without_duplicating(store):
    first_time = datetime(2026, 8, 1, tzinfo=UTC)
    second_time = datetime(2026, 8, 4, tzinfo=UTC)
    original = _pattern(
        confidence=0.5, evidence_count=3, first_observed_at=first_time, last_updated_at=first_time
    )
    updated = _pattern(
        confidence=1.0,
        evidence_count=10,
        description="Frequently uses code.exe (a lot)",
        first_observed_at=second_time,
        last_updated_at=second_time,
    )

    store.upsert(original)
    store.upsert(updated)

    results = store.list_all()
    assert len(results) == 1
    stored = results[0]
    assert stored.pattern_id == original.pattern_id
    assert stored.first_observed_at == first_time
    assert stored.confidence == 1.0
    assert stored.evidence_count == 10
    assert stored.description == "Frequently uses code.exe (a lot)"
    assert stored.last_updated_at == second_time


def test_upsert_with_a_different_subject_creates_a_second_row(store):
    store.upsert(_pattern(subject="code.exe"))
    store.upsert(_pattern(subject="chrome.exe"))

    assert len(store.list_all()) == 2


def test_upsert_with_a_different_pattern_type_creates_a_second_row(store):
    store.upsert(_pattern(pattern_type=PatternType.FREQUENT_APPLICATION, subject="coding"))
    store.upsert(_pattern(pattern_type=PatternType.WORK_HABIT, subject="coding"))

    assert len(store.list_all()) == 2


# --- list_by_type() -------------------------------------------------------------------------


def test_list_by_type_returns_only_matching_patterns(store):
    store.upsert(_pattern(pattern_type=PatternType.FREQUENT_APPLICATION, subject="code.exe"))
    store.upsert(_pattern(pattern_type=PatternType.WORK_HABIT, subject="coding"))

    results = store.list_by_type(PatternType.WORK_HABIT)

    assert len(results) == 1
    assert results[0].subject == "coding"


def test_list_by_type_returns_empty_list_when_nothing_matches(store):
    assert store.list_by_type(PatternType.PREFERRED_TIME) == []


# --- persistence survives close/reopen -----------------------------------------------------


def test_persistence_survives_close_and_reopen(tmp_path):
    db_path = str(tmp_path / "patterns_reopen.db")
    client = SqliteClient(db_path)
    store = PatternStore(client)
    store.start()
    store.upsert(_pattern())
    store.stop()

    reopened_client = SqliteClient(db_path)
    reopened_store = PatternStore(reopened_client)
    reopened_store.start()
    results = reopened_store.list_all()
    reopened_store.stop()

    assert len(results) == 1
    assert results[0].subject == "code.exe"


# --- health_check() ---------------------------------------------------------------------


def test_health_check_false_before_start(tmp_path):
    client = SqliteClient(str(tmp_path / "patterns_health.db"))
    store = PatternStore(client)

    assert store.health_check() is False


def test_health_check_true_after_start_false_after_stop(store):
    assert store.health_check() is True
    store.stop()
    assert store.health_check() is False
