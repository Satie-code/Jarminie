"""Explainability Layer — widens, not replaces, the Explainability Rule
`decision/authority.py`'s `DecisionTrace`/`AuthorityEvaluator.explain()`
(Sprint 3.11) already delivers for ordinary turns, so that "why did you
recommend/decide/do this?" gets a real answer for everything Level 6
Part A has added since: a Planning Engine `Goal`/`Task` (6.1/6.2), a
Decision Engine v2 `RankedAction` (6.5), a Self Evaluation
`EvaluationRecord` (6.10). See docs/sprint_book/sprint_6/sprint_6_11.md.

Extends `reasoning/` (not a new top-level package) — explaining *is* a
reasoning act, and `ReasoningEngine.explain_why()` (6.4) is already this
Book's own general-purpose "why" primitive; `ExplainabilityLayer` is the
aggregator that knows *which* trace object to hand it, not a competing
reasoning mechanism.

**The crux of this sprint: compose existing trace text before calling
the LLM again, never re-explain what was already explained once.**
`DecisionTrace.reasoning_text`, a `Goal`/`Task`'s own status, and an
`EvaluationRecord.summary` were each already produced once, as a real
part of the original decision/plan/evaluation — re-generating a fresh
narrative for the same subject via a second `ReasoningEngine` call would
be redundant latency and a second, unnecessary chance for the model to
say something inconsistent with what actually happened. This mirrors
`internet/summarizer.py`'s own "don't call the model twice for one
answer" discipline, applied here to explanation-composition instead of
summarization. `explain()` only calls `reasoning_engine.explain_why()`
when genuinely nothing else was found for the subject — verified
directly by a zero-call assertion against a fake `ReasoningEngine`, not
just by inspecting the output.

**No new persistence.** `ExplainabilityLayer` reads `DecisionTrace`s,
`Goal`/`Task`s, and `EvaluationRecord`s from wherever they already
live — `decision_trace_lookup` (a plain callable, not a store class:
Level 3 does not persist every `DecisionTrace` in a queryable store of
its own, confirmed against the real `voice/pipeline.py` before assuming
otherwise) and `TaskGraphStore` (6.2/6.10) respectively. It never adds a
store of its own.

**A real, necessary addition beyond this sprint file's own literal
constructor signature**, the same class of gap `planning/task_graph.py`'s
own `TaskGraph.__init__()` already disclosed for `planning_config`: this
sprint file's own Expected Classes lists the constructor as
`(reasoning_engine, task_graph_store, decision_trace_lookup)`, but
`max_explanation_sentences` — the very bound this sprint's own
Acceptance Criteria requires `explain()` to enforce — lives on
`ReasoningConfig`, and `ReasoningEngine` exposes no public accessor for
its own private `_reasoning_config`. A fourth parameter,
`reasoning_config: ReasoningConfig | None = None` (defaulting to
`ReasoningConfig()`, so a caller not tuning it needs no ceremony,
mirroring `TaskGraph`'s own identical default-construction precedent),
is added to make that requirement satisfiable at all.

**Two further real, disclosed resolutions for genuinely ambiguous
subject-kind resolution, both made necessary by what this sprint's own
Files to Modify actually authorizes (`task_graph_store.py` is NOT in
that list — no new store method was added)**:

1. `TaskGraphStore` has no "get one Task by task_id" method, only
   `get_goal(goal_id)`/`list_goals()`. Resolving a `subject_kind="task"`
   request therefore scans every already-loaded `Goal` returned by
   `list_goals()` for a matching `task_id` — an O(goals x tasks) scan,
   using only existing public methods, never a new one.
2. `TaskGraphStore.list_evaluations_for_goal()` (6.10) is the only real
   way to reach an `EvaluationRecord` at all, and it can only ever
   return records for a `Task` under some `Goal` — a `WorkflowRunResult`
   evaluation is structurally unreachable through it (6.10's own
   disclosed scope limit, inherited here unchanged). Resolving a
   `subject_kind="evaluation"` request scans every goal's own
   evaluations for a matching `subject_id`; a workflow-run evaluation
   for which no such goal-attached record could ever exist falls
   through to the `reasoning_engine.explain_why()` fallback like any
   other genuinely-nothing-found subject.

**`subject_kind="ranked_action"` is a real `Literal` member (per this
sprint's own Expected Classes text) that this sprint provides no
resolvable path for.** `DecisionEngineV2.rank_actions()` (6.5) never
persists a `RankedAction` anywhere — there is no store, and this
sprint's own constructor signature defines no `ranked_action_lookup`
callable the way it does for `DecisionTrace`. Every `"ranked_action"`
request therefore gathers zero sources and falls through to the same
LLM fallback as any other unmatched subject — the fourth instance of
this Book's own "accepted but not yet consumable" pattern (6.5's
`authority_evaluator`, 6.8's `decision_engine_v2`/`pattern_recognizer`,
6.10's `evaluation_timeout_seconds`). A live per-turn "the most recent
turn's own top `RankedAction`" lookup, mirroring `decision_trace_lookup`'s
own shape, is Sprint 6.13's own job once a real caller exists to supply
one.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from config.schema import ReasoningConfig
from core.logging_setup import get_logger

if TYPE_CHECKING:
    from context.context_model import WorkingContext
    from decision.authority import DecisionTrace
    from planning.planning_model import Goal, Task
    from planning.self_evaluator import EvaluationRecord
    from planning.task_graph_store import TaskGraphStore
    from reasoning.reasoning_engine import ReasoningEngine

logger = get_logger(__name__)

SubjectKind = Literal["task", "goal", "ranked_action", "decision_trace", "evaluation"]

_SUBJECT_KIND_LABELS: dict[SubjectKind, str] = {
    "task": "task",
    "goal": "goal",
    "ranked_action": "ranked action",
    "decision_trace": "decision",
    "evaluation": "evaluation",
}

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ExplanationRequest:
    """subject_id is a Task.task_id, Goal.goal_id, a DecisionTrace's own
    turn identifier, or (for "evaluation") an EvaluationRecord's own
    subject_id — whatever the user is asking "why?" about."""

    subject_id: str
    subject_kind: SubjectKind


@dataclass
class Explanation:
    """sources names, by type label (e.g. "DecisionTrace", "Goal"), which
    already-recorded trace objects actually contributed — an application
    of the Explainability Rule to this layer's own output, so a user (or
    a future debugging session) can always tell whether an answer was
    assembled from real, already-recorded decisions or freshly reasoned
    from scratch, never left to guess. confidence is carried through
    from a ReasoningTrace.confidence only when the LLM fallback path
    actually fired; None whenever the explanation was composed purely
    from existing trace text, which carries no numeric confidence of its
    own."""

    subject_id: str
    narrative: str
    sources: list[str]
    confidence: float | None


class ExplainabilityLayer:
    """Constructor DI: (reasoning_engine, task_graph_store,
    decision_trace_lookup, reasoning_config=None) — see this module's
    own docstring for why the fourth parameter is a necessary, disclosed
    addition beyond this sprint file's own literal signature.
    task_graph_store/decision_trace_lookup are both Optional: a caller
    that hasn't wired one up yet still gets a real (LLM-fallback)
    Explanation, never an exception. Not a ManagedModule — a stateless
    composition layer, matching ReasoningEngine's/PlanningEngine's own
    identical shape."""

    def __init__(
        self,
        reasoning_engine: ReasoningEngine,
        task_graph_store: TaskGraphStore | None,
        decision_trace_lookup: Callable[[str], DecisionTrace | None] | None,
        reasoning_config: ReasoningConfig | None = None,
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._task_graph_store = task_graph_store
        self._decision_trace_lookup = decision_trace_lookup
        self._reasoning_config = reasoning_config or ReasoningConfig()

    def explain(
        self, request: ExplanationRequest, working_context: WorkingContext | None = None
    ) -> Explanation:
        """Composes whatever existing trace text is available for
        request.subject_id without a fresh LLM call when that alone is
        sufficient; calls reasoning_engine.explain_why() only when
        nothing at all was found for the subject, so "why?" always gets
        a real answer, never a bare "no information available."""
        sources = self._gather(request)
        if sources:
            return Explanation(
                subject_id=request.subject_id,
                narrative=self._compose(sources),
                sources=[label for label, _ in sources],
                confidence=None,
            )
        trace = self._reasoning_engine.explain_why(_fallback_subject(request), working_context)
        return Explanation(
            subject_id=request.subject_id,
            narrative=_truncate_to_sentences(
                trace.conclusion, self._reasoning_config.max_explanation_sentences
            ),
            sources=["ReasoningTrace"],
            confidence=trace.confidence,
        )

    def _compose(self, sources: list[tuple[str, str]]) -> str:
        """The shared text-stitching helper (label, text) -> one
        coherent paragraph, isolated for direct testing independent of
        any live trace lookup."""
        paragraph = " ".join(text.strip() for _, text in sources if text.strip())
        return _truncate_to_sentences(paragraph, self._reasoning_config.max_explanation_sentences)

    def _gather(self, request: ExplanationRequest) -> list[tuple[str, str]]:
        if request.subject_kind == "decision_trace":
            return self._gather_decision_trace(request.subject_id)
        if request.subject_kind == "goal":
            return self._gather_goal(request.subject_id)
        if request.subject_kind == "task":
            return self._gather_task(request.subject_id)
        if request.subject_kind == "evaluation":
            return self._gather_evaluation(request.subject_id)
        # "ranked_action": structurally unresolvable this sprint — see
        # this module's own docstring. Falls through to the LLM fallback.
        return []

    def _gather_decision_trace(self, subject_id: str) -> list[tuple[str, str]]:
        if self._decision_trace_lookup is None:
            return []
        trace = self._decision_trace_lookup(subject_id)
        if trace is None:
            return []
        return [("DecisionTrace", trace.reasoning_text)]

    def _gather_goal(self, subject_id: str) -> list[tuple[str, str]]:
        if self._task_graph_store is None:
            return []
        goal = self._task_graph_store.get_goal(subject_id)
        if goal is None:
            return []
        sources = [("Goal", _describe_goal(goal))]
        records = self._task_graph_store.list_evaluations_for_goal(goal.goal_id)
        if records:
            sources.append(
                ("EvaluationRecord", " ".join(_describe_evaluation(r) for r in records))
            )
        return sources

    def _gather_task(self, subject_id: str) -> list[tuple[str, str]]:
        if self._task_graph_store is None:
            return []
        found = self._find_task(subject_id)
        if found is None:
            return []
        goal, task = found
        sources = [("Task", _describe_task(task))]
        for record in self._task_graph_store.list_evaluations_for_goal(goal.goal_id):
            if record.subject_id == task.task_id:
                sources.append(("EvaluationRecord", _describe_evaluation(record)))
                break
        return sources

    def _gather_evaluation(self, subject_id: str) -> list[tuple[str, str]]:
        if self._task_graph_store is None:
            return []
        for goal in self._task_graph_store.list_goals():
            for record in self._task_graph_store.list_evaluations_for_goal(goal.goal_id):
                if record.subject_id == subject_id:
                    return [("EvaluationRecord", _describe_evaluation(record))]
        return []

    def _find_task(self, task_id: str) -> tuple[Goal, Task] | None:
        for goal in self._task_graph_store.list_goals():
            for milestone in goal.milestones:
                for task in milestone.tasks:
                    if task.task_id == task_id:
                        return goal, task
        return None


def _fallback_subject(request: ExplanationRequest) -> str:
    kind_label = _SUBJECT_KIND_LABELS[request.subject_kind]
    return f'the {kind_label} identified as "{request.subject_id}"'


def _describe_goal(goal: Goal) -> str:
    return f'Goal "{goal.statement}" is currently {goal.status.value}.'


def _describe_task(task: Task) -> str:
    detail = f" — {task.description}" if task.description else ""
    return f'Task "{task.title}" is currently {task.status.value}{detail}.'


def _describe_evaluation(record: EvaluationRecord) -> str:
    note = f" Improvement noted: {record.improvement_note}" if record.improvement_note else ""
    return f"Evaluated as {record.outcome.value}: {record.summary}{note}"


def _truncate_to_sentences(text: str, max_sentences: int) -> str:
    stripped = text.strip()
    sentences = [sentence for sentence in _SENTENCE_SPLIT_PATTERN.split(stripped) if sentence]
    if len(sentences) <= max_sentences:
        return stripped
    return " ".join(sentences[:max_sentences])
