"""Workflow Store — persistent CRUD for WorkflowDefinitions. See
docs/sprint_book/sprint_4_9.md.

Owns its own two-table DDL (workflows, workflow_steps) against the
shared SqliteClient, following ConversationSessionStore's (2.7) and
MemoryStore's (3.1) own "caller owns its own DDL" precedent — no second
database-access layer invented. A real one-to-many relationship
(one workflow, many ordered steps): save() replaces a workflow's own
step rows wholesale (delete-then-reinsert) rather than diffing —
matching this sprint's own explicit "no versioning, save() overwrites
outright" Potential Risk, a deliberate scope limit, not an oversight.

Sprint 4.13 (Integration Testing & Level Freeze) adversarial re-read
finding: get()/list_all() now degrade gracefully (None/[]) on a SQLite
failure, matching MemoryStore's own established Fail Gracefully
convention (Sprint 3.14) — these are this class's only two methods with
a real, live production caller today (WorkflowExecutor.run() and
CommunicationPipeline._resolve_workflow_by_name(), respectively; the
former already had a narrower guard of its own from Sprint 4.12, kept
as deliberate defense in depth, not made redundant by this one).
save()/delete()/set_enabled() remain deliberately unhardened — per this
project's own consistently-applied "do not harden speculatively ahead
of a real caller" discipline (see docs/backlog/technical_debt.md items
11/15/17) — since none of the three has any production caller yet; a
workflow-authoring UI/voice surface, whenever it arrives, is what should
finally give them one and prompt the same treatment. See
docs/backlog/technical_debt.md item 27 for the full history of this
finding.
"""

from __future__ import annotations

import json
from datetime import datetime

from config.schema import WorkflowConfig
from core.logging_setup import get_logger
from database.sqlite_client import SqliteClient
from device_control.action_engine import ActionType
from workflow.workflow_model import WorkflowDefinition, WorkflowStep

logger = get_logger(__name__)

_CREATE_WORKFLOWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_enabled INTEGER NOT NULL
)
"""

_CREATE_WORKFLOW_STEPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    continue_on_failure INTEGER NOT NULL,
    description TEXT NOT NULL
)
"""


class WorkflowStore:
    """Constructor DI: (sqlite_client, workflow_config)."""

    def __init__(self, sqlite_client: SqliteClient, workflow_config: WorkflowConfig) -> None:
        self._sqlite_client = sqlite_client
        self._config = workflow_config
        self._started = False

    def start(self) -> None:
        self._sqlite_client.connect()
        self._sqlite_client.execute(_CREATE_WORKFLOWS_TABLE_SQL)
        self._sqlite_client.execute(_CREATE_WORKFLOW_STEPS_TABLE_SQL)
        self._started = True
        logger.info("Workflow store started.")

    def stop(self) -> None:
        self._sqlite_client.close()
        self._started = False
        logger.info("Workflow store stopped.")

    def health_check(self) -> bool:
        if not self._started:
            return False
        try:
            self._sqlite_client.query("SELECT 1")
            return True
        except Exception:
            logger.exception("Workflow store health check query failed.")
            return False

    def save(self, definition: WorkflowDefinition) -> None:
        """Raises ValueError (never persisting anything) if the
        definition exceeds max_steps_per_workflow — a data-integrity
        boundary this store enforces itself, not left to a caller's own
        discipline."""
        if len(definition.steps) > self._config.max_steps_per_workflow:
            raise ValueError(
                f"Workflow {definition.workflow_id!r} has {len(definition.steps)} steps, "
                f"exceeding max_steps_per_workflow ({self._config.max_steps_per_workflow})"
            )
        self._sqlite_client.execute(
            "INSERT OR REPLACE INTO workflows "
            "(workflow_id, name, created_by, created_at, is_enabled) VALUES (?, ?, ?, ?, ?)",
            (
                definition.workflow_id,
                definition.name,
                definition.created_by,
                definition.created_at.isoformat(),
                int(definition.is_enabled),
            ),
        )
        self._sqlite_client.execute(
            "DELETE FROM workflow_steps WHERE workflow_id = ?", (definition.workflow_id,)
        )
        for step in definition.steps:
            self._sqlite_client.execute(
                "INSERT INTO workflow_steps (workflow_id, step_index, action_type, "
                "parameters_json, continue_on_failure, description) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    definition.workflow_id,
                    step.step_index,
                    step.action_type.value,
                    json.dumps(step.parameters),
                    int(step.continue_on_failure),
                    step.description,
                ),
            )

    def get(self, workflow_id: str) -> WorkflowDefinition | None:
        """Sprint 4.13 hardening: a SQLite failure (either this query or
        _build_definition()'s own step-row query) degrades to None — the
        same "nothing found" outcome as a genuinely-missing workflow,
        matching MemoryStore.get_by_id()'s own established convention.
        WorkflowExecutor.run()'s own Sprint 4.12 guard around this call
        remains in place as deliberate defense in depth, not made
        redundant by this one — see workflow_executor.py's own
        docstring."""
        try:
            rows = self._sqlite_client.query(
                "SELECT workflow_id, name, created_by, created_at, is_enabled "
                "FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            )
            if not rows:
                return None
            return self._build_definition(rows[0])
        except Exception:
            logger.exception("Failed to read workflow %s; treating as not found.", workflow_id)
            return None

    def list_all(self) -> list[WorkflowDefinition]:
        """Sprint 4.13 hardening: a SQLite failure degrades to an empty
        list — CommunicationPipeline._resolve_workflow_by_name() (this
        method's only real caller today) already treats "no match" as a
        normal, reportable outcome ("I couldn't find a workflow named
        ..."), so this closes a real, previously-unguarded gap without
        changing that caller's own behavior at all."""
        try:
            rows = self._sqlite_client.query(
                "SELECT workflow_id, name, created_by, created_at, is_enabled FROM workflows"
            )
            return [self._build_definition(row) for row in rows]
        except Exception:
            logger.exception("Failed to list workflows.")
            return []

    def delete(self, workflow_id: str) -> bool:
        if self.get(workflow_id) is None:
            return False
        self._sqlite_client.execute(
            "DELETE FROM workflows WHERE workflow_id = ?", (workflow_id,)
        )
        self._sqlite_client.execute(
            "DELETE FROM workflow_steps WHERE workflow_id = ?", (workflow_id,)
        )
        return True

    def set_enabled(self, workflow_id: str, is_enabled: bool) -> bool:
        if self.get(workflow_id) is None:
            return False
        self._sqlite_client.execute(
            "UPDATE workflows SET is_enabled = ? WHERE workflow_id = ?",
            (int(is_enabled), workflow_id),
        )
        return True

    def _build_definition(self, row: tuple) -> WorkflowDefinition:
        workflow_id, name, created_by, created_at, is_enabled = row
        step_rows = self._sqlite_client.query(
            "SELECT step_index, action_type, parameters_json, continue_on_failure, description "
            "FROM workflow_steps WHERE workflow_id = ? ORDER BY step_index ASC",
            (workflow_id,),
        )
        steps = [
            WorkflowStep(
                step_index=step_row[0],
                action_type=ActionType(step_row[1]),
                parameters=json.loads(step_row[2]),
                continue_on_failure=bool(step_row[3]),
                description=step_row[4],
            )
            for step_row in step_rows
        ]
        return WorkflowDefinition(
            workflow_id=workflow_id,
            name=name,
            steps=steps,
            created_by=created_by,
            created_at=datetime.fromisoformat(created_at),
            is_enabled=bool(is_enabled),
        )
