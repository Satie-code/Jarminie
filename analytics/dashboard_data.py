"""Analytics Dashboard Data — turns Sprint 5.17's raw AppFocusSample/
UsageSession data into aggregate, meaningful statistics. See
docs/sprint_book/sprint_5/sprint_5_20.md.

Deliberately data-only, per this sprint's own name — no dashboard
widget/UI is built here (no UI sprint for Analytics is named anywhere in
this Sprint Book's own roadmap-granularity table, unlike Level 5 Part A's
dedicated Presentation Layer sprints).

**A real, disclosed scoping narrowing on "Project progress"**: Part 2
names it as one of six things the Analytics Engine tracks, but nothing in
this codebase has ever built a concept of a user-declared "project" (as
distinct from a plain application or file). Rather than fabricate one
with no real data behind it, ProjectProgressSummary is a best-effort
proxy: time spent under any category_map value the user has themselves
labeled as a project category (AnalyticsConfig.project_category_names) —
openly narrower than genuine multi-project tracking. ProjectProgressSummary
has no field that could be mistaken for a genuine completion percentage
or milestone list — only time and session count, the two things
UsageStore's own data can actually support without fabrication.

AnalyticsDashboardService is deliberately NOT a ManagedModule and
registers no TaskScheduler job of its own — every method is a plain,
synchronous, on-demand query over already-persisted data, mirroring
memory/retrieval_engine.py's MemoryRetrievalEngine's own "composes
stores, holds no state of its own" precedent (Sprint 3.9). No caching:
acceptable at this project's own single-user, local-SQLite scale, the
same reasoning that lets MemoryRetrievalEngine skip caching too.

daily_summary()'s "calendar day" boundary is computed directly against
UTC (matching how every UsageSession timestamp is actually stored,
AppFocusSample.sampled_at = datetime.now(UTC)) — the same real local/UTC
conflation this codebase's own WellnessConfig.late_night_start_hour-style
"local time" assumptions already make elsewhere, not a new gap this
sprint introduces.

A "focus session" here is simply one UsageSession — a session's own
definition (a contiguous run of same-process samples, Sprint 5.17) is
already what "focused on one thing for a stretch of time" means in this
codebase's own terms; no separate minimum-duration threshold is invented
without a named basis for one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from analytics.usage_model import UsageSession
from analytics.usage_store import UsageStore
from config.schema import AnalyticsConfig


@dataclass
class DailySummary:
    date: date
    total_active_seconds: float
    top_applications: list[tuple[str, float]]
    focus_session_count: int
    longest_focus_session_seconds: float


@dataclass
class HabitConsistency:
    category: str
    window_days: int
    days_with_activity: int
    consistency_ratio: float


@dataclass
class ProjectProgressSummary:
    """Deliberately no "progress" judgment of any kind (no percentage-
    complete, no trend arrow) — see this module's own docstring."""

    category: str
    window_days: int
    total_seconds: float
    session_count: int


class AnalyticsDashboardService:
    """Constructor DI: (usage_store, analytics_config). Stateless beyond
    its own constructor DI — every method computes fresh from usage_store
    at call time, never caches."""

    def __init__(self, usage_store: UsageStore, analytics_config: AnalyticsConfig) -> None:
        self._usage_store = usage_store
        self._config = analytics_config

    def daily_summary(self, target_date: date) -> DailySummary:
        start_of_day = datetime.combine(target_date, time.min, tzinfo=UTC)
        end_of_day = start_of_day + timedelta(days=1)
        sessions = [
            session
            for session in self._usage_store.list_sessions_since(start_of_day)
            if session.started_at < end_of_day
        ]

        durations = [self._duration_seconds(session) for session in sessions]
        total_active_seconds = sum(durations)

        per_app: dict[str, float] = {}
        for session, duration in zip(sessions, durations, strict=True):
            per_app[session.process_name] = per_app.get(session.process_name, 0.0) + duration
        top_applications = sorted(per_app.items(), key=lambda item: item[1], reverse=True)
        top_applications = top_applications[: self._config.top_applications_limit]

        return DailySummary(
            date=target_date,
            total_active_seconds=total_active_seconds,
            top_applications=top_applications,
            focus_session_count=len(sessions),
            longest_focus_session_seconds=max(durations, default=0.0),
        )

    def habit_consistency(
        self,
        category: str,
        window_days: int | None = None,
        reference_date: date | None = None,
    ) -> HabitConsistency:
        """reference_date (not in the sprint file's own literal signature)
        defaults to date.today() — an explicit, disclosed addition beyond
        the sprint's own spec, added so this method's own window doesn't
        silently read the real wall clock with no way to control it in a
        test, the identical "reads the real clock internally, needs an
        explicit override" gap Sprint 4.15's own ReminderEngine tests
        first hit, and the same fix shape Sprint 5.18/5.19's own
        evaluate_triggers(now=...) parameter already established."""
        window_days = (
            window_days if window_days is not None else self._config.habit_consistency_window_days
        )
        if window_days <= 0:
            return HabitConsistency(
                category=category, window_days=window_days, days_with_activity=0,
                consistency_ratio=0.0,
            )
        window_start = self._window_start(window_days, reference_date)
        sessions = self._usage_store.list_sessions_since(window_start)
        matching_days = {
            session.started_at.date() for session in sessions if session.category == category
        }
        days_with_activity = len(matching_days)
        return HabitConsistency(
            category=category,
            window_days=window_days,
            days_with_activity=days_with_activity,
            consistency_ratio=min(1.0, days_with_activity / window_days),
        )

    def project_progress(
        self,
        category: str,
        window_days: int | None = None,
        reference_date: date | None = None,
    ) -> ProjectProgressSummary:
        """reference_date — see habit_consistency()'s own docstring for
        why this is a disclosed addition beyond the sprint's own literal
        signature."""
        window_days = (
            window_days if window_days is not None else self._config.habit_consistency_window_days
        )
        if window_days <= 0:
            return ProjectProgressSummary(
                category=category, window_days=window_days, total_seconds=0.0, session_count=0
            )
        window_start = self._window_start(window_days, reference_date)
        sessions = [
            session
            for session in self._usage_store.list_sessions_since(window_start)
            if session.category == category
        ]
        return ProjectProgressSummary(
            category=category,
            window_days=window_days,
            total_seconds=sum(self._duration_seconds(session) for session in sessions),
            session_count=len(sessions),
        )

    def all_habit_consistency(self) -> list[HabitConsistency]:
        return [
            self.habit_consistency(category) for category in self._config.habit_category_names
        ]

    def _window_start(self, window_days: int, reference_date: date | None) -> datetime:
        reference_date = reference_date if reference_date is not None else date.today()
        start_of_reference_day = datetime.combine(reference_date, time.min, tzinfo=UTC)
        return start_of_reference_day - timedelta(days=window_days - 1)

    def _duration_seconds(self, session: UsageSession) -> float:
        return (session.ended_at - session.started_at).total_seconds()
