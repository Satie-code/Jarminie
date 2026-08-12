"""Unit tests for workflow.task_graph_adapter.

DecisionEngineV2 is faked (only rank_actions() is needed, matching this
codebase's own "fake at the boundary" convention) — its own real ranking
arithmetic is already covered by tests/unit/decision/test_decision_engine_v2.py.
"""

from datetime import UTC, datetime

from config.schema import WorkflowConfig
from database.sqlite_client import SqliteClient
from decision.decision_engine_v2 import RankedAction
from device_control.action_engine import ActionType
from planning.planning_model import Goal, Milestone, PlanningStatus, Task
from planning.task_graph import TaskGraph
from security.policy_engine import RiskLevel
from workflow.task_graph_adapter import TaskGraphWorkflowAdapter
from workflow.workflow_store import WorkflowStore

_NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


class FakeDecisionEngineV2:
    """rank_actions() returns candidates in the exact order given by
    default — a test overriding `reorder` can instead return a chosen
    permutation, to prove build_workflow() uses the ranked order, not
    original candidate order."""

    def __init__(self, reorder=None) -> None:
        self._reorder = reorder
        self.rank_actions_calls: list[list] = []

    def rank_actions(self, candidates, working_context=None):
        self.rank_actions_calls.append(candidates)
        ordered = self._reorder(candidates) if self._reorder is not None else candidates
        return [
            RankedAction(
                action_request=candidate,
                risk_level=RiskLevel.LOW,
                confidence=1.0,
                composite_score=1.0,
                requires_confirmation=False,
            )
            for candidate in ordered
        ]


def _task(task_id: str, title: str, description: str = "") -> Task:
    return Task(task_id=task_id, title=title, description=description)


def _goal(tasks: list[Task], statement: str = "Continue Project JARMINEI") -> Goal:
    milestone = Milestone(milestone_id="m1", title="Milestone", tasks=tasks)
    return Goal(
        goal_id="g1",
        statement=statement,
        milestones=[milestone],
        created_at=_NOW,
        status=PlanningStatus.ACCEPTED,
    )


def _adapter(reorder=None, **config_overrides) -> TaskGraphWorkflowAdapter:
    return TaskGraphWorkflowAdapter(
        FakeDecisionEngineV2(reorder), WorkflowConfig(**config_overrides)
    )


# --- keyword classification ----------------------------------------------------------------


def test_classifies_open_keyword_as_launch_application():
    task = _task("t1", "Open VS Code")
    task_graph = TaskGraph(_goal([task]))
    adapter = _adapter()

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert workflow.steps[0].action_type is ActionType.LAUNCH_APPLICATION


def test_classifies_launch_keyword_as_launch_application():
    task = _task("t1", "Launch Ollama")
    task_graph = TaskGraph(_goal([task]))
    adapter = _adapter()

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert workflow.steps[0].action_type is ActionType.LAUNCH_APPLICATION


def test_classifies_pull_keyword_as_system_command():
    task = _task("t1", "Pull Git repository")
    task_graph = TaskGraph(_goal([task]))
    adapter = _adapter()

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert workflow.steps[0].action_type is ActionType.SYSTEM_COMMAND
    assert workflow.steps[0].parameters == {"command": ["Pull Git repository"]}


def test_classifies_a_url_shaped_description_as_open_url():
    task = _task("t1", "Open documentation", description="See https://example.com/docs")
    task_graph = TaskGraph(_goal([task]))
    adapter = _adapter()

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert workflow.steps[0].action_type is ActionType.OPEN_URL
    assert workflow.steps[0].parameters == {"url": "https://example.com/docs"}


def test_unclassifiable_title_falls_back_to_system_command_never_dropped():
    task = _task("t1", "Something ambiguous entirely")
    task_graph = TaskGraph(_goal([task]))
    adapter = _adapter()

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert len(workflow.steps) == 1
    assert workflow.steps[0].action_type is ActionType.SYSTEM_COMMAND


# --- step shape / description --------------------------------------------------------------


def test_step_description_is_copied_from_task_title():
    task = _task("t1", "Open the project folder")
    task_graph = TaskGraph(_goal([task]))
    adapter = _adapter()

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert workflow.steps[0].description == "Open the project folder"


def test_workflow_definition_carries_created_by_and_a_real_id():
    task = _task("t1", "Open VS Code")
    task_graph = TaskGraph(_goal([task]))
    adapter = _adapter()

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="voice_turn")

    assert workflow.created_by == "voice_turn"
    assert workflow.workflow_id
    assert workflow.is_enabled is True


# --- ranking order ---------------------------------------------------------------------------


def test_steps_are_ordered_by_decision_engine_v2s_own_ranking():
    tasks = [
        _task("t1", "Open VS Code"),
        _task("t2", "Launch Ollama"),
        _task("t3", "Pull Git repository"),
    ]
    task_graph = TaskGraph(_goal(tasks))
    # Reverse whatever order rank_actions() was given, proving build_workflow()
    # uses THAT order, not task_graph.ready_tasks()'s own original order.
    adapter = _adapter(reorder=lambda candidates: list(reversed(candidates)))

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert [step.description for step in workflow.steps] == [
        "Pull Git repository",
        "Launch Ollama",
        "Open VS Code",
    ]


def test_originating_tasks_are_returned_in_the_same_ranked_order_as_steps():
    """Sprint 6.13's own necessary correction — the second return value
    must stay in lockstep with the reordering rank_actions() applies,
    not the original task_graph.ready_tasks() order."""
    tasks = [
        _task("t1", "Open VS Code"),
        _task("t2", "Launch Ollama"),
        _task("t3", "Pull Git repository"),
    ]
    task_graph = TaskGraph(_goal(tasks))
    adapter = _adapter(reorder=lambda candidates: list(reversed(candidates)))

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert [task.task_id for task in originating_tasks] == ["t3", "t2", "t1"]
    assert [step.description for step in workflow.steps] == [
        task.title for task in originating_tasks
    ]


def test_rank_actions_is_called_with_one_candidate_per_ready_task():
    tasks = [_task("t1", "Open VS Code"), _task("t2", "Launch Ollama")]
    task_graph = TaskGraph(_goal(tasks))
    engine = FakeDecisionEngineV2()
    adapter = TaskGraphWorkflowAdapter(engine, WorkflowConfig())

    adapter.build_workflow(task_graph, created_by="test")

    assert len(engine.rank_actions_calls) == 1
    assert len(engine.rank_actions_calls[0]) == 2


# --- truncation at max_steps_from_task_graph ------------------------------------------------


def test_build_workflow_truncates_at_max_steps_from_task_graph():
    tasks = [_task(f"t{i}", f"Open App {i}") for i in range(5)]
    task_graph = TaskGraph(_goal(tasks))
    adapter = _adapter(max_steps_from_task_graph=2)

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert len(workflow.steps) == 2


# --- only ready (non-blocked) tasks become steps --------------------------------------------


def test_only_ready_tasks_become_steps():
    tasks = [_task("t1", "Open VS Code"), _task("t2", "Launch Ollama")]
    goal = _goal(tasks)
    task_graph = TaskGraph(goal)
    task_graph.add_dependency("t1", "t2")  # t2 is blocked until t1 completes
    adapter = _adapter()

    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    assert len(workflow.steps) == 1
    assert workflow.steps[0].description == "Open VS Code"


# --- integration-shaped: the existing, unmodified WorkflowStore/WorkflowExecutor accept ------
# this sprint's own output unchanged (Testing Checklist's own explicit requirement) -----------


def test_a_built_workflow_round_trips_through_the_real_unmodified_workflow_store(tmp_path):
    tasks = [
        _task("t1", "Open VS Code"),
        _task("t2", "Pull Git repository"),
        _task("t3", "Open documentation", description="See https://example.com/docs"),
    ]
    task_graph = TaskGraph(_goal(tasks))
    adapter = _adapter()
    workflow, originating_tasks = adapter.build_workflow(task_graph, created_by="test")

    client = SqliteClient(str(tmp_path / "workflow.db"))
    store = WorkflowStore(client, WorkflowConfig())
    store.start()
    try:
        store.save(workflow)  # must not raise -- the real, unmodified store
        fetched = store.get(workflow.workflow_id)
    finally:
        store.stop()

    assert fetched is not None
    assert fetched.name == workflow.name
    assert len(fetched.steps) == 3
    assert {step.action_type for step in fetched.steps} == {
        ActionType.LAUNCH_APPLICATION,
        ActionType.SYSTEM_COMMAND,
        ActionType.OPEN_URL,
    }
