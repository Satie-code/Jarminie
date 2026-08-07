"""Planning Engine data model — the Goal -> Milestone -> Task decomposition
Sprint 6.1's PlanningEngine produces. See
docs/sprint_book/sprint_6/sprint_6_1.md.

Every level shares one PlanningStatus vocabulary. This sprint only ever
constructs PROPOSED instances — Sprint 6.2's TaskGraph is what actually
transitions a Task through ACCEPTED/IN_PROGRESS/COMPLETED/ABANDONED.

Task is deliberately NOT typed against device_control/action_engine.py's
ActionType — a freshly-decomposed Task is a human-readable intention, not
yet a dispatchable ActionRequest. Translating one into the other is
Sprint 6.9's own job (workflow/task_graph_adapter.py), mirroring how
workflow/workflow_model.py's own docstring already describes translating
a WorkflowStep into an ActionRequest as "a one-line operation," not a
first-class model concern.

Field order below places every required field before any defaulted one,
a plain Python dataclass necessity — the Sprint Book's own prose lists
Goal's fields in a different order (status before created_at) that is
not valid as literal declaration order; the set of fields, types, and
defaults is unchanged, only the declaration order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PlanningStatus(Enum):
    """Shared lifecycle vocabulary for Goal/Milestone/Task alike."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass
class Task:
    """estimated_effort is a short human phrase (e.g. "15 minutes"),
    deliberately not a typed duration — the LLM's own effort estimate is
    a rough hint, not a scheduling commitment."""

    task_id: str
    title: str
    description: str
    estimated_effort: str | None = None
    status: PlanningStatus = PlanningStatus.PROPOSED


@dataclass
class Milestone:
    milestone_id: str
    title: str
    tasks: list[Task]
    status: PlanningStatus = PlanningStatus.PROPOSED


@dataclass
class Goal:
    """statement is the user's own original phrasing, preserved verbatim
    — the Human First Rule applied to planning: JARMINEI's own
    decomposition never overwrites what the user actually asked for."""

    goal_id: str
    statement: str
    milestones: list[Milestone]
    created_at: datetime
    status: PlanningStatus = PlanningStatus.PROPOSED
