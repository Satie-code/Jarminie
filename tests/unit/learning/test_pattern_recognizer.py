"""Unit tests for learning.pattern_recognizer.

detect_*() methods are exercised against a duck-typed fake UsageStore/
AnalyticsDashboardService (real UsageStore/AnalyticsDashboardService
aggregation logic is already covered by tests/unit/analytics/'s own
Sprint 5.17/5.20 test suites) — this file tests only the pattern-
detection gating/confidence/description logic built on top of them.
run_detection_pass()'s own idempotency test uses a REAL PatternStore
against a temp-file SQLite database, since upsert()'s own identity-based
overwrite behavior is exactly what that test needs to verify for real.
"""

from datetime import UTC, datetime, timedelta

import pytest

from analytics.dashboard_data import HabitConsistency
from analytics.usage_model import UsageSession
from config.schema import LearningConfig
from database.sqlite_client import SqliteClient
from learning.pattern_model import PatternType
from learning.pattern_recognizer import PatternRecognizer
from learning.pattern_store import PatternStore

_NOW = datetime(2026, 8, 4, 15, 0, tzinfo=UTC)


class _FakeUsageStore:
    def __init__(self, sessions: list[UsageSession]) -> None:
        self._sessions = sessions

    def list_sessions_since(self, since: datetime) -> list[UsageSession]:
        return [session for session in self._sessions if session.started_at >= since]


class _FakeDashboardService:
    def __init__(self, habit_results: list[HabitConsistency]) -> None:
        self._habit_results = habit_results
        self.all_habit_consistency_call_count = 0

    def all_habit_consistency(self) -> list[HabitConsistency]:
        self.all_habit_consistency_call_count += 1
        return self._habit_results


def _at_hour(hour: int, day_offset: int = 0) -> datetime:
    return (_NOW - timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0)


def _session(
    process_name: str, started_at: datetime, duration_seconds: float = 60.0
) -> UsageSession:
    return UsageSession(
        process_name=process_name,
        category=None,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=duration_seconds),
        sample_count=1,
    )


@pytest.fixture
def pattern_store(tmp_path) -> PatternStore:
    client = SqliteClient(str(tmp_path / "patterns.db"))
    store = PatternStore(client)
    store.start()
    yield store
    store.stop()


def _recognizer(pattern_store, sessions=None, habit_results=None, **config_overrides):
    usage_store = _FakeUsageStore(sessions or [])
    dashboard_service = _FakeDashboardService(habit_results or [])
    config = LearningConfig(**config_overrides)
    recognizer = PatternRecognizer(usage_store, dashboard_service, pattern_store, config)
    return recognizer, dashboard_service


# --- detect_preferred_times() ---------------------------------------------------------------


def test_detect_preferred_times_requires_the_occurrence_gate(pattern_store):
    sessions = [_session("a.exe", _at_hour(14, day_offset=i)) for i in range(3)]
    recognizer, _ = _recognizer(
        pattern_store, sessions=sessions, pattern_min_occurrences=5, pattern_min_days=3
    )

    assert recognizer.detect_preferred_times() == []


def test_detect_preferred_times_requires_the_distinct_days_gate(pattern_store):
    sessions = [_session(f"app{i}.exe", _at_hour(14)) for i in range(5)]
    recognizer, _ = _recognizer(
        pattern_store, sessions=sessions, pattern_min_occurrences=5, pattern_min_days=3
    )

    assert recognizer.detect_preferred_times() == []


def test_detect_preferred_times_produces_a_pattern_when_both_gates_clear(pattern_store):
    sessions = [_session(f"app{i}.exe", _at_hour(14, day_offset=i)) for i in range(6)]
    recognizer, _ = _recognizer(
        pattern_store,
        sessions=sessions,
        pattern_min_occurrences=5,
        pattern_min_days=3,
        preferred_time_bucket_hours=2,
    )

    patterns = recognizer.detect_preferred_times()

    assert len(patterns) == 1
    pattern = patterns[0]
    assert pattern.pattern_type is PatternType.PREFERRED_TIME
    assert pattern.subject == "14-16"
    assert "14:00" in pattern.description and "16:00" in pattern.description
    assert pattern.evidence_count == 6
    assert pattern.confidence == 1.0


def test_detect_preferred_times_bucket_boundaries_group_correctly(pattern_store):
    sessions = [
        *[_session(f"a{i}.exe", _at_hour(13, day_offset=i)) for i in range(5)],
        *[_session(f"b{i}.exe", _at_hour(14, day_offset=i)) for i in range(5)],
    ]
    recognizer, _ = _recognizer(
        pattern_store,
        sessions=sessions,
        pattern_min_occurrences=5,
        pattern_min_days=3,
        preferred_time_bucket_hours=2,
    )

    patterns = recognizer.detect_preferred_times()
    subjects = {p.subject for p in patterns}

    assert subjects == {"12-14", "14-16"}


def test_detect_preferred_times_confidence_is_capped_at_one(pattern_store):
    sessions = [_session(f"app{i}.exe", _at_hour(14, day_offset=i)) for i in range(20)]
    recognizer, _ = _recognizer(
        pattern_store, sessions=sessions, pattern_min_occurrences=5, pattern_min_days=3
    )

    pattern = recognizer.detect_preferred_times()[0]

    assert pattern.confidence == 1.0


# --- detect_frequent_applications() ----------------------------------------------------------


def test_detect_frequent_applications_requires_the_occurrence_gate(pattern_store):
    sessions = [_session("code.exe", _at_hour(9, day_offset=i)) for i in range(3)]
    recognizer, _ = _recognizer(
        pattern_store, sessions=sessions, pattern_min_occurrences=5, pattern_min_days=3
    )

    assert recognizer.detect_frequent_applications() == []


def test_detect_frequent_applications_requires_the_distinct_days_gate(pattern_store):
    sessions = [_session("code.exe", _at_hour(9)) for _ in range(5)]
    recognizer, _ = _recognizer(
        pattern_store, sessions=sessions, pattern_min_occurrences=5, pattern_min_days=3
    )

    assert recognizer.detect_frequent_applications() == []


def test_detect_frequent_applications_produces_a_pattern_when_both_gates_clear(pattern_store):
    sessions = [_session("code.exe", _at_hour(9, day_offset=i)) for i in range(6)]
    recognizer, _ = _recognizer(
        pattern_store, sessions=sessions, pattern_min_occurrences=5, pattern_min_days=3
    )

    patterns = recognizer.detect_frequent_applications()

    assert len(patterns) == 1
    pattern = patterns[0]
    assert pattern.pattern_type is PatternType.FREQUENT_APPLICATION
    assert pattern.subject == "code.exe"
    assert "code.exe" in pattern.description
    assert pattern.evidence_count == 6


# --- detect_work_habits() ---------------------------------------------------------------------


def test_detect_work_habits_calls_analytics_dashboard_service_not_usage_store(pattern_store):
    habit_results = [
        HabitConsistency(
            category="coding", window_days=7, days_with_activity=5, consistency_ratio=5 / 7
        )
    ]
    recognizer, dashboard_service = _recognizer(
        pattern_store, habit_results=habit_results, pattern_min_occurrences=5, pattern_min_days=3
    )

    patterns = recognizer.detect_work_habits()

    assert dashboard_service.all_habit_consistency_call_count == 1
    assert len(patterns) == 1
    assert patterns[0].pattern_type is PatternType.WORK_HABIT
    assert patterns[0].subject == "coding"


def test_detect_work_habits_requires_the_days_gate(pattern_store):
    habit_results = [
        HabitConsistency(
            category="coding", window_days=7, days_with_activity=2, consistency_ratio=2 / 7
        )
    ]
    recognizer, _ = _recognizer(
        pattern_store, habit_results=habit_results, pattern_min_occurrences=5, pattern_min_days=3
    )

    assert recognizer.detect_work_habits() == []


def test_detect_work_habits_requires_the_ratio_gate(pattern_store):
    habit_results = [
        HabitConsistency(
            category="coding", window_days=7, days_with_activity=4, consistency_ratio=4 / 7
        )
    ]
    recognizer, _ = _recognizer(
        pattern_store, habit_results=habit_results, pattern_min_occurrences=5, pattern_min_days=3
    )

    assert recognizer.detect_work_habits() == []


def test_detect_work_habits_confidence_matches_consistency_ratio(pattern_store):
    habit_results = [
        HabitConsistency(
            category="coding", window_days=7, days_with_activity=7, consistency_ratio=1.0
        )
    ]
    recognizer, _ = _recognizer(
        pattern_store, habit_results=habit_results, pattern_min_occurrences=5, pattern_min_days=3
    )

    pattern = recognizer.detect_work_habits()[0]

    assert pattern.confidence == 1.0
    assert pattern.evidence_count == 7


def test_detect_work_habits_degrades_to_empty_list_with_no_configured_categories(pattern_store):
    recognizer, dashboard_service = _recognizer(pattern_store, habit_results=[])

    assert recognizer.detect_work_habits() == []
    assert dashboard_service.all_habit_consistency_call_count == 1


# --- run_detection_pass() ---------------------------------------------------------------------


def test_run_detection_pass_upserts_every_detected_pattern(pattern_store):
    sessions = [_session("code.exe", _at_hour(9, day_offset=i)) for i in range(6)]
    recognizer, _ = _recognizer(
        pattern_store, sessions=sessions, pattern_min_occurrences=5, pattern_min_days=3
    )

    returned = recognizer.run_detection_pass()

    assert len(returned) >= 1
    assert len(pattern_store.list_all()) == len(returned)


def test_run_detection_pass_does_not_duplicate_rows_on_repeated_runs(pattern_store):
    sessions = [_session("code.exe", _at_hour(9, day_offset=i)) for i in range(6)]
    recognizer, _ = _recognizer(
        pattern_store, sessions=sessions, pattern_min_occurrences=5, pattern_min_days=3
    )

    recognizer.run_detection_pass()
    first_count = len(pattern_store.list_all())
    recognizer.run_detection_pass()
    second_count = len(pattern_store.list_all())

    assert first_count == second_count


# --- health_check() ---------------------------------------------------------------------------


def test_health_check_false_before_start(pattern_store):
    recognizer, _ = _recognizer(pattern_store)

    assert recognizer.health_check() is False


def test_health_check_true_after_start_false_after_stop(pattern_store):
    recognizer, _ = _recognizer(pattern_store)

    recognizer.start()
    assert recognizer.health_check() is True
    recognizer.stop()
    assert recognizer.health_check() is False
