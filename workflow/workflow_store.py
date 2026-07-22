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

No Fail Gracefully wrapping around SQLite errors here (unlike
ConversationSessionStore/ActionAuditLog, which already went through
their own dedicated hardening passes) — this sprint's own Implementation
Tasks name only the max_steps_per_workflow ValueError as a required
error path; systematic exception hardening across every Level 4 Part A
persistence class is Sprint 4.12's (Error Handling & Recovery Hardening)
job, the same "hardening arrives in its own later sprint" precedent
already established for Level 2 (2.13) and Level 3 (3.13).
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
        rows = self._sqlite_client.query(
            "SELECT workflow_id, name, created_by, created_at, is_enabled "
            "FROM workflows WHERE workflow_id = ?",
            (workflow_id,),
        )
        if not rows:
            return None
        return self._build_definition(rows[0])

    def list_all(self) -> list[WorkflowDefinition]:
        rows = self._sqlite_client.query(
            "SELECT workflow_id, name, created_by, created_at, is_enabled FROM workflows"
        )
        return [self._build_definition(row) for row in rows]

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
