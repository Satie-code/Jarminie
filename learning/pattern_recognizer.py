"""Pattern Recognizer — the Learning Engine's detection half. See
docs/sprint_book/sprint_5/sprint_5_21.md.

**"Gradually" and "no unpredictable behavior" (Phase 5.4's own Acceptance
Criteria) are real, binding design constraints, not just phrasing**:
every detect_*() method here is a small, explainable, arithmetic
threshold-and-frequency computation over already-real stored data
(analytics/usage_store.py's UsageStore, Sprint 5.17) — never a trained
model, embedding-similarity search, or LLM call. This mirrors
memory/confidence_scorer.py's own "explainable arithmetic over real
signals, not machine learning" precedent (Sprint 3.5) and directly
satisfies the Learning Engine's own "never makes major autonomous
decisions" line — there is no decision here at all, only observation. A
pattern only becomes LearnedPattern-worthy once it clears BOTH
learning_config.pattern_min_occurrences (or its own habit-consistency
equivalent) AND learning_config.pattern_min_days — the literal mechanism
behind "gradually."

LearnedPatterns are stored in a dedicated PatternStore, not a sixth
memory/models.py MemoryType — see pattern_store.py's own module docstring
for the full reasoning.

detect_*() methods never write to PatternStore themselves — only
run_detection_pass() persists, keeping each detect_*() a pure,
individually testable function over its own inputs, the same "decision
separated from its own side effect" discipline wellness/wellness_tracker.
py's evaluate_triggers() (Sprint 5.18) already established.

**A real, disclosed judgment call on detect_work_habits()'s own two-gate
translation**: the sprint file's own text describes the gate as
"HabitConsistency.consistency_ratio clears pattern_min_occurrences /
pattern_min_days's own equivalent ratio," which is genuinely ambiguous
(pattern_min_occurrences / pattern_min_days, read literally with the
default 5/3, exceeds 1.0 — impossible for a ratio bounded [0.0, 1.0], so
that reading cannot be what was intended). Resolved as two real,
dimensionally sound gates instead: (1) habit.days_with_activity >=
pattern_min_days (the direct days-dimension analog every other detect_*()
method already uses), and (2) habit.consistency_ratio >=
pattern_min_occurrences / habit.window_days (habit.window_days is the
REAL window HabitConsistency was computed over, not pattern_min_days —
converting "at least pattern_min_occurrences worth of evidence" into an
equivalent minimum ratio for that specific window). With this Sprint
Book's own shipped defaults (pattern_min_occurrences=5, pattern_min_days=
3, AnalyticsConfig.habit_consistency_window_days=7), gate (2) requires
5/7 ≈ 0.71 (~5 of the last 7 days active) — the stricter of the two gates
in practice, a sensible "regularly, not just adequately" bar.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from analytics.dashboard_data import AnalyticsDashboardService
from analytics.usage_model import UsageSession
from analytics.usage_store import UsageStore
from config.schema import LearningConfig
from core.logging_setup import get_logger
from learning.pattern_model import LearnedPattern, PatternType
from learning.pattern_store import PatternStore

logger = get_logger(__name__)


class PatternRecognizer:
    """Constructor DI: (usage_store, dashboard_service, pattern_store,
    learning_config)."""

    def __init__(
        self,
        usage_store: UsageStore,
        dashboard_service: AnalyticsDashboardService,
        pattern_store: PatternStore,
        learning_config: LearningConfig,
    ) -> None:
        self._usage_store = usage_store
        self._dashboard_service = dashboard_service
        self._pattern_store = pattern_store
        self._config = learning_config
        self._started = False

    def start(self) -> None:
        self._started = True
        logger.info("Pattern recognizer started.")

    def stop(self) -> None:
        self._started = False
        logger.info("Pattern recognizer stopped.")

    def health_check(self) -> bool:
        return self._started

    def detect_preferred_times(self) -> list[LearnedPattern]:
        bucket_hours = self._config.preferred_time_bucket_hours
        buckets: dict[int, list[UsageSession]] = defaultdict(list)
        for session in self._usage_store.list_sessions_since(self._lookback_start()):
            buckets[session.started_at.hour // bucket_hours].append(session)

        now = datetime.now(UTC)
        patterns: list[LearnedPattern] = []
        for bucket_index, sessions in buckets.items():
            if not self._clears_both_gates(sessions):
                continue
            start_hour = bucket_index * bucket_hours
            end_hour = start_hour + bucket_hours
            patterns.append(
                LearnedPattern(
                    pattern_type=PatternType.PREFERRED_TIME,
                    description=(
                        f"Frequently active between {start_hour:02d}:00 and {end_hour:02d}:00"
                    ),
                    subject=f"{start_hour:02d}-{end_hour:02d}",
                    confidence=self._confidence(len(sessions)),
                    evidence_count=len(sessions),
                    first_observed_at=min(session.started_at for session in sessions),
                    last_updated_at=now,
                )
            )
        return patterns

    def detect_frequent_applications(self) -> list[LearnedPattern]:
        by_process: dict[str, list[UsageSession]] = defaultdict(list)
        for session in self._usage_store.list_sessions_since(self._lookback_start()):
            by_process[session.process_name].append(session)

        now = datetime.now(UTC)
        patterns: list[LearnedPattern] = []
        for process_name, sessions in by_process.items():
            if not self._clears_both_gates(sessions):
                continue
            patterns.append(
                LearnedPattern(
                    pattern_type=PatternType.FREQUENT_APPLICATION,
                    description=f"Frequently uses {process_name}",
                    subject=process_name,
                    confidence=self._confidence(len(sessions)),
                    evidence_count=len(sessions),
                    first_observed_at=min(session.started_at for session in sessions),
                    last_updated_at=now,
                )
            )
        return patterns

    def detect_work_habits(self) -> list[LearnedPattern]:
        now = datetime.now(UTC)
        patterns: list[LearnedPattern] = []
        for habit in self._dashboard_service.all_habit_consistency():
            if habit.days_with_activity < self._config.pattern_min_days:
                continue
            min_ratio = self._config.pattern_min_occurrences / habit.window_days
            if habit.consistency_ratio < min_ratio:
                continue
            patterns.append(
                LearnedPattern(
                    pattern_type=PatternType.WORK_HABIT,
                    description=f"Regularly active in the '{habit.category}' category",
                    subject=habit.category,
                    confidence=min(1.0, habit.consistency_ratio),
                    evidence_count=habit.days_with_activity,
                    first_observed_at=now,
                    last_updated_at=now,
                )
            )
        return patterns

    def run_detection_pass(self) -> list[LearnedPattern]:
        patterns = [
            *self.detect_preferred_times(),
            *self.detect_frequent_applications(),
            *self.detect_work_habits(),
        ]
        for pattern in patterns:
            self._pattern_store.upsert(pattern)
        logger.info("Pattern detection pass upserted %d pattern(s).", len(patterns))
        return patterns

    def _clears_both_gates(self, sessions: list[UsageSession]) -> bool:
        if len(sessions) < self._config.pattern_min_occurrences:
            return False
        distinct_days = {session.started_at.date() for session in sessions}
        return len(distinct_days) >= self._config.pattern_min_days

    def _confidence(self, evidence_count: int) -> float:
        return min(1.0, evidence_count / self._config.pattern_min_occurrences)

    def _lookback_start(self) -> datetime:
        return datetime.now(UTC) - timedelta(days=self._config.lookback_days)
