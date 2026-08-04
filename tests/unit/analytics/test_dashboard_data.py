"""Unit tests for analytics.dashboard_data.

AnalyticsDashboardService is exercised against a duck-typed fake
UsageStore (only list_sessions_since() is needed, matching the real
UsageStore's own contract of "sessions with started_at >= since") rather
than a real SQLite-backed one — UsageStore's own session-derivation logic
is already tested in tests/unit/analytics/test_usage_store.py (Sprint
5.17); this file tests only the aggregation math built on top of it.

habit_consistency()/project_progress() read date.today() internally for
their own window's end anchor — the identical "reads the real clock
internally" gap Sprint 4.15's own ReminderEngine tests first hit, fixed
here the same way Sprint 5.18/5.19 fixed it for WellnessTracker: an
explicit, disclosed reference_date override parameter, used throughout
this file's own window-dependent tests rather than a fixed hardcoded date.
"""

import dataclasses
from datetime import UTC, date, datetime, time, timedelta

from analytics.dashboard_data import (
    AnalyticsDashboardService,
    DailySummary,
    HabitConsistency,
    ProjectProgressSummary,
)
from analytics.usage_model import UsageSession
from config.schema import AnalyticsConfig

_TARGET_DATE = date(2026, 8, 4)
_DAY_START = datetime(2026, 8, 4, tzinfo=UTC)


class _FakeUsageStore:
    def __init__(self, sessions: list[UsageSession]) -> None:
        self._sessions = sessions

    def list_sessions_since(self, since: datetime) -> list[UsageSession]:
        return [session for session in self._sessions if session.started_at >= since]


def _session(
    process_name: str,
    category: str | None,
    started_at: datetime,
    duration_seconds: float,
    sample_count: int = 1,
) -> UsageSession:
    return UsageSession(
        process_name=process_name,
        category=category,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=duration_seconds),
        sample_count=sample_count,
    )


def _midday(target_date: date) -> datetime:
    return datetime.combine(target_date, time(12, 0), tzinfo=UTC)


def _service(sessions: list[UsageSession], **config_overrides) -> AnalyticsDashboardService:
    return AnalyticsDashboardService(_FakeUsageStore(sessions), AnalyticsConfig(**config_overrides))


# --- daily_summary() -----------------------------------------------------------------------


def test_daily_summary_aggregates_total_time_and_top_applications():
    sessions = [
        _session("code.exe", "coding", _DAY_START + timedelta(hours=1), 3600.0),
        _session("code.exe", "coding", _DAY_START + timedelta(hours=3), 1800.0),
        _session("chrome.exe", "browsing", _DAY_START + timedelta(hours=5), 900.0),
    ]
    service = _service(sessions)

    summary = service.daily_summary(_TARGET_DATE)

    assert summary.date == _TARGET_DATE
    assert summary.total_active_seconds == 3600.0 + 1800.0 + 900.0
    assert summary.top_applications == [("code.exe", 5400.0), ("chrome.exe", 900.0)]


def test_daily_summary_caps_top_applications_at_the_configured_limit():
    sessions = [
        _session(f"app{i}.exe", None, _DAY_START + timedelta(hours=i), 100.0 * (i + 1))
        for i in range(5)
    ]
    service = _service(sessions, top_applications_limit=2)

    summary = service.daily_summary(_TARGET_DATE)

    assert len(summary.top_applications) == 2
    assert summary.top_applications[0][0] == "app4.exe"
    assert summary.top_applications[1][0] == "app3.exe"


def test_daily_summary_focus_session_count_and_longest():
    sessions = [
        _session("a.exe", None, _DAY_START + timedelta(hours=1), 500.0),
        _session("b.exe", None, _DAY_START + timedelta(hours=2), 1500.0),
        _session("c.exe", None, _DAY_START + timedelta(hours=3), 200.0),
    ]
    service = _service(sessions)

    summary = service.daily_summary(_TARGET_DATE)

    assert summary.focus_session_count == 3
    assert summary.longest_focus_session_seconds == 1500.0


def test_daily_summary_excludes_sessions_starting_a_different_day():
    sessions = [
        _session("a.exe", None, _DAY_START + timedelta(hours=1), 100.0),
        _session("b.exe", None, _DAY_START - timedelta(hours=1), 100.0),
        _session("c.exe", None, _DAY_START + timedelta(days=1, hours=1), 100.0),
    ]
    service = _service(sessions)

    summary = service.daily_summary(_TARGET_DATE)

    assert summary.focus_session_count == 1
    assert summary.total_active_seconds == 100.0


def test_daily_summary_against_an_empty_usage_store_is_zeroed_not_raised():
    service = _service([])

    summary = service.daily_summary(_TARGET_DATE)

    assert summary.total_active_seconds == 0.0
    assert summary.top_applications == []
    assert summary.focus_session_count == 0
    assert summary.longest_focus_session_seconds == 0.0


# --- habit_consistency() --------------------------------------------------------------------


def test_habit_consistency_counts_distinct_matching_days_within_the_window():
    reference = _TARGET_DATE
    sessions = [
        _session("code.exe", "coding", _midday(reference), 60.0),
        _session("code.exe", "coding", _midday(reference - timedelta(days=1)), 60.0),
        _session("code.exe", "coding", _midday(reference - timedelta(days=1)), 60.0),
        _session("chrome.exe", "browsing", _midday(reference - timedelta(days=2)), 60.0),
    ]
    service = _service(sessions)

    result = service.habit_consistency("coding", window_days=7, reference_date=reference)

    assert result.category == "coding"
    assert result.window_days == 7
    assert result.days_with_activity == 2
    assert result.consistency_ratio == 2 / 7


def test_habit_consistency_excludes_days_outside_the_window():
    reference = _TARGET_DATE
    sessions = [_session("code.exe", "coding", _midday(reference - timedelta(days=10)), 60.0)]
    service = _service(sessions)

    result = service.habit_consistency("coding", window_days=7, reference_date=reference)

    assert result.days_with_activity == 0
    assert result.consistency_ratio == 0.0


def test_habit_consistency_zero_window_days_returns_zeroed_result_not_raised():
    service = _service([])

    result = service.habit_consistency("coding", window_days=0)

    assert result.days_with_activity == 0
    assert result.consistency_ratio == 0.0


def test_habit_consistency_defaults_window_from_config():
    service = _service([], habit_consistency_window_days=14)

    result = service.habit_consistency("coding")

    assert result.window_days == 14


def test_habit_consistency_against_an_empty_usage_store_is_zeroed_not_raised():
    service = _service([])

    result = service.habit_consistency("coding")

    assert result.days_with_activity == 0
    assert result.consistency_ratio == 0.0


def test_all_habit_consistency_iterates_habit_category_names_in_order():
    reference = _TARGET_DATE
    sessions = [
        _session("code.exe", "coding", _midday(reference), 60.0),
        _session("word.exe", "writing", _midday(reference), 60.0),
    ]
    service = _service(sessions, habit_category_names=["coding", "writing", "unused"])

    results = service.all_habit_consistency()

    assert [r.category for r in results] == ["coding", "writing", "unused"]


# --- project_progress() ---------------------------------------------------------------------


def test_project_progress_sums_matching_sessions_within_the_window():
    reference = _TARGET_DATE
    sessions = [
        _session("code.exe", "project-x", _midday(reference), 1000.0),
        _session("code.exe", "project-x", _midday(reference - timedelta(days=1)), 500.0),
        _session("chrome.exe", "browsing", _midday(reference), 200.0),
    ]
    service = _service(sessions)

    result = service.project_progress("project-x", window_days=7, reference_date=reference)

    assert result.total_seconds == 1500.0
    assert result.session_count == 2


def test_project_progress_excludes_sessions_outside_the_window():
    reference = _TARGET_DATE
    sessions = [_session("code.exe", "project-x", _midday(reference - timedelta(days=10)), 1000.0)]
    service = _service(sessions)

    result = service.project_progress("project-x", window_days=7, reference_date=reference)

    assert result.total_seconds == 0.0
    assert result.session_count == 0


def test_project_progress_zero_window_days_returns_zeroed_result_not_raised():
    service = _service([])

    result = service.project_progress("project-x", window_days=0)

    assert result.total_seconds == 0.0
    assert result.session_count == 0


def test_project_progress_against_an_empty_usage_store_is_zeroed_not_raised():
    service = _service([])

    result = service.project_progress("project-x")

    assert result.total_seconds == 0.0
    assert result.session_count == 0


def test_project_progress_summary_has_no_progress_judgment_fields():
    field_names = {field.name for field in dataclasses.fields(ProjectProgressSummary)}

    assert field_names == {"category", "window_days", "total_seconds", "session_count"}


# --- dataclass shapes -----------------------------------------------------------------------


def test_daily_summary_and_habit_consistency_construct_with_all_fields():
    DailySummary(
        date=_TARGET_DATE,
        total_active_seconds=0.0,
        top_applications=[],
        focus_session_count=0,
        longest_focus_session_seconds=0.0,
    )
    HabitConsistency(category="x", window_days=7, days_with_activity=0, consistency_ratio=0.0)
