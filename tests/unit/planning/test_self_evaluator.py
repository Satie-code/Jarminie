"""Unit tests for planning.self_evaluator.

Uses only a local, in-file fake LanguageModelClient wired into a real
ReasoningEngine — no real Ollama call is made, the same convention as
test_reasoning_engine.py/test_planning_engine.py. _summarize() is tested
directly per this sprint's own explicit Testing Checklist item (unlike
the module-level raw-text parsers this codebase otherwise never imports
by name — _summarize() is a SelfEvaluator method the sprint file itself
names for direct coverage), alongside full indirect coverage through
evaluate_task()/evaluate_workflow_run().
"""

import ast
import os
from datetime import UTC, datetime

import pytest

from config.schema import ModelConfig, PlanningConfig, ReasoningConfig
from database.sqlite_client import SqliteClient
from decision.llm_client import LlmError
from device_control.action_engine import (
    ActionContext,
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)
from planning.planning_model import Goal, Milestone, PlanningStatus, Task
from planning.self_evaluator import EvaluationOutcome, SelfEvaluator
from planning.task_graph_store import TaskGraphStore
from reasoning.reasoning_engine import ReasoningEngine
from workflow.workflow_executor import WorkflowRunResult, WorkflowStepResult


class FakeLanguageModelClient:
    """Implements ONLY the LanguageModelClient Protocol (no is_reachable)
    — matches test_reasoning_engine.py's own established fake."""

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[str] = []

    def generate(
        self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
    ) -> str:
        self.calls.append(prompt)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


@pytest.fixture
def model_config() -> ModelConfig:
    return ModelConfig(ollama_timeout_seconds=5.0)


@pytest.fixture
def reasoning_config() -> ReasoningConfig:
    return ReasoningConfig(reasoning_timeout_seconds=30.0)


@pytest.fixture
def planning_config() -> PlanningConfig:
    return PlanningConfig()


@pytest.fixture
def store(tmp_path) -> TaskGraphStore:
    client = SqliteClient(str(tmp_path / "planning.db"))
    task_graph_store = TaskGraphStore(client, PlanningConfig())
    task_graph_store.start()
    yield task_graph_store
    task_graph_store.stop()


def make_reasoning_engine(model_config, reasoning_config, response=None, error=None):
    fake_client = FakeLanguageModelClient(response=response, error=error)
    return ReasoningEngine(fake_client, model_config, reasoning_config), fake_client


def make_goal_with_task(goal_id: str, task_status: PlanningStatus) -> Goal:
    return Goal(
        goal_id=goal_id,
        statement="Ship the feature",
        milestones=[
            Milestone(
                milestone_id=f"{goal_id}-m1",
                title="Build it",
                tasks=[
                    Task(
                        task_id=f"{goal_id}-t1",
                        title="Write the code",
                        description="Implement the feature end to end",
                        status=task_status,
                    ),
                ],
            ),
        ],
        created_at=datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC),
        status=PlanningStatus.ACCEPTED,
    )


_BASE_CONTEXT = ActionContext(requested_by="test_caller")


def make_step_result(step_index: int, status: ActionStatus, skipped: bool = False):
    request = ActionRequest(
        action_type=ActionType.LAUNCH_APPLICATION,
        parameters={},
        context=_BASE_CONTEXT,
        requested_at=datetime.now(UTC),
    )
    return WorkflowStepResult(
        step_index=step_index,
        action_result=ActionResult(
            request=request,
            status=status,
            completed_at=datetime.now(UTC),
        ),
        skipped=skipped,
    )


def make_run_result(step_results, aborted_early: bool, run_id: str = "run-1") -> WorkflowRunResult:
    return WorkflowRunResult(
        workflow_id="wf-1",
        run_id=run_id,
        step_results=step_results,
        aborted_early=aborted_early,
        whole_workflow_confirmation=None,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )


# --- evaluate_task() ----------------------------------------------------------------------


def test_evaluate_task_raises_for_each_non_terminal_status(store, model_config, reasoning_config):
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: fine"
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())

    for status in (
        PlanningStatus.PROPOSED,
        PlanningStatus.ACCEPTED,
        PlanningStatus.IN_PROGRESS,
    ):
        task = Task(task_id="t1", title="Do the thing", description="", status=status)
        with pytest.raises(ValueError, match="terminal"):
            evaluator.evaluate_task(task)


def test_evaluate_task_completed_produces_success_record(store, model_config, reasoning_config):
    reasoning_engine, fake_client = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: Went well overall."
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())
    task = Task(
        task_id="t1", title="Ship it", description="", status=PlanningStatus.COMPLETED
    )

    record = evaluator.evaluate_task(task)

    assert record.subject_id == "t1"
    assert record.outcome == EvaluationOutcome.SUCCESS
    assert record.summary == "Went well overall."
    assert len(fake_client.calls) == 1


def test_evaluate_task_abandoned_produces_failure_record(store, model_config, reasoning_config):
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: It stalled."
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())
    task = Task(
        task_id="t1", title="Ship it", description="", status=PlanningStatus.ABANDONED
    )

    record = evaluator.evaluate_task(task)

    assert record.outcome == EvaluationOutcome.FAILURE


# --- evaluate_workflow_run() mechanical classification -------------------------------------


def test_all_steps_succeeded_and_none_skipped_is_success(store, model_config, reasoning_config):
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: All good."
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())
    run_result = make_run_result(
        [
            make_step_result(0, ActionStatus.SUCCEEDED),
            make_step_result(1, ActionStatus.SUCCEEDED),
        ],
        aborted_early=False,
    )

    record = evaluator.evaluate_workflow_run(run_result)

    assert record.outcome == EvaluationOutcome.SUCCESS
    assert record.subject_id == "run-1"


def test_aborted_early_with_no_real_completion_is_failure(store, model_config, reasoning_config):
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: Failed fast."
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())
    run_result = make_run_result(
        [make_step_result(0, ActionStatus.FAILED)],
        aborted_early=True,
    )

    record = evaluator.evaluate_workflow_run(run_result)

    assert record.outcome == EvaluationOutcome.FAILURE


def test_no_steps_at_all_and_aborted_is_failure(store, model_config, reasoning_config):
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: Never started."
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())
    run_result = make_run_result([], aborted_early=True)

    record = evaluator.evaluate_workflow_run(run_result)

    assert record.outcome == EvaluationOutcome.FAILURE


def test_mixed_success_and_failure_without_abort_is_partial(store, model_config, reasoning_config):
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: Mixed results."
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())
    run_result = make_run_result(
        [
            make_step_result(0, ActionStatus.SUCCEEDED),
            make_step_result(1, ActionStatus.FAILED),
            make_step_result(2, ActionStatus.SUCCEEDED),
        ],
        aborted_early=False,
    )

    record = evaluator.evaluate_workflow_run(run_result)

    assert record.outcome == EvaluationOutcome.PARTIAL


def test_aborted_early_with_one_real_success_before_the_abort_is_partial(
    store, model_config, reasoning_config
):
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: Got partway."
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())
    run_result = make_run_result(
        [
            make_step_result(0, ActionStatus.SUCCEEDED),
            make_step_result(1, ActionStatus.FAILED),
            make_step_result(2, ActionStatus.PENDING, skipped=True),
        ],
        aborted_early=True,
    )

    record = evaluator.evaluate_workflow_run(run_result)

    assert record.outcome == EvaluationOutcome.PARTIAL


def test_outcome_stays_correct_even_when_summarize_raises_llm_error(
    store, model_config, reasoning_config
):
    """The mechanical outcome must never depend on the narrative half —
    forcing _summarize() to hit LlmError still produces the correct
    outcome, only the summary/improvement_note degrade."""
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, error=LlmError("model unreachable")
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())
    run_result = make_run_result(
        [make_step_result(0, ActionStatus.SUCCEEDED)],
        aborted_early=False,
    )

    record = evaluator.evaluate_workflow_run(run_result)

    assert record.outcome == EvaluationOutcome.SUCCESS
    assert record.summary == (
        "Evaluation completed; a detailed narrative could not be generated."
    )
    assert record.improvement_note is None


# --- _summarize() ---------------------------------------------------------------------------


def test_summarize_normal_case_splits_off_the_improvement_marker(
    store, model_config, reasoning_config
):
    reasoning_engine, _ = make_reasoning_engine(
        model_config,
        reasoning_config,
        response=(
            "CONCLUSION: The task finished on time. Improvement: allocate more time for "
            "testing next time."
        ),
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())

    summary, improvement_note = evaluator._summarize(
        'the task "Ship it"', EvaluationOutcome.SUCCESS, working_context=None
    )

    assert summary == "The task finished on time."
    assert improvement_note == "allocate more time for testing next time."


def test_summarize_with_no_improvement_marker_returns_none(store, model_config, reasoning_config):
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: Nothing further to add."
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())

    summary, improvement_note = evaluator._summarize(
        'the task "Ship it"', EvaluationOutcome.SUCCESS, working_context=None
    )

    assert summary == "Nothing further to add."
    assert improvement_note is None


def test_summarize_degrades_honestly_on_llm_error(store, model_config, reasoning_config):
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, error=LlmError("timeout")
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())

    summary, improvement_note = evaluator._summarize(
        'the task "Ship it"', EvaluationOutcome.FAILURE, working_context=None
    )

    assert summary == "Evaluation completed; a detailed narrative could not be generated."
    assert improvement_note is None


# --- persistence round trip via TaskGraphStore ----------------------------------------------


def test_evaluation_record_persists_and_is_retrievable_for_its_goal(
    store, model_config, reasoning_config
):
    goal = make_goal_with_task("g1", PlanningStatus.COMPLETED)
    store.save_goal(goal)
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: Done well."
    )
    evaluator = SelfEvaluator(reasoning_engine, store, PlanningConfig())
    task = goal.milestones[0].tasks[0]

    record = evaluator.evaluate_task(task)
    fetched = store.list_evaluations_for_goal("g1")

    assert len(fetched) == 1
    assert fetched[0].record_id == record.record_id
    assert fetched[0].subject_id == task.task_id
    assert fetched[0].outcome == EvaluationOutcome.SUCCESS
    assert fetched[0].summary == "Done well."


def test_evaluation_record_persistence_survives_close_and_reopen(
    tmp_path, model_config, reasoning_config
):
    db_path = str(tmp_path / "eval_persist.db")
    goal = make_goal_with_task("g1", PlanningStatus.COMPLETED)

    client1 = SqliteClient(db_path)
    store1 = TaskGraphStore(client1, PlanningConfig())
    store1.start()
    store1.save_goal(goal)
    reasoning_engine, _ = make_reasoning_engine(
        model_config, reasoning_config, response="CONCLUSION: Solid."
    )
    evaluator = SelfEvaluator(reasoning_engine, store1, PlanningConfig())
    evaluator.evaluate_task(goal.milestones[0].tasks[0])
    store1.stop()

    client2 = SqliteClient(db_path)
    store2 = TaskGraphStore(client2, PlanningConfig())
    store2.start()
    fetched = store2.list_evaluations_for_goal("g1")
    store2.stop()

    assert len(fetched) == 1
    assert fetched[0].summary == "Solid."


def test_list_evaluations_for_goal_with_no_evaluations_returns_empty_list(store):
    goal = make_goal_with_task("g1", PlanningStatus.COMPLETED)
    store.save_goal(goal)

    assert store.list_evaluations_for_goal("g1") == []


# --- static: zero self-modification -------------------------------------------------------


def test_self_evaluator_module_has_no_self_modification_surface():
    """AST-based, not a substring scan — mirrors tests/unit/proactive/
    test_proactive_assistant.py's own import-boundary check precedent,
    widened per this sprint's own explicit Architecture Notes to also
    check for open()/Path.write_* calls and a subprocess import, not
    just banned names. Confirms planning/self_evaluator.py never writes
    a file, never shells out, and never references ActionRegistry/
    ActionExecutor (device_control/action_engine.py) — SelfEvaluator's
    only write surface is TaskGraphStore's own evaluation_records table."""
    module_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "planning", "self_evaluator.py"
    )
    with open(module_path, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source, filename=module_path)

    imported_names: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    assert "subprocess" not in imported_modules
    assert "ActionRegistry" not in imported_names
    assert "ActionExecutor" not in imported_names

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id != "open"
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"write_text", "write_bytes"}
