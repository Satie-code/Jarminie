# Sprint 4.10 — Workflow Executor

## Sprint ID

4.10

## Sprint Name

Workflow Executor

## Purpose

Execute a stored `WorkflowDefinition` (Sprint 4.9) step by step through the Action Engine (Sprint 4.1) and its full permission/resource/audit stack (Sprints 4.6–4.8), with large-workflow confirmation gating — Part 2's own "Large workflow rule: if many actions are about to execute, request confirmation before proceeding," and this task's own "Managing multi-step workflows... Performing automation sequences."

## Engineering Rationale

Corresponds unchanged to `docs/sprint_book/INDEX.md`'s original `4.6 Workflow Executor` roadmap entry in name and core scope, but **absorbs** the original roadmap's separate `4.7 Large-Workflow Confirmation Gate` entry rather than keeping it as its own sprint — see Sprint 4.7's own Engineering Rationale for the full justification (a single, general Permission & Confirmation System built once, at the right layer, rather than a workflow-specific gate duplicating the same "classify risk, ask, honor the answer" logic a second time). This sprint's own job regarding confirmation is narrower and specific to workflows: deciding *when* a whole-workflow-level prompt is warranted (as opposed to Sprint 4.7's per-action prompts, which still apply to each individual step), not re-implementing the underlying confirmation mechanism itself.

Every step's execution reuses `ActionRegistry.dispatch()` exactly as any other Level 4 caller would — `WorkflowExecutor` does not call any executor (`ApplicationManager`, `FileOperationsManager`, etc.) directly, and does not bypass `PermissionGate`/`ActionResourceGate`/`ActionAuditLog` for any step. This is the direct payoff of Sprint 4.1's foundational design: a workflow is not a privileged execution path, it is simply a caller that happens to issue several `ActionRequest`s in sequence — the same safety guarantees apply uniformly, with no special-cased bypass anywhere.

## Objectives

- `WorkflowExecutor.run(workflow_id: str, context: ActionContext) -> WorkflowRunResult`: executes a `WorkflowDefinition`'s steps in order via `ActionRegistry.dispatch()`, respecting each step's `continue_on_failure`.
- A whole-workflow confirmation prompt (via Sprint 4.7's `ConfirmationService`) before execution begins, when the workflow's step count or aggregate risk crosses a configured threshold — Part 2's "large workflow rule," made concrete.
- A `WorkflowRunResult` recording per-step outcomes, so a partially-completed workflow's exact state is always knowable, never ambiguous.

## Dependencies

4.1 (Action Engine Foundation), 4.7 (Permission & Confirmation System), 4.8 (Action Logging & Recovery), 4.9 (Workflow Builder)

## Files to Create

- `workflow/workflow_executor.py` — `WorkflowRunResult` (dataclass), `WorkflowStepResult` (dataclass), `WorkflowExecutor`.
- `tests/unit/workflow/test_workflow_executor.py`

## Files to Modify

- `config/schema.py` — `WorkflowConfig` gains `large_workflow_step_threshold: int = 5` (a workflow with this many steps or more always triggers the whole-workflow confirmation prompt, regardless of individual step risk) and `large_workflow_confirmation_prompt_template: str` (a config-overridable prompt template, e.g. `"This workflow '{name}' will run {step_count} actions, including {high_risk_count} higher-risk steps. Should I proceed?"`).
- `config/defaults.yaml` — matching fields.

## Expected Classes

- `WorkflowStepResult` (dataclass) — `step_index: int`, `action_result: ActionResult`, `skipped: bool` (a step is `skipped`, not attempted at all, if a prior non-`continue_on_failure` step already aborted the run).
- `WorkflowRunResult` (dataclass) — `workflow_id: str`, `run_id: str`, `step_results: list[WorkflowStepResult]`, `aborted_early: bool`, `whole_workflow_confirmation: ConfirmationOutcome | None` (`None` if the workflow was small/low-risk enough that no whole-workflow prompt was triggered), `started_at: datetime`, `completed_at: datetime`.
- `WorkflowExecutor` — constructor DI: `(workflow_store: WorkflowStore, action_registry: ActionRegistry, permission_policy_engine: PermissionPolicyEngine, confirmation_service: ConfirmationService, workflow_config: WorkflowConfig)`. Not a `ManagedModule` (no lifecycle of its own — it orchestrates already-lifecycle-managed collaborators, the same reasoning `MemoryRetrievalEngine`/`ContextManager` established).

## Expected Interfaces

None new — depends entirely on Sprints 4.1, 4.7, 4.9's existing interfaces.

## Expected Functions

- `WorkflowExecutor.run(workflow_id: str, context: ActionContext) -> WorkflowRunResult` — loads the definition via `workflow_store.get()`; returns immediately with an empty, `aborted_early=True` result if `is_enabled` is `False` or the workflow doesn't exist (never silently no-ops without a reportable reason); calls `_maybe_request_whole_workflow_confirmation()`; on a `DECLINED`/`TIMED_OUT` outcome, aborts before any step runs; otherwise iterates `steps`, building an `ActionRequest` per step (`action_type`, `parameters` copied directly, `context` derived from the passed-in `context` with `requested_by` rewritten to `"workflow:{workflow_id}"`) and calling `action_registry.dispatch()`; on a step `FAILED`/`DENIED` result where `continue_on_failure` is `False`, sets `aborted_early=True` and marks every remaining step `skipped=True` without dispatching them.
- `WorkflowExecutor._maybe_request_whole_workflow_confirmation(definition: WorkflowDefinition) -> ConfirmationOutcome | None` — internal; triggers when `len(steps) >= large_workflow_step_threshold` OR any step's `permission_policy_engine.classify(action_type).risk_level` is `HIGH`; builds the prompt from `large_workflow_confirmation_prompt_template`; returns `None` (no prompt needed) otherwise.
- `WorkflowExecutor._build_step_request(step: WorkflowStep, workflow_id: str, base_context: ActionContext) -> ActionRequest` — internal, the `WorkflowStep`→`ActionRequest` translation named in Sprint 4.9's own Architecture Notes.

## Data Flow

```
WorkflowExecutor.run(workflow_id, context)
      ↓
WorkflowStore.get(workflow_id) → WorkflowDefinition (or abort: not found / disabled)
      ↓
_maybe_request_whole_workflow_confirmation(definition)
      ↓
threshold/risk exceeded?  → ConfirmationService.request_confirmation()  → DECLINED/TIMED_OUT → abort, no steps run
      ↓ (CONFIRMED or no prompt needed)
for each WorkflowStep:
      ↓
  _build_step_request(step) → ActionRequest
      ↓
  ActionRegistry.dispatch(request)   [PermissionGate → ActionResourceGate → executor → ActionAuditLog, per-step, full stack]
      ↓
  ActionResult → WorkflowStepResult
      ↓
  FAILED/DENIED and NOT continue_on_failure?  → abort, remaining steps marked skipped
      ↓
WorkflowRunResult (all step_results, aborted_early, whole_workflow_confirmation)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `large_workflow_step_threshold`, `large_workflow_confirmation_prompt_template`.
2. `workflow/workflow_executor.py` — `WorkflowStepResult`, `WorkflowRunResult`, `WorkflowExecutor`.
3. Unit tests: full successful multi-step run; abort-on-failure (with correct `skipped` marking of remaining steps); `continue_on_failure` allowing a run to proceed past a failed step; whole-workflow confirmation triggering (by step count, and separately by risk) and correctly aborting on decline/timeout; disabled/nonexistent workflow handling.

## Architecture Notes

`WorkflowExecutor` never calls any concrete executor (`ApplicationManager`, etc.) directly and never constructs its own `PermissionGate`/`ActionResourceGate`/`ActionAuditLog` — it holds only `action_registry` and calls `dispatch()`, exactly like any other caller. This is stated as a hard architectural invariant, not just a convenience: if a future change ever needs `WorkflowExecutor` to bypass part of the dispatch stack for "efficiency," that is a signal the underlying design needs revisiting, not a shortcut to take quietly (Part 2's own words: "every automated action must be safe, auditable, and reversible where practical" makes no workflow-step exception).

The whole-workflow confirmation check happens **once, before any step runs** — not per-step in addition to Sprint 4.7's own per-step confirmation. A step still classified `MEDIUM`/`HIGH` risk individually will still trigger its own Sprint 4.7 confirmation prompt during `dispatch()`, independent of whether the whole-workflow prompt already ran; this sprint does not suppress or short-circuit Sprint 4.7's own per-step gating in any way — the two prompts answer different questions ("should this whole sequence run at all" vs. "should this specific step run") and can both fire in the same run.

## Integration Considerations

- `WorkflowExecutor` is constructed and (indirectly, via `WORKFLOW_STEP`/`ActionType`-shaped routing — see Sprint 4.11) invoked from the live turn-processing path by Sprint 4.11, which also wires `EngineSelection.WORKFLOW` (3.11, currently reserved/unwired) to actually call `WorkflowExecutor.run()`.
- Every step's `ActionAuditRecord` (Sprint 4.8) is correlated by `requested_by = "workflow:{workflow_id}"` — Sprint 4.8's own schema needs no workflow-specific column for this to work, per its own Integration Considerations.
- A future "undo this whole workflow run" capability would need to iterate `WorkflowRunResult.step_results` in reverse, calling `ActionRecoveryManager.attempt_recovery()` (4.8) per reversible step — not built in this sprint (no spec names it), flagged as a Future Consideration.

## Potential Risks

- **`continue_on_failure` per-step is the only failure-handling primitive** — there is no "retry this step" or "skip to a labeled step" control flow; acceptable given Part 2's own strictly linear worked example, but a real limitation if workflows grow more complex, matching Sprint 4.9's own identical flagged limitation.
- **A long-running workflow (many steps, each potentially resource-gated per Sprint 4.6) has no overall timeout** — only individual steps are timeout-bounded (Sprint 4.5's `command_timeout_seconds`, Sprint 4.4's `window_operation_timeout_seconds`); a pathological workflow could still run for a long time in aggregate. Flagged as a Future Consideration (`WorkflowConfig.max_total_runtime_seconds`) rather than built speculatively without evidence it's needed.
- **The whole-workflow confirmation prompt's "aggregate risk" wording (`high_risk_count`) requires classifying every step up front**, before execution begins — a small but real amount of duplicated work with Sprint 4.7's own per-step classification (which happens again, individually, at each step's `dispatch()` call). Accepted as a minor, bounded cost (at most `max_steps_per_workflow`, i.e. 20, classification calls, each cheap) rather than engineering a shared cache for a cost this small.

## Acceptance Criteria

- A multi-step workflow with no failures executes every step in order, producing a `WorkflowRunResult` with all steps `SUCCEEDED`.
- A step failure with `continue_on_failure=False` aborts the run; every subsequent step is marked `skipped=True`, none are dispatched.
- A step failure with `continue_on_failure=True` does not abort the run; execution proceeds to the next step.
- A workflow at or above `large_workflow_step_threshold`, or containing any `HIGH`-risk step, triggers a whole-workflow confirmation prompt before any step runs.
- A declined or timed-out whole-workflow confirmation aborts before any step is dispatched — verified by a spy proving `ActionRegistry.dispatch()` is never called in that case.
- Matches Part 4 Phase 4.2's "Complex workflows execute correctly."

## Testing Checklist

- [ ] Unit: full successful multi-step run.
- [ ] Unit: abort-on-failure with correct `skipped` marking.
- [ ] Unit: `continue_on_failure=True` allows the run to proceed past a failed step.
- [ ] Unit: whole-workflow confirmation triggers by step-count threshold.
- [ ] Unit: whole-workflow confirmation triggers by any-step-`HIGH`-risk, even under the step-count threshold.
- [ ] Unit: declined/timed-out whole-workflow confirmation aborts before any `dispatch()` call (spy-verified).
- [ ] Unit: disabled workflow (`is_enabled=False`) is rejected before any confirmation prompt or step runs.
- [ ] Unit: nonexistent `workflow_id` degrades to a reportable abort, not an exception.

## Documentation Checklist

- [ ] `workflow/workflow_executor.py` docstring: the "never bypasses `ActionRegistry.dispatch()`'s full stack" invariant, and the two-different-questions distinction between whole-workflow and per-step confirmation, both stated explicitly.
- [ ] `docs/STATUS.md` — Phase 4.2 (Workflow Engine) row notes Workflow Executor complete.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

4.11 — Workflow & Device Control Integration.

## Future Considerations

- Reverse-order whole-run recovery ("undo this entire workflow") — flagged above, a real but non-trivial extension of Sprint 4.8's per-action recovery.
- An overall workflow runtime bound (`max_total_runtime_seconds`) — flagged above, not built without evidence of real need.
- Richer control flow (retry-this-step, conditional branching) — explicitly deferred, matching Sprint 4.9's own identical Future Consideration.
