"""Unit tests for learning.pattern_recognizer's four Sprint 6.7 (Learning
Engine v2, Level 6 Part A) detectors — detect_preferred_workflows()/
detect_preferred_tools()/detect_daily_routine()/detect_study_schedule().
Kept in a separate file from test_pattern_recognizer.py, matching Sprint
5.22's own established "extend the test file that matches the new
scope" judgment; that file's own five-detector-era suite is untouched.

Uses the identical duck-typed fake UsageStore/AnalyticsDashboardService
convention test_pattern_recognizer.py already established, plus a local
fake WorkflowStore for detect_preferred_workflows().
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
from workflow.workflow_model import WorkflowRun

_NOW = datetime(2026, 8, 9, 15, 0, tzinfo=UTC)


class _FakeUsageStore:
    def __init__(self, sessions: list[UsageSession]) -> None:
        self._sessions = sessions

    def list_sessions_since(self, since: datetime) -> list[UsageSession]:
        return [session for session in self._sessions if session.started_at >= since]


class _FakeDashboardService:
    def __init__(self, habit_results: list[HabitConsistency] | None = None) -> None:
        self._habit_results = habit_results or []

    def all_habit_consistency(self) -> list[HabitConsistency]:
        return list(self._habit_results)


class _FakeWorkflowStore:
    def __init__(self, runs: list[WorkflowRun]) -> None:
        self._runs = runs

    def list_run_history(self) -> list[WorkflowRun]:
        return list(self._runs)


def _at_hour(hour: int, day_offset: int = 0) -> datetime:
    return (_NOW - timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0)


def _session(
    process_name: str,
    started_at: datetime,
    category: str | None = None,
    duration_seconds: float = 60.0,
) -> UsageSession:
    return UsageSession(
        process_name=process_name,
        category=category,
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


def _recognizer(
    pattern_store, sessions=None, workflow_runs=None, workflow_store=None, **config_overrides
):
    usage_store = _FakeUsageStore(sessions or [])
    dashboard_service = _FakeDashboardService()
    config = LearningConfig(**config_overrides)
    if workflow_store is None and workflow_runs is not None:
        workflow_store = _FakeWorkflowStore(workflow_runs)
    return PatternRecognizer(
        usage_store, dashboard_service, pattern_store, config, workflow_store=workflow_store
    )


# --- detect_preferred_workflows() -----------------------------------------------------------


def test_detect_preferred_workflows_below_threshold_produces_nothing(pattern_store):
    runs = [WorkflowRun(workflow_id="wf-1", run_at=_at_hour(9, i)) for i in range(2)]
    recognizer = _recognizer(pattern_store, workflow_runs=runs, preferred_workflow_min_runs=3)

    assert recognizer.detect_preferred_workflows() == []


def test_detect_preferred_workflows_at_threshold_surfaces_a_pattern(pattern_store):
    runs = [WorkflowRun(workflow_id="wf-1", run_at=_at_hour(9, i)) for i in range(3)]
    recognizer = _recognizer(pattern_store, workflow_runs=runs, preferred_workflow_min_runs=3)

    patterns = recognizer.detect_preferred_workflows()

    assert len(patterns) == 1
    assert patterns[0].pattern_type is PatternType.PREFERRED_WORKFLOW
    assert patterns[0].subject == "wf-1"
    assert patterns[0].evidence_count == 3


def test_detect_preferred_workflows_with_no_workflow_store_returns_empty_list(pattern_store):
    recognizer = _recognizer(pattern_store, workflow_store=None)

    assert recognizer.detect_preferred_workflows() == []


def test_detect_preferred_workflows_groups_by_workflow_id(pattern_store):
    runs = [
        *(WorkflowRun(workflow_id="wf-1", run_at=_at_hour(9, i)) for i in range(3)),
        WorkflowRun(workflow_id="wf-2", run_at=_at_hour(9, 0)),
    ]
    recognizer = _recognizer(pattern_store, workflow_runs=runs, preferred_workflow_min_runs=3)

    patterns = recognizer.detect_preferred_workflows()

    assert {p.subject for p in patterns} == {"wf-1"}


# --- detect_preferred_tools() ----------------------------------------------------------------


def test_detect_preferred_tools_below_threshold_produces_nothing(pattern_store):
    sessions = [_session("code.exe", _at_hour(9, i), category="coding") for i in range(2)]
    recognizer = _recognizer(
        pattern_store, sessions=sessions, preferred_tool_min_sessions=3, pattern_min_days=3
    )

    assert recognizer.detect_preferred_tools() == []


def test_detect_preferred_tools_at_threshold_surfaces_a_pattern(pattern_store):
    sessions = [_session("code.exe", _at_hour(9, i), category="coding") for i in range(3)]
    recognizer = _recognizer(
        pattern_store, sessions=sessions, preferred_tool_min_sessions=3, pattern_min_days=3
    )

    patterns = recognizer.detect_preferred_tools()

    assert len(patterns) == 1
    assert patterns[0].pattern_type is PatternType.PREFERRED_TOOL
    assert patterns[0].subject == "code.exe"
    assert "coding" in patterns[0].description


def test_detect_preferred_tools_ignores_uncategorized_sessions(pattern_store):
    sessions = [_session("random.exe", _at_hour(9, i), category=None) for i in range(5)]
    recognizer = _recognizer(
        pattern_store, sessions=sessions, preferred_tool_min_sessions=3, pattern_min_days=3
    )

    assert recognizer.detect_preferred_tools() == []


# --- detect_daily_routine() -------------------------------------------------------------------


def test_detect_daily_routine_requires_the_dedicated_day_gate(pattern_store):
    # Enough occurrences, but only 3 distinct days — below daily_routine_min_days=5.
    sessions = [_session("a.exe", _at_hour(14, i)) for i in range(3)]
    recognizer = _recognizer(
        pattern_store,
        sessions=sessions,
        pattern_min_occurrences=2,
        daily_routine_min_days=5,
    )

    assert recognizer.detect_daily_routine() == []


def test_detect_daily_routine_surfaces_once_both_gates_clear(pattern_store):
    sessions = [_session("a.exe", _at_hour(14, i)) for i in range(5)]
    recognizer = _recognizer(
        pattern_store,
        sessions=sessions,
        pattern_min_occurrences=2,
        daily_routine_min_days=5,
    )

    patterns = recognizer.detect_daily_routine()

    assert len(patterns) == 1
    assert patterns[0].pattern_type is PatternType.DAILY_ROUTINE
    assert patterns[0].subject == "14-16"


def test_detect_daily_routine_requires_the_occurrence_gate_independently_of_days(pattern_store):
    # 5 distinct days clears daily_routine_min_days, but occurrence gate is set impossibly high.
    sessions = [_session("a.exe", _at_hour(14, i)) for i in range(5)]
    recognizer = _recognizer(
        pattern_store,
        sessions=sessions,
        pattern_min_occurrences=10,
        daily_routine_min_days=5,
    )

    assert recognizer.detect_daily_routine() == []


# --- detect_study_schedule() ------------------------------------------------------------------


def test_detect_study_schedule_below_threshold_produces_nothing(pattern_store):
    sessions = [_session("ide.exe", _at_hour(20, i), category="coding") for i in range(2)]
    recognizer = _recognizer(
        pattern_store, sessions=sessions, study_schedule_min_sessions=4, pattern_min_days=3
    )

    assert recognizer.detect_study_schedule() == []


def test_detect_study_schedule_at_threshold_surfaces_a_pattern(pattern_store):
    sessions = [_session("ide.exe", _at_hour(20, i), category="coding") for i in range(4)]
    recognizer = _recognizer(
        pattern_store, sessions=sessions, study_schedule_min_sessions=4, pattern_min_days=3
    )

    patterns = recognizer.detect_study_schedule()

    assert len(patterns) == 1
    assert patterns[0].pattern_type is PatternType.STUDY_SCHEDULE
    assert patterns[0].subject == "20-22"


def test_detect_study_schedule_ignores_uncategorized_sessions(pattern_store):
    sessions = [_session("random.exe", _at_hour(20, i), category=None) for i in range(6)]
    recognizer = _recognizer(
        pattern_store, sessions=sessions, study_schedule_min_sessions=4, pattern_min_days=3
    )

    assert recognizer.detect_study_schedule() == []


def test_detect_study_schedule_and_detect_preferred_tools_are_non_contradictory(pattern_store):
    """The same category ('coding') legitimately supports both a
    PREFERRED_TOOL pattern (the IDE) and a STUDY_SCHEDULE pattern (when
    it typically happens) — neither detector's own output excludes the
    other's."""
    sessions = [_session("ide.exe", _at_hour(20, i), category="coding") for i in range(5)]
    recognizer = _recognizer(
        pattern_store,
        sessions=sessions,
        preferred_tool_min_sessions=3,
        study_schedule_min_sessions=3,
        pattern_min_days=3,
    )

    tool_patterns = recognizer.detect_preferred_tools()
    schedule_patterns = recognizer.detect_study_schedule()

    assert len(tool_patterns) == 1
    assert len(schedule_patterns) == 1


# --- run_detection_pass() now aggregates seven detectors ---------------------------------------


def test_run_detection_pass_aggregates_all_seven_detectors(pattern_store):
    sessions = [
        *(_session("a.exe", _at_hour(14, i)) for i in range(5)),  # preferred_time + daily_routine
        *(_session("code.exe", _at_hour(9, i), category="coding") for i in range(5)),
    ]
    runs = [WorkflowRun(workflow_id="wf-1", run_at=_at_hour(9, i)) for i in range(3)]
    recognizer = _recognizer(
        pattern_store,
        sessions=sessions,
        workflow_runs=runs,
        pattern_min_occurrences=3,
        pattern_min_days=3,
        daily_routine_min_days=3,
        preferred_workflow_min_runs=3,
        preferred_tool_min_sessions=3,
        study_schedule_min_sessions=3,
    )

    patterns = recognizer.run_detection_pass()
    pattern_types = {p.pattern_type for p in patterns}

    assert PatternType.PREFERRED_WORKFLOW in pattern_types
    assert PatternType.PREFERRED_TOOL in pattern_types
    assert PatternType.DAILY_ROUTINE in pattern_types
    assert PatternType.STUDY_SCHEDULE in pattern_types
    # All returned patterns were actually persisted.
    stored_ids = {p.pattern_id for p in pattern_store.list_all()}
    assert {p.pattern_id for p in patterns} <= stored_ids
