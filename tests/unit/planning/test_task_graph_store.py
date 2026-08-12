"""Unit tests for planning.task_graph_store."""

from datetime import UTC, datetime

import pytest

from config.schema import PlanningConfig
from database.sqlite_client import SqliteClient
from planning.planning_model import Goal, Milestone, PlanningStatus, Task
from planning.task_graph import TaskEdge
from planning.task_graph_store import TaskGraphStore


def make_goal(goal_id: str = "g1") -> Goal:
    return Goal(
        goal_id=goal_id,
        statement="Build a small app",
        milestones=[
            Milestone(
                milestone_id=f"{goal_id}-m1",
                title="Set up the project",
                tasks=[
                    Task(
                        task_id=f"{goal_id}-t1",
                        title="Create the repository",
                        description="Initialize a new git repository",
                        estimated_effort="5 minutes",
                    ),
                    Task(
                        task_id=f"{goal_id}-t2",
                        title="Install dependencies",
                        description="Run the package manager",
                    ),
                ],
            ),
            Milestone(
                milestone_id=f"{goal_id}-m2",
                title="Write the first feature",
                tasks=[
                    Task(
                        task_id=f"{goal_id}-t3",
                        title="Implement the core logic",
                        description="Write the main function",
                        status=PlanningStatus.IN_PROGRESS,
                    ),
                ],
            ),
        ],
        created_at=datetime(2026, 8, 6, 12, 0, 0, tzinfo=UTC),
        status=PlanningStatus.ACCEPTED,
    )


@pytest.fixture
def store(tmp_path) -> TaskGraphStore:
    client = SqliteClient(str(tmp_path / "planning.db"))
    task_graph_store = TaskGraphStore(client, PlanningConfig())
    task_graph_store.start()
    yield task_graph_store
    task_graph_store.stop()


# --- save_goal()/get_goal() round trip --------------------------------------------------


def test_save_get_round_trip_preserves_every_field(store):
    goal = make_goal()

    store.save_goal(goal)
    fetched = store.get_goal(goal.goal_id)

    assert fetched is not None
    assert fetched.goal_id == goal.goal_id
    assert fetched.statement == goal.statement
    assert fetched.created_at == goal.created_at
    assert fetched.status == goal.status
    assert len(fetched.milestones) == 2
    assert fetched.milestones[0].milestone_id == goal.milestones[0].milestone_id
    assert fetched.milestones[0].title == goal.milestones[0].title
    assert len(fetched.milestones[0].tasks) == 2
    restored_task = fetched.milestones[0].tasks[0]
    original_task = goal.milestones[0].tasks[0]
    assert restored_task.task_id == original_task.task_id
    assert restored_task.title == original_task.title
    assert restored_task.description == original_task.description
    assert restored_task.estimated_effort == original_task.estimated_effort
    assert restored_task.status == original_task.status
    assert fetched.milestones[1].tasks[0].status == PlanningStatus.IN_PROGRESS


def test_save_get_preserves_milestone_and_task_order(store):
    goal = make_goal()

    store.save_goal(goal)
    fetched = store.get_goal(goal.goal_id)

    assert [m.milestone_id for m in fetched.milestones] == [
        goal.milestones[0].milestone_id,
        goal.milestones[1].milestone_id,
    ]
    assert [t.task_id for t in fetched.milestones[0].tasks] == [
        goal.milestones[0].tasks[0].task_id,
        goal.milestones[0].tasks[1].task_id,
    ]


def test_get_nonexistent_goal_returns_none(store):
    assert store.get_goal("does-not-exist") is None


def test_save_goal_overwrites_existing_goal_outright(store):
    goal = make_goal()
    store.save_goal(goal)

    updated = make_goal()
    updated.statement = "A different statement"
    updated.milestones = updated.milestones[:1]
    store.save_goal(updated)

    fetched = store.get_goal(goal.goal_id)
    assert fetched.statement == "A different statement"
    assert len(fetched.milestones) == 1


def test_a_task_with_no_estimated_effort_round_trips_as_none(store):
    goal = make_goal()

    store.save_goal(goal)
    fetched = store.get_goal(goal.goal_id)

    assert fetched.milestones[0].tasks[1].estimated_effort is None


# --- list_goals() ------------------------------------------------------------------------


def test_list_goals_reflects_saved_goals(store):
    assert store.list_goals() == []

    store.save_goal(make_goal("g-a"))
    store.save_goal(make_goal("g-b"))

    assert {g.goal_id for g in store.list_goals()} == {"g-a", "g-b"}


def test_list_goals_filters_by_status(store):
    accepted = make_goal("g-accepted")
    proposed = make_goal("g-proposed")
    proposed.status = PlanningStatus.PROPOSED
    store.save_goal(accepted)
    store.save_goal(proposed)

    result = store.list_goals(status=PlanningStatus.PROPOSED)

    assert {g.goal_id for g in result} == {"g-proposed"}


# --- save_edges()/get_edges() ------------------------------------------------------------


def test_save_get_edges_round_trip(store):
    goal = make_goal()
    store.save_goal(goal)
    edges = [
        TaskEdge(from_task_id="g1-t1", to_task_id="g1-t2"),
        TaskEdge(from_task_id="g1-t2", to_task_id="g1-t3"),
    ]

    store.save_edges(goal.goal_id, edges)
    fetched_edges = store.get_edges(goal.goal_id)

    assert len(fetched_edges) == 2
    assert TaskEdge(from_task_id="g1-t1", to_task_id="g1-t2") in fetched_edges
    assert TaskEdge(from_task_id="g1-t2", to_task_id="g1-t3") in fetched_edges


def test_get_edges_for_a_goal_with_no_saved_edges_returns_empty_list(store):
    goal = make_goal()
    store.save_goal(goal)

    assert store.get_edges(goal.goal_id) == []


def test_save_edges_overwrites_existing_edges_outright(store):
    goal = make_goal()
    store.save_goal(goal)
    store.save_edges(goal.goal_id, [TaskEdge(from_task_id="g1-t1", to_task_id="g1-t2")])

    store.save_edges(goal.goal_id, [TaskEdge(from_task_id="g1-t2", to_task_id="g1-t3")])

    fetched_edges = store.get_edges(goal.goal_id)
    assert fetched_edges == [TaskEdge(from_task_id="g1-t2", to_task_id="g1-t3")]


# --- real persistence across close()/reopen, full goal+edge structure --------------------


def test_persistence_survives_close_and_reopen_including_edges(tmp_path):
    db_path = str(tmp_path / "persist.db")
    goal = make_goal()
    edges = [TaskEdge(from_task_id="g1-t1", to_task_id="g1-t2")]

    client1 = SqliteClient(db_path)
    store1 = TaskGraphStore(client1, PlanningConfig())
    store1.start()
    store1.save_goal(goal)
    store1.save_edges(goal.goal_id, edges)
    store1.stop()

    client2 = SqliteClient(db_path)
    store2 = TaskGraphStore(client2, PlanningConfig())
    store2.start()
    fetched_goal = store2.get_goal(goal.goal_id)
    fetched_edges = store2.get_edges(goal.goal_id)
    store2.stop()

    assert fetched_goal is not None
    assert fetched_goal.statement == goal.statement
    assert len(fetched_goal.milestones) == len(goal.milestones)
    assert fetched_edges == edges


# --- health_check() -----------------------------------------------------------------------


def test_health_check_false_before_start(tmp_path):
    client = SqliteClient(str(tmp_path / "hc.db"))
    store = TaskGraphStore(client, PlanningConfig())
    assert store.health_check() is False


def test_health_check_true_after_start(store):
    assert store.health_check() is True


# --- Sprint 6.14 hardening (scenario b): SQLite read failures ---------------------------------


class _RaisingSqliteClient(SqliteClient):
    """Matches the project's established "_Raising*-style local test
    double" pattern (tests/unit/scheduler/test_calendar_store.py et al.)
    — a real SqliteClient whose query() can be switched to fail on
    demand, after start() has already succeeded."""

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.raise_on_query = False

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self.raise_on_query:
            raise RuntimeError("sqlite query exploded")
        return super().query(sql, params)


def test_list_goals_degrades_to_empty_list_on_a_sqlite_read_failure(tmp_path):
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    task_graph_store = TaskGraphStore(client, PlanningConfig())
    task_graph_store.start()
    try:
        task_graph_store.save_goal(make_goal())
        client.raise_on_query = True

        assert task_graph_store.list_goals() == []
        assert task_graph_store.list_goals(status=PlanningStatus.ACCEPTED) == []
    finally:
        client.raise_on_query = False
        task_graph_store.stop()


def test_get_edges_degrades_to_empty_list_on_a_sqlite_read_failure(tmp_path):
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    task_graph_store = TaskGraphStore(client, PlanningConfig())
    task_graph_store.start()
    try:
        goal = make_goal()
        task_graph_store.save_goal(goal)
        task_graph_store.save_edges(
            goal.goal_id, [TaskEdge(from_task_id="g1-t1", to_task_id="g1-t2")]
        )
        client.raise_on_query = True

        assert task_graph_store.get_edges(goal.goal_id) == []
    finally:
        client.raise_on_query = False
        task_graph_store.stop()
