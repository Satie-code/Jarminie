"""Task Graph — Sprint 6.1's flat Goal -> Milestone -> Task tree, turned
into a real graph: dependency edges, parallel-work/blocked queries, and
completion-state cascades. See docs/sprint_book/sprint_6/sprint_6_2.md.

TaskGraph is an in-memory query/mutation layer over one already-built
Goal (mutated in place) plus its own edge list — it never persists
anything itself; TaskGraphStore (task_graph_store.py) owns that. The
same in-memory-representation-over-a-persisted-source split
decision/priority_queue.py's PriorityQueueManager already uses for its
own queue.

Dependency edges are deliberately NOT inferred automatically from a
PlanningEngine decomposition anywhere in this module — the LLM's own
proposed task ordering (if any, expressed only as list order in the
source text) is never parsed into real TaskEdges here. Automatic
dependency inference is real, additional LLM-reasoning work (closer to
Sprint 6.4's Reasoning Engine territory) than a graph-storage concern; a
TaskGraph built directly from a fresh Goal has zero edges (every task
immediately "ready") unless a caller explicitly calls add_dependency().
"""

from __future__ import annotations

from dataclasses import dataclass

from config.schema import PlanningConfig
from planning.errors import CyclicDependencyError
from planning.planning_model import Goal, Milestone, PlanningStatus, Task

_NON_TERMINAL_STATUSES = (PlanningStatus.PROPOSED, PlanningStatus.ACCEPTED)


@dataclass
class TaskEdge:
    """from_task_id is the dependency; to_task_id is the dependent task —
    it cannot run until from_task_id is COMPLETED."""

    from_task_id: str
    to_task_id: str


class TaskGraph:
    """Constructed from one Goal (mutated in place by mark_completed()/
    mark_failed()) plus an optional initial edge list — the shape a
    caller reconstructing a graph from TaskGraphStore.get_goal()/
    get_edges() would pass in. planning_config is accepted beyond this
    sprint's own literal "constructed from one Goal" Expected Classes
    description — add_dependency()'s own max_task_dependencies bound
    (config/schema.py's PlanningConfig) needs somewhere to read that
    bound from, and TaskGraph is the only class that enforces it; a
    real, necessary, disclosed addition, defaulting to PlanningConfig()
    so a caller that doesn't care about tuning it needs no ceremony."""

    def __init__(
        self,
        goal: Goal,
        edges: list[TaskEdge] | None = None,
        planning_config: PlanningConfig | None = None,
    ) -> None:
        self._goal = goal
        self._edges: list[TaskEdge] = list(edges) if edges else []
        self._planning_config = planning_config or PlanningConfig()
        self._tasks_by_id: dict[str, Task] = {}
        self._milestone_by_task_id: dict[str, Milestone] = {}
        for milestone in goal.milestones:
            for task in milestone.tasks:
                self._tasks_by_id[task.task_id] = task
                self._milestone_by_task_id[task.task_id] = milestone

    @property
    def goal(self) -> Goal:
        return self._goal

    @property
    def edges(self) -> list[TaskEdge]:
        return list(self._edges)

    def add_dependency(self, from_task_id: str, to_task_id: str) -> None:
        """Raises ValueError for an unknown task_id or a bound-exceeding
        request, CyclicDependencyError for a request that would create a
        cycle (direct or transitive) — a real depth-first-search check,
        not a heuristic. Never partially applies a rejected edge: every
        check runs before self._edges is mutated."""
        if from_task_id not in self._tasks_by_id:
            raise ValueError(f"Unknown task_id in add_dependency(): {from_task_id!r}")
        if to_task_id not in self._tasks_by_id:
            raise ValueError(f"Unknown task_id in add_dependency(): {to_task_id!r}")

        incoming_count = sum(1 for edge in self._edges if edge.to_task_id == to_task_id)
        if incoming_count >= self._planning_config.max_task_dependencies:
            raise ValueError(
                f"Task {to_task_id!r} already has {incoming_count} dependencies, at the "
                f"configured maximum (max_task_dependencies="
                f"{self._planning_config.max_task_dependencies})"
            )

        if self._can_reach(to_task_id, from_task_id):
            raise CyclicDependencyError(
                f"Adding a dependency from {from_task_id!r} to {to_task_id!r} would create "
                "a cycle."
            )
        self._edges.append(TaskEdge(from_task_id=from_task_id, to_task_id=to_task_id))

    def ready_tasks(self) -> list[Task]:
        """Every non-terminal Task whose every incoming TaskEdge points
        at an already-COMPLETED task. Two or more ready tasks with no
        edge between them are real, honest parallel-work candidates —
        never ordered relative to each other."""
        return [
            task
            for task in self._tasks_by_id.values()
            if task.status in _NON_TERMINAL_STATUSES and not self._is_blocked(task.task_id)
        ]

    def blocked_tasks(self) -> list[Task]:
        """The exact complement of ready_tasks() among non-terminal
        tasks."""
        return [
            task
            for task in self._tasks_by_id.values()
            if task.status in _NON_TERMINAL_STATUSES and self._is_blocked(task.task_id)
        ]

    def mark_completed(self, task_id: str) -> None:
        """Cascades: every sibling Task in the owning Milestone COMPLETED
        moves that Milestone to COMPLETED; every Milestone in the Goal
        COMPLETED moves the Goal to COMPLETED — derived state recomputed
        from real children, never a separately-settable flag that could
        disagree (wellness/escalation.py's is_hard_limited() precedent,
        Sprint 5.19)."""
        task = self._require_task(task_id)
        task.status = PlanningStatus.COMPLETED
        milestone = self._milestone_by_task_id[task_id]
        if all(t.status is PlanningStatus.COMPLETED for t in milestone.tasks):
            milestone.status = PlanningStatus.COMPLETED
            if all(m.status is PlanningStatus.COMPLETED for m in self._goal.milestones):
                self._goal.status = PlanningStatus.COMPLETED

    def mark_failed(self, task_id: str) -> None:
        """Sets only the Task's own status to ABANDONED (PlanningStatus
        has no separate FAILED member) — deliberately does NOT cascade
        upward. A failed task blocks its own dependents mechanically via
        blocked_tasks() (its status never reaches COMPLETED), but a
        Milestone/Goal is never auto-marked ABANDONED — that is a human
        or Sprint 6.10 (Self Evaluation) judgment call, not a mechanical
        one."""
        task = self._require_task(task_id)
        task.status = PlanningStatus.ABANDONED

    def _is_blocked(self, task_id: str) -> bool:
        for edge in self._edges:
            if edge.to_task_id != task_id:
                continue
            prerequisite = self._tasks_by_id.get(edge.from_task_id)
            if prerequisite is not None and prerequisite.status is not PlanningStatus.COMPLETED:
                return True
        return False

    def _can_reach(self, start: str, target: str) -> bool:
        """True if target is reachable from start by following existing
        from_task_id -> to_task_id edges forward — used to detect
        whether a new from_task_id -> to_task_id edge would close a
        cycle (a path already exists back from to_task_id to
        from_task_id)."""
        visited: set[str] = set()
        stack = [start]
        while stack:
            current = stack.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            for edge in self._edges:
                if edge.from_task_id == current:
                    stack.append(edge.to_task_id)
        return False

    def _require_task(self, task_id: str) -> Task:
        task = self._tasks_by_id.get(task_id)
        if task is None:
            raise ValueError(f"Unknown task_id: {task_id!r}")
        return task
