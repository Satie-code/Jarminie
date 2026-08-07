"""Unit tests for planning.planning_model."""

from datetime import UTC, datetime

from planning.planning_model import Goal, Milestone, PlanningStatus, Task


def test_task_defaults_to_proposed_status_and_no_estimated_effort():
    task = Task(task_id="t1", title="Do the thing", description="A description")

    assert task.status is PlanningStatus.PROPOSED
    assert task.estimated_effort is None


def test_task_can_carry_an_estimated_effort():
    task = Task(task_id="t1", title="Do the thing", description="", estimated_effort="15 minutes")

    assert task.estimated_effort == "15 minutes"


def test_milestone_defaults_to_proposed_status():
    task = Task(task_id="t1", title="A task", description="")
    milestone = Milestone(milestone_id="m1", title="A milestone", tasks=[task])

    assert milestone.status is PlanningStatus.PROPOSED
    assert milestone.tasks == [task]


def test_goal_defaults_to_proposed_status_and_preserves_statement_verbatim():
    task = Task(task_id="t1", title="A task", description="")
    milestone = Milestone(milestone_id="m1", title="A milestone", tasks=[task])
    now = datetime.now(UTC)

    goal = Goal(
        goal_id="g1",
        statement="  Learn to juggle  ",
        milestones=[milestone],
        created_at=now,
    )

    assert goal.status is PlanningStatus.PROPOSED
    assert goal.statement == "  Learn to juggle  "
    assert goal.milestones == [milestone]
    assert goal.created_at == now


def test_planning_status_has_exactly_the_five_expected_members():
    assert {member.value for member in PlanningStatus} == {
        "proposed",
        "accepted",
        "in_progress",
        "completed",
        "abandoned",
    }
