"""Workflow Executor — runs a stored WorkflowDefinition (Sprint 4.9)
step by step through the Action Engine (Sprint 4.1) and its full
permission/resource/audit stack (Sprints 4.6-4.8). See
docs/sprint_book/sprint_4_10.md.

WorkflowExecutor never calls any concrete executor (ApplicationManager,
FileOperationsManager, etc.) directly and never constructs its own
PermissionGate/ActionResourceGate/ActionAuditLog — it holds only an
ActionRegistry and calls dispatch(), exactly like any other caller. This
is a hard architectural invariant, not just a convenience: a workflow is
not a privileged execution path, it is simply a caller that happens to
issue several ActionRequests in sequence — the same safety guarantees
Sprint 4.1 built apply uniformly, with no special-cased bypass anywhere.

Two different confirmation questions, both real, neither suppressing the
other: this module's own _maybe_request_whole_workflow_confirmation()
asks "should this whole sequence run at all" once, before any step
starts; PermissionGate.check() (Sprint 4.7), consulted independently by
ActionRegistry.dispatch() for every single step, keeps asking "should
this specific step run" exactly as it would for any other caller. A step
individually classified MEDIUM/HIGH risk still triggers its own Sprint
4.7 confirmation during dispatch() regardless of whether the
whole-workflow prompt already ran.

Known gap, not fixed here (out of this sprint's own scope): the
whole-workflow ConfirmationRequest's prompt_text is built from
WorkflowConfig.large_workflow_confirmation_prompt_template (naming the
workflow, step count, and higher-risk step count), but
VoiceConfirmationService.request_confirmation() (security/
confirmation_service.py, Sprint 4.7) deliberately ignores
ConfirmationRequest.prompt_text and rebuilds its own spoken text from
ConfirmationRequest.action_request/risk_level via build_prompt_text() —
by design, per that module's own docstring ("rather than trusting a
possibly-generic prompt_text unconditionally"). Since the pseudo
ActionRequest built for the whole-workflow prompt is a WORKFLOW_STEP
action with no per-workflow description template in
security/confirmation_service.py's own _ACTION_DESCRIPTIONS, a real
voice-spoken whole-workflow prompt currently degrades to the generic
"This will run a workflow step. Should I proceed?" rather than the
richer template text — prompt_text itself is still correctly built and
is exactly what a future non-voice (e.g. UI dialog) ConfirmationService
implementation would use verbatim. Changing VoiceConfirmationService's
own already-shipped, already-tested behavior is a Sprint 4.7 concern, not
this sprint's own Files to Modify — see docs/backlog/technical_debt.md
item 25.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.logging_setup import get_logger
from device_control.action_engine import (
    ActionContext,
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)
from security.confirmation_service import ConfirmationOutcome, ConfirmationRequest
from security.policy_engine import RiskLevel

if TYPE_CHECKING:
    from config.schema import WorkflowConfig
    from device_control.action_engine import ActionRegistry
    from security.confirmation_service import ConfirmationService
    from security.policy_engine import PermissionPolicyEngine
    from workflow.workflow_model import WorkflowDefinition, WorkflowStep
    from workflow.workflow_store import WorkflowStore

logger = get_logger(__name__)

_ABORTED_CONFIRMATION_OUTCOMES = frozenset(
    {ConfirmationOutcome.DECLINED, ConfirmationOutcome.TIMED_OUT}
)


@dataclass
class WorkflowStepResult:
    """skipped=True means this step was never dispatched at all — a
    prior non-continue_on_failure step already aborted the run before
    this step's turn came up. action_result is still a real, well-formed
    ActionResult even for a skipped step (status=PENDING, an explanatory
    error_message) rather than None, so a caller inspecting
    WorkflowRunResult never needs a None-check per step to know exactly
    what happened."""

    step_index: int
    action_result: ActionResult
    skipped: bool


@dataclass
class WorkflowRunResult:
    """whole_workflow_confirmation is None specifically when no
    whole-workflow prompt was warranted (small, low-risk workflow) — not
    conflated with a real DECLINED/TIMED_OUT outcome, so a caller can
    always tell "no prompt needed" apart from "a prompt fired and was
    refused"."""

    workflow_id: str
    run_id: str
    step_results: list[WorkflowStepResult]
    aborted_early: bool
    whole_workflow_confirmation: ConfirmationOutcome | None
    started_at: datetime
    completed_at: datetime


class WorkflowExecutor:
    """Constructor DI: (workflow_store, action_registry,
    permission_policy_engine, confirmation_service, workflow_config). Not
    a ManagedModule — no lifecycle of its own, it orchestrates already
    lifecycle-managed collaborators, the same reasoning
    MemoryRetrievalEngine/ContextManager established."""

    def __init__(
        self,
        workflow_store: WorkflowStore,
        action_registry: ActionRegistry,
        permission_policy_engine: PermissionPolicyEngine,
        confirmation_service: ConfirmationService,
        workflow_config: WorkflowConfig,
    ) -> None:
        self._workflow_store = workflow_store
        self._action_registry = action_registry
        self._permission_policy_engine = permission_policy_engine
        self._confirmation_service = confirmation_service
        self._workflow_config = workflow_config

    def run(self, workflow_id: str, context: ActionContext) -> WorkflowRunResult:
        started_at = datetime.now(UTC)
        run_id = str(uuid.uuid4())

        definition = self._workflow_store.get(workflow_id)
        if definition is None:
            logger.warning("WorkflowExecutor.run(): workflow %s does not exist.", workflow_id)
            return self._aborted_result(workflow_id, run_id, started_at, None)
        if not definition.is_enabled:
            logger.info(
                "WorkflowExecutor.run(): workflow %s is disabled; refusing to run.", workflow_id
            )
            return self._aborted_result(workflow_id, run_id, started_at, None)

        confirmation_outcome = self._maybe_request_whole_workflow_confirmation(definition)
        if confirmation_outcome in _ABORTED_CONFIRMATION_OUTCOMES:
            logger.info(
                "WorkflowExecutor.run(): whole-workflow confirmation for %s was %s; "
                "aborting before any step runs.",
                workflow_id,
                confirmation_outcome.value,
            )
            return self._aborted_result(workflow_id, run_id, started_at, confirmation_outcome)

        step_results: list[WorkflowStepResult] = []
        aborted_early = False
        for step in definition.steps:
            request = self._build_step_request(step, workflow_id, context)

            if aborted_early:
                step_results.append(
                    WorkflowStepResult(
                        step_index=step.step_index,
                        action_result=ActionResult(
                            request=request,
                            status=ActionStatus.PENDING,
                            completed_at=datetime.now(UTC),
                            error_message=(
                                "Skipped: a prior step aborted this workflow run."
                            ),
                        ),
                        skipped=True,
                    )
                )
                continue

            result = self._action_registry.dispatch(request)
            step_results.append(
                WorkflowStepResult(step_index=step.step_index, action_result=result, skipped=False)
            )

            if (
                result.status in (ActionStatus.FAILED, ActionStatus.DENIED)
                and not step.continue_on_failure
            ):
                aborted_early = True

        return WorkflowRunResult(
            workflow_id=workflow_id,
            run_id=run_id,
            step_results=step_results,
            aborted_early=aborted_early,
            whole_workflow_confirmation=confirmation_outcome,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )

    def _maybe_request_whole_workflow_confirmation(
        self, definition: WorkflowDefinition
    ) -> ConfirmationOutcome | None:
        step_count = len(definition.steps)
        high_risk_count = sum(
            1
            for step in definition.steps
            if self._permission_policy_engine.classify(step.action_type).risk_level
            is RiskLevel.HIGH
        )

        if (
            step_count < self._workflow_config.large_workflow_step_threshold
            and high_risk_count == 0
        ):
            return None

        prompt_text = self._workflow_config.large_workflow_confirmation_prompt_template.format(
            name=definition.name,
            step_count=step_count,
            high_risk_count=high_risk_count,
        )
        pseudo_request = ActionRequest(
            action_type=ActionType.WORKFLOW_STEP,
            parameters={
                "workflow_id": definition.workflow_id,
                "name": definition.name,
                "step_count": step_count,
            },
            context=ActionContext(requested_by=f"workflow:{definition.workflow_id}"),
            requested_at=datetime.now(UTC),
        )
        confirmation_request = ConfirmationRequest(
            action_request=pseudo_request,
            risk_level=RiskLevel.HIGH if high_risk_count > 0 else RiskLevel.MEDIUM,
            prompt_text=prompt_text,
        )
        outcome = self._confirmation_service.request_confirmation(confirmation_request)
        logger.info(
            "Whole-workflow confirmation for %s (%d steps, %d high-risk): %s",
            definition.workflow_id,
            step_count,
            high_risk_count,
            outcome.value,
        )
        return outcome

    def _build_step_request(
        self, step: WorkflowStep, workflow_id: str, base_context: ActionContext
    ) -> ActionRequest:
        step_context = ActionContext(
            requested_by=f"workflow:{workflow_id}",
            persona_name=base_context.persona_name,
            session_id=base_context.session_id,
            decision_trace=base_context.decision_trace,
        )
        return ActionRequest(
            action_type=step.action_type,
            parameters=step.parameters,
            context=step_context,
            requested_at=datetime.now(UTC),
        )

    def _aborted_result(
        self,
        workflow_id: str,
        run_id: str,
        started_at: datetime,
        confirmation_outcome: ConfirmationOutcome | None,
    ) -> WorkflowRunResult:
        return WorkflowRunResult(
            workflow_id=workflow_id,
            run_id=run_id,
            step_results=[],
            aborted_early=True,
            whole_workflow_confirmation=confirmation_outcome,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
