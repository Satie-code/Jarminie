"""Task Graph Store — persistent CRUD for Goal/Milestone/Task/TaskEdge.
See docs/sprint_book/sprint_6/sprint_6_2.md.

Owns its own four-table DDL (goals, milestones, tasks, task_edges)
against the shared SqliteClient, following WorkflowStore's (4.9) own
"caller owns its own DDL" precedent — no second database-access layer
invented. save_goal() replaces a goal's own milestone/task rows wholesale
(delete-then-reinsert) rather than diffing, the identical "no versioning,
save() overwrites outright" shape WorkflowStore.save() already
established for its own one-to-many workflow/step relationship, scaled
here to a three-level goal/milestone/task hierarchy plus a separate
edges table.

Deliberately NOT given Fail Gracefully hardening this sprint — matching
CalendarStore's/UsageStore's identical precedent (no real caller exists
yet to meaningfully degrade for); Sprint 6.14's job once Sprint 6.9/6.13
give this store real callers.
"""

from __future__ import annotations

from datetime import datetime

from config.schema import PlanningConfig
from core.logging_setup import get_logger
from database.sqlite_client import SqliteClient
from planning.planning_model import Goal, Milestone, PlanningStatus, Task
from planning.task_graph import TaskEdge

logger = get_logger(__name__)

_CREATE_GOALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS goals (
    goal_id TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL
)
"""

_CREATE_MILESTONES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_id TEXT NOT NULL UNIQUE,
    goal_id TEXT NOT NULL,
    milestone_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL
)
"""

_CREATE_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL UNIQUE,
    milestone_id TEXT NOT NULL,
    task_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    estimated_effort TEXT,
    status TEXT NOT NULL
)
"""

_CREATE_TASK_EDGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id TEXT NOT NULL,
    from_task_id TEXT NOT NULL,
    to_task_id TEXT NOT NULL
)
"""


class TaskGraphStore:
    """Constructor DI: (sqlite_client, planning_config)."""

    def __init__(self, sqlite_client: SqliteClient, planning_config: PlanningConfig) -> None:
        self._sqlite_client = sqlite_client
        self._config = planning_config
        self._started = False

    def start(self) -> None:
        self._sqlite_client.connect()
        self._sqlite_client.execute(_CREATE_GOALS_TABLE_SQL)
        self._sqlite_client.execute(_CREATE_MILESTONES_TABLE_SQL)
        self._sqlite_client.execute(_CREATE_TASKS_TABLE_SQL)
        self._sqlite_client.execute(_CREATE_TASK_EDGES_TABLE_SQL)
        self._started = True
        logger.info("Task graph store started.")

    def stop(self) -> None:
        self._sqlite_client.close()
        self._started = False
        logger.info("Task graph store stopped.")

    def health_check(self) -> bool:
        if not self._started:
            return False
        try:
            self._sqlite_client.query("SELECT 1")
            return True
        except Exception:
            logger.exception("Task graph store health check query failed.")
            return False

    def save_goal(self, goal: Goal) -> None:
        self._sqlite_client.execute(
            "INSERT OR REPLACE INTO goals (goal_id, statement, created_at, status) "
            "VALUES (?, ?, ?, ?)",
            (goal.goal_id, goal.statement, goal.created_at.isoformat(), goal.status.value),
        )
        existing_milestone_rows = self._sqlite_client.query(
            "SELECT milestone_id FROM milestones WHERE goal_id = ?", (goal.goal_id,)
        )
        for (milestone_id,) in existing_milestone_rows:
            self._sqlite_client.execute(
                "DELETE FROM tasks WHERE milestone_id = ?", (milestone_id,)
            )
        self._sqlite_client.execute(
            "DELETE FROM milestones WHERE goal_id = ?", (goal.goal_id,)
        )

        for milestone_index, milestone in enumerate(goal.milestones):
            self._sqlite_client.execute(
                "INSERT INTO milestones "
                "(milestone_id, goal_id, milestone_index, title, status) VALUES (?, ?, ?, ?, ?)",
                (
                    milestone.milestone_id,
                    goal.goal_id,
                    milestone_index,
                    milestone.title,
                    milestone.status.value,
                ),
            )
            for task_index, task in enumerate(milestone.tasks):
                self._sqlite_client.execute(
                    "INSERT INTO tasks (task_id, milestone_id, task_index, title, description, "
                    "estimated_effort, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        task.task_id,
                        milestone.milestone_id,
                        task_index,
                        task.title,
                        task.description,
                        task.estimated_effort,
                        task.status.value,
                    ),
                )

    def get_goal(self, goal_id: str) -> Goal | None:
        rows = self._sqlite_client.query(
            "SELECT goal_id, statement, created_at, status FROM goals WHERE goal_id = ?",
            (goal_id,),
        )
        if not rows:
            return None
        return self._build_goal(rows[0])

    def list_goals(self, status: PlanningStatus | None = None) -> list[Goal]:
        if status is None:
            rows = self._sqlite_client.query(
                "SELECT goal_id, statement, created_at, status FROM goals"
            )
        else:
            rows = self._sqlite_client.query(
                "SELECT goal_id, statement, created_at, status FROM goals WHERE status = ?",
                (status.value,),
            )
        return [self._build_goal(row) for row in rows]

    def save_edges(self, goal_id: str, edges: list[TaskEdge]) -> None:
        self._sqlite_client.execute(
            "DELETE FROM task_edges WHERE goal_id = ?", (goal_id,)
        )
        for edge in edges:
            self._sqlite_client.execute(
                "INSERT INTO task_edges (goal_id, from_task_id, to_task_id) VALUES (?, ?, ?)",
                (goal_id, edge.from_task_id, edge.to_task_id),
            )

    def get_edges(self, goal_id: str) -> list[TaskEdge]:
        """A real, necessary addition beyond this sprint's own literal
        Expected Functions list — the symmetric read counterpart to
        save_edges(), needed to satisfy this sprint's own Acceptance
        Criteria ("A Goal with its full milestone/task/edge structure
        survives a close/reopen cycle... unchanged"), which is otherwise
        unsatisfiable: nothing else in this store can read edges back."""
        rows = self._sqlite_client.query(
            "SELECT from_task_id, to_task_id FROM task_edges WHERE goal_id = ?", (goal_id,)
        )
        return [TaskEdge(from_task_id=row[0], to_task_id=row[1]) for row in rows]

    def _build_goal(self, row: tuple) -> Goal:
        goal_id, statement, created_at, status = row
        milestone_rows = self._sqlite_client.query(
            "SELECT milestone_id, title, status FROM milestones WHERE goal_id = ? "
            "ORDER BY milestone_index ASC",
            (goal_id,),
        )
        milestones = [self._build_milestone(row) for row in milestone_rows]
        return Goal(
            goal_id=goal_id,
            statement=statement,
            milestones=milestones,
            created_at=datetime.fromisoformat(created_at),
            status=PlanningStatus(status),
        )

    def _build_milestone(self, row: tuple) -> Milestone:
        milestone_id, title, status = row
        task_rows = self._sqlite_client.query(
            "SELECT task_id, title, description, estimated_effort, status FROM tasks "
            "WHERE milestone_id = ? ORDER BY task_index ASC",
            (milestone_id,),
        )
        tasks = [
            Task(
                task_id=task_row[0],
                title=task_row[1],
                description=task_row[2],
                estimated_effort=task_row[3],
                status=PlanningStatus(task_row[4]),
            )
            for task_row in task_rows
        ]
        return Milestone(
            milestone_id=milestone_id, title=title, tasks=tasks, status=PlanningStatus(status)
        )
