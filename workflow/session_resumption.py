"""Session Resumption — composes Sprint 6.6's Knowledge Graph into a
real WorkflowDefinition for "resume my previous session." See
docs/sprint_book/sprint_6/sprint_6_9.md.

**A query composition, not new storage** — this class invents no
persistence of its own; it finds the most-recently-referenced
EntityType.PROJECT (KnowledgeGraphStore.find_entities(), sorted by
last_referenced_at) and builds ordinary LAUNCH_APPLICATION/OPEN_URL
steps from whatever that project's own related EntityType.FILE entities
describe (via KnowledgeGraphStore.related_entities()). Every
WorkflowDefinition this class produces still goes through
WorkflowExecutor.run()'s own completely unchanged permission/
confirmation/audit pipeline — see task_graph_adapter.py's own docstring
for the identical "translation layer, never a second execution path"
boundary, which applies here just as directly.

**Only EntityType.FILE entities become steps.** related_entities() can
return any entity type via any RelationshipType — this sprint's own
Expected Functions text names only a FILE-PART_OF-PROJECT example, with
no textual basis for what action a PERSON/GOAL/TOPIC/PROJECT relation
would dispatch as; scoping to FILE (LAUNCH_APPLICATION if the entity's
own name isn't URL-shaped, OPEN_URL if it is) is a deliberate, disclosed
narrowing, not an oversight.

**A real, disclosed "accepted but not yet consumed" constructor
collaborator, the same pattern this Sprint Book has now established
repeatedly**: context_engine is required per this sprint's own literal
Expected Classes signature, but no method in this class's own Expected
Functions text calls it — build_workflow()'s own described logic is
entirely knowledge_graph_store-driven. Stored, not called, disclosed
here rather than invented a use for it.

**No PROJECT entity found returns None, never a fabricated workflow**
— an honest "there is no previous session to resume." A PROJECT entity
that exists but has zero related FILE entities returns a real,
genuinely empty-of-steps WorkflowDefinition instead — the project WAS
found, it simply has nothing concrete yet to resume; inventing a fake
placeholder step just to make it non-empty would be the same kind of
fabrication the Human First Rule already rules out elsewhere in this
codebase (e.g. context/context_engine.py's own None-vs-[] degrade
discipline, Sprint 6.3).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from config.schema import WorkflowConfig
from device_control.action_engine import ActionType
from knowledge.knowledge_model import Entity, EntityType
from workflow.workflow_model import WorkflowDefinition, WorkflowStep

if TYPE_CHECKING:
    from context.context_engine import ContextEngine
    from knowledge.knowledge_graph_store import KnowledgeGraphStore

_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
"""A small, disclosed duplicate of workflow/task_graph_adapter.py's own
identical pattern — kept local rather than importing that module's
private constant across a module boundary, matching this codebase's own
"never import an underscore-prefixed symbol by name" convention."""


def _classify_entity(entity: Entity) -> tuple[ActionType, dict[str, object]]:
    if _URL_PATTERN.search(entity.name):
        return ActionType.OPEN_URL, {"url": entity.name}
    return ActionType.LAUNCH_APPLICATION, {"executable_path": entity.name}


class SessionResumption:
    """Constructor DI: (knowledge_graph_store, context_engine,
    workflow_config). Not a ManagedModule — no lifecycle of its own,
    matching TaskGraphWorkflowAdapter's identical shape."""

    def __init__(
        self,
        knowledge_graph_store: KnowledgeGraphStore,
        context_engine: ContextEngine,
        workflow_config: WorkflowConfig,
    ) -> None:
        self._knowledge_graph_store = knowledge_graph_store
        self._context_engine = context_engine
        self._config = workflow_config

    def build_workflow(self, created_by: str) -> WorkflowDefinition | None:
        projects = self._knowledge_graph_store.find_entities(entity_type=EntityType.PROJECT)
        if not projects:
            return None
        most_recent_project = max(projects, key=lambda project: project.last_referenced_at)

        related = self._knowledge_graph_store.related_entities(most_recent_project.entity_id)
        file_entities = [entity for entity in related if entity.entity_type is EntityType.FILE]

        now = datetime.now(UTC)
        steps: list[WorkflowStep] = []
        for index, entity in enumerate(file_entities):
            action_type, parameters = _classify_entity(entity)
            steps.append(
                WorkflowStep(
                    step_index=index,
                    action_type=action_type,
                    parameters=parameters,
                    description=f"Resume {entity.name}",
                )
            )
        return WorkflowDefinition(
            workflow_id=str(uuid.uuid4()),
            name=f"Resume session: {most_recent_project.name}",
            steps=steps,
            created_by=created_by,
            created_at=now,
        )
