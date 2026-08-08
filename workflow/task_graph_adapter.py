"""Task Graph Workflow Adapter — translates a Task Graph's own currently-
runnable tasks into a real, dispatchable WorkflowDefinition the existing
WorkflowExecutor can run unchanged. See
docs/sprint_book/sprint_6/sprint_6_9.md.

**Extends workflow/, does not fork it.** WorkflowExecutor/WorkflowStore/
WorkflowDefinition/WorkflowStep (Sprint 4.9/4.10) are untouched — this
class only adds a new *source* of a WorkflowDefinition beyond hand-
authoring. Every WorkflowDefinition build_workflow() produces still goes
through WorkflowExecutor.run()'s own completely unchanged permission/
confirmation/audit pipeline (PermissionPolicyEngine, ConfirmationService,
ActionAuditLog) — this is a translation layer, never a second execution
path that could bypass Level 4 Part A's own already-hardened safety
machinery.

**The keyword classifier is deliberately small and literal, not a
second reasoning pass** — a Task.title is already human-authored
(LLM-decomposed, Sprint 6.1) text, not raw conversational input, so the
same lighter-weight classification discipline decision/authority.py's
own keyword tuples use for similarly-already-structured input is the
right level of machinery here, not ReasoningEngine. An unclassifiable
title falls back to ActionType.SYSTEM_COMMAND (using the task's own
title as a literal command) — a deliberate, disclosed choice: a
SYSTEM_COMMAND step is inert by default (DeviceControlConfig.
approved_commands ships empty), so a misclassified fallback's worst
case is "does nothing until explicitly approved," never "silently does
something risky." This is the identical "SYSTEM_COMMAND steps derived
from a Task Graph are inert by default" consequence this sprint's own
Potential Risks already names for the brief's own "Pull Git repository"
worked example — an unclassifiable task inherits that same honest gate.

**A real, disclosed limitation**: the classifier's own generated
`parameters` (e.g. `executable_path`/`command` set directly from
Task.title/description text) are not resolved into a real, launchable
path or verified command — Task.title is a human phrase ("Open VS
Code"), not necessarily a literal executable path. Resolving a human
description into a real, dispatchable parameter is out of this sprint's
own scope (no textual basis names it); a generated LAUNCH_APPLICATION
step may well fail with FileNotFoundError at real dispatch time, an
honest, disclosed gap rather than a fabricated success.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from config.schema import WorkflowConfig
from device_control.action_engine import ActionContext, ActionRequest, ActionType
from workflow.workflow_model import WorkflowDefinition, WorkflowStep

if TYPE_CHECKING:
    from decision.decision_engine_v2 import DecisionEngineV2
    from planning.planning_model import Task
    from planning.task_graph import TaskGraph

_LAUNCH_KEYWORDS = ("open", "launch")
_COMMAND_KEYWORDS = ("pull", "run", "execute")
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


def _classify(task: Task) -> tuple[ActionType, dict[str, object]]:
    """A small, literal keyword-to-ActionType mapping over Task.title +
    Task.description combined — see this module's own docstring for why
    this is the right level of machinery, and for the disclosed fallback
    (SYSTEM_COMMAND, inert by default) when nothing matches."""
    combined_text = f"{task.title} {task.description}"
    url_match = _URL_PATTERN.search(combined_text)
    if url_match:
        return ActionType.OPEN_URL, {"url": url_match.group(0)}

    lowered = combined_text.lower()
    if any(keyword in lowered for keyword in _LAUNCH_KEYWORDS):
        return ActionType.LAUNCH_APPLICATION, {"executable_path": task.title}
    if any(keyword in lowered for keyword in _COMMAND_KEYWORDS):
        return ActionType.SYSTEM_COMMAND, {"command": [task.title]}
    return ActionType.SYSTEM_COMMAND, {"command": [task.title]}


class TaskGraphWorkflowAdapter:
    """Constructor DI: (decision_engine_v2, workflow_config). Not a
    ManagedModule — no lifecycle of its own, matching WorkflowExecutor's
    own "orchestrates already lifecycle-managed collaborators" shape."""

    def __init__(
        self, decision_engine_v2: DecisionEngineV2, workflow_config: WorkflowConfig
    ) -> None:
        self._decision_engine_v2 = decision_engine_v2
        self._config = workflow_config

    def build_workflow(self, task_graph: TaskGraph, created_by: str) -> WorkflowDefinition:
        """Classifies each of task_graph.ready_tasks() (bounded to
        workflow_config.max_steps_from_task_graph) into a candidate
        ActionRequest, ranks them via decision_engine_v2.rank_actions(),
        and emits one WorkflowStep per candidate in ranked order — each
        step's own description copied from the originating Task.title,
        preserving the Explainability Rule's existing "step description
        is human-readable" property workflow/workflow_model.py already
        established."""
        tasks = task_graph.ready_tasks()[: self._config.max_steps_from_task_graph]
        now = datetime.now(UTC)

        task_by_request_id: dict[int, Task] = {}
        candidates: list[ActionRequest] = []
        for task in tasks:
            action_type, parameters = _classify(task)
            request = ActionRequest(
                action_type=action_type,
                parameters=parameters,
                context=ActionContext(requested_by=created_by),
                requested_at=now,
            )
            candidates.append(request)
            task_by_request_id[id(request)] = task

        ranked = self._decision_engine_v2.rank_actions(candidates)

        steps = [
            WorkflowStep(
                step_index=index,
                action_type=ranked_action.action_request.action_type,
                parameters=ranked_action.action_request.parameters,
                description=task_by_request_id[id(ranked_action.action_request)].title,
            )
            for index, ranked_action in enumerate(ranked)
        ]
        return WorkflowDefinition(
            workflow_id=str(uuid.uuid4()),
            name=f"Plan: {task_graph.goal.statement}",
            steps=steps,
            created_by=created_by,
            created_at=now,
        )
