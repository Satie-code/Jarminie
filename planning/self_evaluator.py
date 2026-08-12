"""Self Evaluation — the genuine feedback loop over Sprint 6.2's TaskGraph
and Sprint 6.9's Multi-Step Workflow Engine: after a Task or a
WorkflowRunResult reaches a terminal state, look at what actually
happened and record it durably. See docs/sprint_book/sprint_6/sprint_6_10.md.

Extends planning/ (not a sixth top-level package) — evaluating a
Task/Goal's outcome is Planning's own natural continuation, the same
relationship memory/lifecycle_manager.py has to memory/memory_store.py.

**"Without self-modifying code" is a hard architectural boundary here,
not a suggestion.** SelfEvaluator never writes to any .py file, never
calls config/loader.py's write path, and never issues any ActionRequest
— its only write surface is TaskGraphStore's own new evaluation_records
table (an append-only log, read by a human or by a future advisory
consumer, never executed automatically). This is mechanically checkable,
not just documented — see tests/unit/planning/test_self_evaluator.py's
own AST-based zero-self-modification proof, confirming this module
contains no open()/Path.write_*/subprocess/ActionRegistry/
ActionExecutor reference anywhere. ActionStatus is imported below
specifically as a read-only enum (needed only to classify an already-
computed WorkflowStepResult's own outcome) — structurally distinct from
ActionRegistry/ActionExecutor, neither of which grants any dispatch
capability.

The mechanical-outcome-before-narrative ordering in
evaluate_workflow_run() is this sprint's own single most important
design decision: the *recorded fact* of success/failure/partial is
derived purely from WorkflowRunResult.step_results/aborted_early, never
from the LLM-backed narrative — a model hallucination can corrupt the
*explanation* of why, never the recorded outcome itself.

A real, disclosed correction from this sprint file's own text:
PlanningStatus (planning/planning_model.py) has exactly two terminal
members, COMPLETED and ABANDONED — there is no separate FAILED member
(see planning/task_graph.py's own mark_failed() docstring, which already
states this explicitly). evaluate_task() therefore raises ValueError for
PROPOSED/ACCEPTED/IN_PROGRESS and produces a real EvaluationRecord for
each of *two* terminal statuses, not the "three terminal statuses" this
sprint file's own Acceptance Criteria describes.

A second, disclosed simplification, necessitated by
reasoning/reasoning_engine.py's own real, current shape:
ReasoningEngine.explain_why() returns a single-line CONCLUSION — its
prompt format has no second field for a separate "improvement idea."
_summarize() asks for both in one call by instructing the model to
append an "Improvement: <suggestion>" clause to its own conclusion when
it has something specific to add, then splits that one line on the
marker — never a second LLM call (which would double this sprint's own
disclosed-unused evaluation_timeout_seconds budget for no real gain, see
config/schema.py's own PlanningConfig docstring), never a new
ReasoningEngine response format.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from core.logging_setup import get_logger
from decision.llm_client import LlmError
from device_control.action_engine import ActionStatus
from planning.planning_model import PlanningStatus

if TYPE_CHECKING:
    from config.schema import PlanningConfig
    from context.context_model import WorkingContext
    from planning.planning_model import Task
    from planning.task_graph_store import TaskGraphStore
    from reasoning.reasoning_engine import ReasoningEngine
    from workflow.workflow_executor import WorkflowRunResult

logger = get_logger(__name__)

_TASK_TERMINAL_STATUSES = (PlanningStatus.COMPLETED, PlanningStatus.ABANDONED)

_FALLBACK_SUMMARY = "Evaluation completed; a detailed narrative could not be generated."

_IMPROVEMENT_MARKER_PATTERN = re.compile(r"improvement:\s*(.+)$", re.IGNORECASE | re.DOTALL)


class EvaluationOutcome(Enum):
    """A WorkflowRunResult with some steps succeeding and others
    skipped/failed is honestly PARTIAL, never rounded up to SUCCESS or
    down to FAILURE."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass
class EvaluationRecord:
    """One evaluation of one completed/failed Task or WorkflowRunResult.

    subject_id is a Task.task_id or a WorkflowRunResult.run_id —
    deliberately not a typed union, matching TaskEdge's own plain-string
    id-reference precedent (planning/task_graph.py); nothing in this
    module needs to distinguish the two subject kinds once evaluation is
    done. improvement_note is None, never an empty string, when there is
    honestly nothing specific to add."""

    record_id: str
    subject_id: str
    outcome: EvaluationOutcome
    summary: str
    improvement_note: str | None
    evaluated_at: datetime


class SelfEvaluator:
    """Constructor DI: (reasoning_engine, task_graph_store,
    planning_config). Not a ManagedModule — a stateless evaluation call
    plus a store write, matching PlanningEngine's own shape. Every
    constructor collaborator type is imported under TYPE_CHECKING only
    (mirroring workflow/workflow_executor.py's own identical DI-
    collaborator-typing precedent) — task_graph_store.py itself imports
    EvaluationOutcome/EvaluationRecord from this module for its own new
    save_evaluation()/list_evaluations_for_goal() signatures, so a real,
    unconditional top-level import of TaskGraphStore here would create an
    actual circular import."""

    def __init__(
        self,
        reasoning_engine: ReasoningEngine,
        task_graph_store: TaskGraphStore,
        planning_config: PlanningConfig,
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._task_graph_store = task_graph_store
        self._planning_config = planning_config

    def evaluate_task(self, task: Task) -> EvaluationRecord:
        """Raises ValueError immediately for a non-terminal Task status —
        evaluating something not yet finished is a caller bug, not a
        runtime condition to tolerate. Persists the produced
        EvaluationRecord via TaskGraphStore.save_evaluation() before
        returning it."""
        if task.status not in _TASK_TERMINAL_STATUSES:
            raise ValueError(
                "SelfEvaluator.evaluate_task() requires a terminal Task status "
                f"(COMPLETED or ABANDONED); got {task.status.value!r} for "
                f"task_id={task.task_id!r}."
            )
        outcome = (
            EvaluationOutcome.SUCCESS
            if task.status is PlanningStatus.COMPLETED
            else EvaluationOutcome.FAILURE
        )
        summary, improvement_note = self._summarize(
            f'the task "{task.title}"', outcome, working_context=None
        )
        record = EvaluationRecord(
            record_id=str(uuid.uuid4()),
            subject_id=task.task_id,
            outcome=outcome,
            summary=summary,
            improvement_note=improvement_note,
            evaluated_at=datetime.now(UTC),
        )
        self._task_graph_store.save_evaluation(record)
        return record

    def evaluate_workflow_run(self, run_result: WorkflowRunResult) -> EvaluationRecord:
        """Derives EvaluationOutcome mechanically from
        run_result.step_results/aborted_early BEFORE calling
        reasoning_engine.explain_why() for the qualitative summary — see
        this module's own docstring for why that ordering is the
        sprint's single most important guarantee. Persists the produced
        EvaluationRecord via TaskGraphStore.save_evaluation() before
        returning it."""
        outcome = _classify_workflow_outcome(run_result)
        summary, improvement_note = self._summarize(
            f'the workflow run "{run_result.workflow_id}" (run_id={run_result.run_id})',
            outcome,
            working_context=None,
        )
        record = EvaluationRecord(
            record_id=str(uuid.uuid4()),
            subject_id=run_result.run_id,
            outcome=outcome,
            summary=summary,
            improvement_note=improvement_note,
            evaluated_at=datetime.now(UTC),
        )
        self._task_graph_store.save_evaluation(record)
        return record

    def _summarize(
        self,
        subject_description: str,
        outcome: EvaluationOutcome,
        working_context: WorkingContext | None,
    ) -> tuple[str, str | None]:
        """The shared ReasoningEngine.explain_why()-backed call producing
        (summary, improvement_note). On LlmError, degrades to a fixed,
        honest fallback summary with improvement_note=None, rather than
        leaving the whole EvaluationRecord unwritten — the mechanical
        outcome is always worth recording even when the narrative half
        fails."""
        subject = (
            f"{subject_description}, which finished as a {outcome.value}. Explain in "
            "1-3 sentences what went well and what didn't. If there is one specific, "
            'concrete way to do better next time, end with "Improvement: <the specific '
            'suggestion>"; if there is honestly nothing specific to add, do not include '
            "that phrase at all."
        )
        try:
            trace = self._reasoning_engine.explain_why(subject, working_context)
        except LlmError:
            logger.warning(
                "SelfEvaluator._summarize(): ReasoningEngine.explain_why() raised "
                "LlmError; degrading to a fixed fallback summary for %s.",
                subject_description,
            )
            return _FALLBACK_SUMMARY, None
        return _split_summary_and_improvement(trace.conclusion)


def _classify_workflow_outcome(run_result: WorkflowRunResult) -> EvaluationOutcome:
    """Purely mechanical, never LLM-derived. SUCCESS only when every step
    ran (none skipped) and every one succeeded; FAILURE only when the run
    aborted early and nothing meaningful completed (zero real
    successes); PARTIAL otherwise — the honest default for anything in
    between, per this module's own EvaluationOutcome docstring."""
    total = len(run_result.step_results)
    succeeded_count = sum(
        1
        for step_result in run_result.step_results
        if not step_result.skipped and step_result.action_result.status is ActionStatus.SUCCEEDED
    )
    skipped_count = sum(1 for step_result in run_result.step_results if step_result.skipped)

    if total > 0 and skipped_count == 0 and succeeded_count == total:
        return EvaluationOutcome.SUCCESS
    if run_result.aborted_early and succeeded_count == 0:
        return EvaluationOutcome.FAILURE
    return EvaluationOutcome.PARTIAL


def _split_summary_and_improvement(conclusion: str) -> tuple[str, str | None]:
    """Extracts an "Improvement: <...>" clause this module's own prompt
    asks the model to append when it has something specific to add —
    see this module's own docstring for why this single-line-split
    approach is used instead of a second LLM call or a new
    ReasoningEngine response format."""
    match = _IMPROVEMENT_MARKER_PATTERN.search(conclusion)
    if not match:
        return conclusion.strip(), None
    improvement_note = match.group(1).strip()
    summary = conclusion[: match.start()].strip()
    if not summary:
        summary = conclusion.strip()
    if not improvement_note:
        return summary, None
    return summary, improvement_note
