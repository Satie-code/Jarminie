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

**Sprint 6.7 (Learning Engine v2, Level 6 Part A) widens this class with
four more detectors** — detect_preferred_workflows()/detect_preferred_
tools()/detect_daily_routine()/detect_study_schedule() — over the same
"small, explainable arithmetic over real stored data" discipline above.
detect_preferred_tools()/detect_study_schedule() both filter to
UsageSessions with a non-None category (AnalyticsConfig.category_map) —
"a tool the user has deliberately categorized," never a guess.
detect_daily_routine() reuses detect_preferred_times()'s own time-bucket
grouping but gates on learning_config.daily_routine_min_days (a
stricter, dedicated day-count bar) instead of pattern_min_days — a
genuine daily routine is a stronger claim than a merely-preferred time.

**A real, disclosed correction to this sprint file's own text**:
run_detection_pass() now calls seven detectors (three existing + four
new), not "nine (five existing + four new)" as that sprint file states —
PatternRecognizer only ever had three real detect_*() methods before
this sprint; PatternType's fourth pre-existing member, CONVERSATION_STYLE,
is detected by a wholly different class (learning/preference_learner.py's
PreferenceLearner.detect_conversation_style()), never called from this
class's own run_detection_pass() and, per backlog/technical_debt.md item
41, with no live caller anywhere in this codebase at all. That sprint
file's own count assumed a wiring that was never actually built.

**A real, disclosed gap in this sprint file's own text, resolved by
adding real workflow run-history infrastructure (not by faking it)**:
detect_preferred_workflows() needs WorkflowStore.list_run_history(), a
method that did not exist anywhere in this codebase before this sprint
(that sprint file's own text claimed it was "confirmed against the real
signature" — it was not; no run-tracking mechanism of any kind existed).
Resolved by adding workflow/workflow_model.py's WorkflowRun,
WorkflowStore.record_run()/list_run_history(), and one guarded call site
in workflow/workflow_executor.py's run() — a user-confirmed decision
(asked directly, given the size of the gap and that it touches files
outside this sprint's own stated Files to Modify), not assumed silently.
workflow_store is therefore an OPTIONAL constructor collaborator
(defaulting to None) specifically so this sprint keeps its own literal
"Zero changes to... main.py" Acceptance Criterion true: main.py's
existing PatternRecognizer(...) construction call is untouched, and
detect_preferred_workflows() degrades to [] (never raises) until a
future sprint (6.13 Integration) threads a real WorkflowStore through —
the identical "optional collaborator, graceful absence" shape Sprint
6.6's KnowledgeGraphStore already established for ContextEngine grounding.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from analytics.dashboard_data import AnalyticsDashboardService
from analytics.usage_model import UsageSession
from analytics.usage_store import UsageStore
from config.schema import LearningConfig
from core.logging_setup import get_logger
from learning.pattern_model import LearnedPattern, PatternType
from learning.pattern_store import PatternStore

if TYPE_CHECKING:
    from workflow.workflow_store import WorkflowStore

logger = get_logger(__name__)


class PatternRecognizer:
    """Constructor DI: (usage_store, dashboard_service, pattern_store,
    learning_config, workflow_store=None). workflow_store is optional —
    see this module's own docstring for why detect_preferred_workflows()
    must tolerate its absence."""

    def __init__(
        self,
        usage_store: UsageStore,
        dashboard_service: AnalyticsDashboardService,
        pattern_store: PatternStore,
        learning_config: LearningConfig,
        workflow_store: WorkflowStore | None = None,
    ) -> None:
        self._usage_store = usage_store
        self._dashboard_service = dashboard_service
        self._pattern_store = pattern_store
        self._config = learning_config
        self._workflow_store = workflow_store
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

    def detect_preferred_workflows(self) -> list[LearnedPattern]:
        """Empty (never raises) when workflow_store is None — see this
        module's own docstring for why that's an expected, not a
        degraded, state today."""
        if self._workflow_store is None:
            return []

        by_workflow: dict[str, list] = defaultdict(list)
        for run in self._workflow_store.list_run_history():
            by_workflow[run.workflow_id].append(run)

        now = datetime.now(UTC)
        patterns: list[LearnedPattern] = []
        for workflow_id, runs in by_workflow.items():
            if len(runs) < self._config.preferred_workflow_min_runs:
                continue
            patterns.append(
                LearnedPattern(
                    pattern_type=PatternType.PREFERRED_WORKFLOW,
                    description=f"Frequently runs the '{workflow_id}' workflow",
                    subject=workflow_id,
                    confidence=min(1.0, len(runs) / self._config.preferred_workflow_min_runs),
                    evidence_count=len(runs),
                    first_observed_at=min(run.run_at for run in runs),
                    last_updated_at=now,
                )
            )
        return patterns

    def detect_preferred_tools(self) -> list[LearnedPattern]:
        """The same shape as detect_frequent_applications(), scoped to
        UsageSessions whose category (AnalyticsConfig.category_map) is
        non-None — "a tool the user has deliberately categorized," never
        any frequently-focused window."""
        by_process: dict[str, list[UsageSession]] = defaultdict(list)
        for session in self._usage_store.list_sessions_since(self._lookback_start()):
            if session.category is None:
                continue
            by_process[session.process_name].append(session)

        now = datetime.now(UTC)
        patterns: list[LearnedPattern] = []
        for process_name, sessions in by_process.items():
            if not self._clears_both_gates(
                sessions, min_occurrences=self._config.preferred_tool_min_sessions
            ):
                continue
            patterns.append(
                LearnedPattern(
                    pattern_type=PatternType.PREFERRED_TOOL,
                    description=f"Frequently uses {process_name} ({sessions[0].category})",
                    subject=process_name,
                    confidence=min(
                        1.0, len(sessions) / self._config.preferred_tool_min_sessions
                    ),
                    evidence_count=len(sessions),
                    first_observed_at=min(session.started_at for session in sessions),
                    last_updated_at=now,
                )
            )
        return patterns

    def detect_daily_routine(self) -> list[LearnedPattern]:
        """Reuses detect_preferred_times()'s own time-bucket grouping,
        but gated on learning_config.daily_routine_min_days (a stricter,
        dedicated day-count bar) instead of pattern_min_days — see this
        module's own docstring for why."""
        bucket_hours = self._config.preferred_time_bucket_hours
        buckets: dict[int, list[UsageSession]] = defaultdict(list)
        for session in self._usage_store.list_sessions_since(self._lookback_start()):
            buckets[session.started_at.hour // bucket_hours].append(session)

        now = datetime.now(UTC)
        patterns: list[LearnedPattern] = []
        for bucket_index, sessions in buckets.items():
            if len(sessions) < self._config.pattern_min_occurrences:
                continue
            distinct_days = {session.started_at.date() for session in sessions}
            if len(distinct_days) < self._config.daily_routine_min_days:
                continue
            start_hour = bucket_index * bucket_hours
            end_hour = start_hour + bucket_hours
            patterns.append(
                LearnedPattern(
                    pattern_type=PatternType.DAILY_ROUTINE,
                    description=(
                        f"Follows a daily routine active between {start_hour:02d}:00 and "
                        f"{end_hour:02d}:00"
                    ),
                    subject=f"{start_hour:02d}-{end_hour:02d}",
                    confidence=min(1.0, len(distinct_days) / self._config.daily_routine_min_days),
                    evidence_count=len(sessions),
                    first_observed_at=min(session.started_at for session in sessions),
                    last_updated_at=now,
                )
            )
        return patterns

    def detect_study_schedule(self) -> list[LearnedPattern]:
        """A time-bucket detector like detect_daily_routine(), but scoped
        to UsageSessions with a non-None category — the exact same
        category_map-driven classification surface detect_preferred_
        tools() uses, reused rather than duplicated."""
        bucket_hours = self._config.preferred_time_bucket_hours
        buckets: dict[int, list[UsageSession]] = defaultdict(list)
        for session in self._usage_store.list_sessions_since(self._lookback_start()):
            if session.category is None:
                continue
            buckets[session.started_at.hour // bucket_hours].append(session)

        now = datetime.now(UTC)
        patterns: list[LearnedPattern] = []
        for bucket_index, sessions in buckets.items():
            if not self._clears_both_gates(
                sessions, min_occurrences=self._config.study_schedule_min_sessions
            ):
                continue
            start_hour = bucket_index * bucket_hours
            end_hour = start_hour + bucket_hours
            patterns.append(
                LearnedPattern(
                    pattern_type=PatternType.STUDY_SCHEDULE,
                    description=(
                        f"Typically studies/works between {start_hour:02d}:00 and "
                        f"{end_hour:02d}:00"
                    ),
                    subject=f"{start_hour:02d}-{end_hour:02d}",
                    confidence=min(
                        1.0, len(sessions) / self._config.study_schedule_min_sessions
                    ),
                    evidence_count=len(sessions),
                    first_observed_at=min(session.started_at for session in sessions),
                    last_updated_at=now,
                )
            )
        return patterns

    def run_detection_pass(self) -> list[LearnedPattern]:
        """Calls seven detectors (three existing + four new, Sprint
        6.7) — see this module's own docstring for why this is seven,
        not the "nine" that sprint file's own text describes."""
        patterns = [
            *self.detect_preferred_times(),
            *self.detect_frequent_applications(),
            *self.detect_work_habits(),
            *self.detect_preferred_workflows(),
            *self.detect_preferred_tools(),
            *self.detect_daily_routine(),
            *self.detect_study_schedule(),
        ]
        for pattern in patterns:
            self._pattern_store.upsert(pattern)
        logger.info("Pattern detection pass upserted %d pattern(s).", len(patterns))
        return patterns

    def _clears_both_gates(
        self, sessions: list[UsageSession], min_occurrences: int | None = None
    ) -> bool:
        threshold = (
            min_occurrences if min_occurrences is not None else self._config.pattern_min_occurrences
        )
        if len(sessions) < threshold:
            return False
        distinct_days = {session.started_at.date() for session in sessions}
        return len(distinct_days) >= self._config.pattern_min_days

    def _confidence(self, evidence_count: int) -> float:
        return min(1.0, evidence_count / self._config.pattern_min_occurrences)

    def _lookback_start(self) -> datetime:
        return datetime.now(UTC) - timedelta(days=self._config.lookback_days)
