"""Unit tests for planning.task_graph."""

from datetime import UTC, datetime

import pytest

from config.schema import PlanningConfig
from planning.errors import CyclicDependencyError
from planning.planning_model import Goal, Milestone, PlanningStatus, Task
from planning.task_graph import TaskEdge, TaskGraph


def make_task(task_id: str, status: PlanningStatus = PlanningStatus.PROPOSED) -> Task:
    return Task(task_id=task_id, title=f"Task {task_id}", description="", status=status)


def make_goal(*milestones: Milestone) -> Goal:
    return Goal(
        goal_id="g1",
        statement="A goal",
        milestones=list(milestones),
        created_at=datetime.now(UTC),
    )


# --- add_dependency() / cycle detection ------------------------------------------------


def test_add_dependency_accepts_a_valid_edge():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a"), make_task("b")])
    graph = TaskGraph(make_goal(milestone))

    graph.add_dependency("a", "b")

    assert graph.edges == [TaskEdge(from_task_id="a", to_task_id="b")]


def test_add_dependency_rejects_a_direct_two_cycle():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a"), make_task("b")])
    graph = TaskGraph(make_goal(milestone))
    graph.add_dependency("a", "b")

    with pytest.raises(CyclicDependencyError):
        graph.add_dependency("b", "a")

    assert graph.edges == [TaskEdge(from_task_id="a", to_task_id="b")]  # unchanged


def test_add_dependency_rejects_a_longer_transitive_cycle():
    milestone = Milestone(
        milestone_id="m1",
        title="M1",
        tasks=[make_task("a"), make_task("b"), make_task("c")],
    )
    graph = TaskGraph(make_goal(milestone))
    graph.add_dependency("a", "b")
    graph.add_dependency("b", "c")

    with pytest.raises(CyclicDependencyError):
        graph.add_dependency("c", "a")

    assert len(graph.edges) == 2  # unchanged


def test_add_dependency_rejects_a_self_loop():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a")])
    graph = TaskGraph(make_goal(milestone))

    with pytest.raises(CyclicDependencyError):
        graph.add_dependency("a", "a")


def test_add_dependency_unknown_task_id_raises_value_error():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a")])
    graph = TaskGraph(make_goal(milestone))

    with pytest.raises(ValueError, match="a-ghost"):
        graph.add_dependency("a-ghost", "a")


def test_add_dependency_enforces_max_task_dependencies():
    tasks = [make_task(str(i)) for i in range(4)]
    milestone = Milestone(milestone_id="m1", title="M1", tasks=tasks)
    graph = TaskGraph(make_goal(milestone), planning_config=PlanningConfig(max_task_dependencies=2))
    graph.add_dependency("0", "3")
    graph.add_dependency("1", "3")

    with pytest.raises(ValueError, match="max_task_dependencies"):
        graph.add_dependency("2", "3")

    assert len(graph.edges) == 2


# --- ready_tasks() / blocked_tasks() --------------------------------------------------


def test_ready_tasks_returns_independent_tasks_as_parallel_candidates():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a"), make_task("b")])
    graph = TaskGraph(make_goal(milestone))  # no edges between a and b

    ready_ids = {task.task_id for task in graph.ready_tasks()}

    assert ready_ids == {"a", "b"}
    assert graph.blocked_tasks() == []


def test_ready_tasks_excludes_a_task_whose_prerequisite_is_not_completed():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a"), make_task("b")])
    graph = TaskGraph(make_goal(milestone))
    graph.add_dependency("a", "b")

    ready_ids = {task.task_id for task in graph.ready_tasks()}
    blocked_ids = {task.task_id for task in graph.blocked_tasks()}

    assert ready_ids == {"a"}
    assert blocked_ids == {"b"}


def test_ready_tasks_includes_a_task_once_its_prerequisite_is_completed():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a"), make_task("b")])
    graph = TaskGraph(make_goal(milestone))
    graph.add_dependency("a", "b")

    graph.mark_completed("a")

    assert {task.task_id for task in graph.ready_tasks()} == {"b"}
    assert graph.blocked_tasks() == []


def test_linear_chain_only_the_first_task_is_ready():
    milestone = Milestone(
        milestone_id="m1",
        title="M1",
        tasks=[make_task("a"), make_task("b"), make_task("c")],
    )
    graph = TaskGraph(make_goal(milestone))
    graph.add_dependency("a", "b")
    graph.add_dependency("b", "c")

    assert {task.task_id for task in graph.ready_tasks()} == {"a"}
    assert {task.task_id for task in graph.blocked_tasks()} == {"b", "c"}


def test_ready_and_blocked_tasks_exclude_terminal_tasks():
    milestone = Milestone(
        milestone_id="m1",
        title="M1",
        tasks=[
            make_task("done", status=PlanningStatus.COMPLETED),
            make_task("abandoned", status=PlanningStatus.ABANDONED),
            make_task("active"),
        ],
    )
    graph = TaskGraph(make_goal(milestone))

    ready_ids = {task.task_id for task in graph.ready_tasks()}
    blocked_ids = {task.task_id for task in graph.blocked_tasks()}

    assert ready_ids == {"active"}
    assert blocked_ids == set()


def test_a_permanently_abandoned_prerequisite_leaves_its_dependent_blocked():
    milestone = Milestone(
        milestone_id="m1",
        title="M1",
        tasks=[make_task("a"), make_task("b")],
    )
    graph = TaskGraph(make_goal(milestone))
    graph.add_dependency("a", "b")

    graph.mark_failed("a")

    assert graph.ready_tasks() == []
    assert {task.task_id for task in graph.blocked_tasks()} == {"b"}


# --- mark_completed() / mark_failed() cascade -------------------------------------------


def test_mark_completed_cascades_to_milestone_and_goal_when_everything_completes():
    milestone1 = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a")])
    milestone2 = Milestone(milestone_id="m2", title="M2", tasks=[make_task("b")])
    goal = make_goal(milestone1, milestone2)
    graph = TaskGraph(goal)

    graph.mark_completed("a")
    assert milestone1.status is PlanningStatus.COMPLETED
    assert goal.status is not PlanningStatus.COMPLETED  # m2 not done yet

    graph.mark_completed("b")
    assert milestone2.status is PlanningStatus.COMPLETED
    assert goal.status is PlanningStatus.COMPLETED


def test_mark_completed_does_not_cascade_a_milestone_with_an_incomplete_sibling():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a"), make_task("b")])
    graph = TaskGraph(make_goal(milestone))

    graph.mark_completed("a")

    assert milestone.status is PlanningStatus.PROPOSED


def test_mark_failed_sets_abandoned_and_does_not_cascade():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a"), make_task("b")])
    goal = make_goal(milestone)
    graph = TaskGraph(goal)

    graph.mark_failed("a")
    graph.mark_completed("b")

    task_a = next(t for t in milestone.tasks if t.task_id == "a")
    assert task_a.status is PlanningStatus.ABANDONED
    assert milestone.status is not PlanningStatus.COMPLETED
    assert goal.status is not PlanningStatus.COMPLETED


def test_mark_completed_unknown_task_id_raises_value_error():
    milestone = Milestone(milestone_id="m1", title="M1", tasks=[make_task("a")])
    graph = TaskGraph(make_goal(milestone))

    with pytest.raises(ValueError, match="ghost"):
        graph.mark_completed("ghost")


# --- Sprint 6.14 hardening (scenario e): CyclicDependencyError reachability ------------------


def test_add_dependency_has_no_production_caller_anywhere():
    """Sprint 6.14's own scenario (e) asks to confirm a live
    _handle_planning_turn() degrades honestly when add_dependency()
    raises CyclicDependencyError mid-turn. Investigation against the
    real Sprint 6.13 graph found the scenario's own premise does not
    currently hold: add_dependency() has no caller anywhere in
    production code. planning/task_graph.py's own module docstring
    already discloses why — "Dependency edges are deliberately NOT
    inferred automatically from a PlanningEngine decomposition anywhere
    in this module" — PlanningEngine.decompose_goal() (6.1) never
    proposes edges, and TaskGraph.__init__() (this file) accepts an
    edges list directly (from TaskGraphStore.get_edges(), the shape
    _run_accepted_plan() actually uses) without calling this method at
    all. A CyclicDependencyError can therefore never reach a live turn
    today — confirmed here via a real, repo-wide AST scan (mirroring
    tests/unit/proactive/test_proactive_assistant.py's own import-
    boundary AST proof) rather than fabricating a fix for an
    unreachable path. If a future sprint ever wires something that DOES
    call add_dependency() from a live turn, this test will fail and
    that's the correct, honest signal that _handle_planning_turn()'s own
    CyclicDependencyError handling (still absent) needs to be added
    then, not before."""
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    excluded_dirs = {"tests", ".venv", "docs", ".git"}
    call_sites: list[str] = []

    for py_file in repo_root.rglob("*.py"):
        if any(part in excluded_dirs for part in py_file.parts):
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_dependency"
            ):
                call_sites.append(str(py_file.relative_to(repo_root)))

    assert call_sites == []
