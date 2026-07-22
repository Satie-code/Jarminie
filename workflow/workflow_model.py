"""Workflow Builder — the Workflow Engine's definition model. See
docs/sprint_book/sprint_4_9.md.

WorkflowStep.parameters deliberately mirrors ActionRequest.parameters's
own shape exactly (device_control/action_engine.py) — a WorkflowStep is
not translated into an ActionRequest by any complex mapping logic;
Sprint 4.10's executor constructs an ActionRequest from a WorkflowStep
by copying action_type/parameters directly and wrapping them with a
workflow-specific ActionContext (requested_by = "workflow:<workflow_id>").
Keeping the two shapes deliberately aligned is what makes that
translation a one-line operation rather than its own subsystem.

ActionType is imported only under TYPE_CHECKING — this module holds
ActionType values as plain dataclass fields but never inspects or
constructs one itself; workflow/workflow_store.py is what actually
needs the real enum at runtime (to serialize/deserialize
action_type.value), matching the same TYPE_CHECKING-only discipline
already established for the same reason in security/policy_engine.py
(Sprint 4.7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from device_control.action_engine import ActionType


@dataclass
class WorkflowStep:
    """description is a human-readable label (e.g. "Open project
    folder") — the Explainability Rule applied to a workflow step,
    shown to the user before/during execution, not just in logs."""

    step_index: int
    action_type: ActionType
    parameters: dict[str, object]
    description: str
    continue_on_failure: bool = False


@dataclass
class WorkflowDefinition:
    """is_enabled exists because a workflow, once it can contain
    HIGH-risk steps (Sprint 4.7's classification), is functionally
    closer to a saved, reusable script than a single fire-and-forget
    request — a "pause this without deleting it" affordance is a real
    safety-relevant feature. A disabled workflow can be stored but
    never executed — Sprint 4.10 checks this before running."""

    workflow_id: str
    name: str
    steps: list[WorkflowStep]
    created_by: str
    created_at: datetime
    is_enabled: bool = True
