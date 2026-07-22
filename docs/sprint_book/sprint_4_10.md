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

## Sprint Completion Report (2026-07-21)

Implemented as specified, authorized directly ("proceed with sprint 4.10") — same pattern as 4.2–4.9. No spec ambiguity or stop-and-ask gates on the executor's own shape: `WorkflowStepResult`/`WorkflowRunResult`/`WorkflowExecutor`'s constructor DI, `run()`/`_maybe_request_whole_workflow_confirmation()`/`_build_step_request()` signatures, and the `WorkflowConfig` additions were all fully and unambiguously specified. Delivered `workflow/workflow_executor.py` (`WorkflowStepResult`, `WorkflowRunResult`, `WorkflowExecutor`), `WorkflowConfig.large_workflow_step_threshold`/`large_workflow_confirmation_prompt_template` in `config/schema.py` (with `_validate_workflow()` extended: positive threshold, non-blank template) and `config/defaults.yaml`. 14 new tests: 12 in `tests/unit/workflow/test_workflow_executor.py` (full successful run; `requested_by` rewriting; abort-with-skip on `FAILED`/`DENIED`; `continue_on_failure=True` proceeding past a failure; whole-workflow confirmation triggering by step-count threshold and separately by any `HIGH`-risk step under threshold; a below-threshold/low-risk workflow confirmed to *not* prompt; declined/timed-out whole-workflow confirmation aborting before any `dispatch()` call, spy-verified for both outcomes; disabled and nonexistent workflows both degrading to a reportable abort) plus 2 in `tests/unit/config/test_schema.py` for the two new `WorkflowConfig` fields. 863/863 full-suite tests passing, `ruff check .` clean.

**`WorkflowExecutor` never calls a concrete executor or constructs its own `PermissionGate`/`ActionResourceGate`/`ActionAuditLog`** — it holds only `action_registry` (Sprint 4.1's `ActionRegistry`) and calls `dispatch()`, exactly as this sprint's own Architecture Notes require. Verified structurally, not just asserted: `tests/unit/workflow/test_workflow_executor.py`'s `FakeActionRegistry` is a bare duck-typed `dispatch()` stand-in with no `PermissionGate`-shaped dependency at all, and every test still passes — `WorkflowExecutor` genuinely has no other path to an executor.

**Whole-workflow confirmation, real classification, one prompt, before any step**: `_maybe_request_whole_workflow_confirmation()` classifies every step via the real `PermissionPolicyEngine.classify()` (not a fake — same "prefer a real, cheap collaborator" precedent `test_action_engine.py`'s own `real_permission_gate` fixture set), counts `HIGH`-risk steps, and triggers exactly when `step_count >= large_workflow_step_threshold` **or** `high_risk_count > 0` — both paths independently tested, including a below-threshold, all-`LOW`-risk workflow proving the prompt does *not* fire needlessly. A `DECLINED`/`TIMED_OUT` outcome returns before the step loop starts; `test_declined_or_timed_out_confirmation_aborts_before_any_step_dispatches` (parametrized over both outcomes) asserts `registry.dispatched == []` — the spy proof this sprint's own Acceptance Criteria named explicitly.

**Skipped steps carry a real, well-formed `ActionResult` (`status=PENDING`, an explanatory `error_message`), never `None`** — a step aborted mid-run is exactly as inspectable as one that actually ran, per the sprint's own "a partially-completed workflow's exact state is always knowable, never ambiguous" Objective. `PENDING` was chosen over inventing a new `ActionStatus` member: it already means "never got past pending," which is literally true of a step that was built but never dispatched — no `ActionStatus` enum change needed, keeping `device_control/action_engine.py` (outside this sprint's Files to Modify) untouched.

**Known, deliberately undertaken gap, found before writing any code, not after**: the whole-workflow `ConfirmationRequest.prompt_text` is built correctly from `large_workflow_confirmation_prompt_template` (verified directly — `test_whole_workflow_confirmation_triggers_at_step_count_threshold`/`..._on_any_high_risk_step_under_threshold` both assert the workflow name/step count/high-risk count appear in `prompt_text`), but the real `VoiceConfirmationService` (Sprint 4.7) ignores `ConfirmationRequest.prompt_text` by design and rebuilds generic per-`ActionType` text instead — confirmed by reading `security/confirmation_service.py`'s own docstring and its existing test suite before assuming anything. Not fixed here: doing so would mean changing already-shipped, already-tested Sprint 4.7 code, outside this sprint's own Files to Modify and its own stated scope ("deciding *when* a whole-workflow prompt is warranted... not re-implementing the underlying confirmation mechanism itself"). Logged as `backlog/technical_debt.md` item 25 rather than silently accepted or silently patched.

Not yet wired into `main.py`/`CoreManager` or the live turn-processing path — per this sprint's own Integration Considerations, that's Sprint 4.11's job, which also wires `EngineSelection.WORKFLOW` (3.11, currently reserved/unwired) to actually call `WorkflowExecutor.run()`. **This closes both of Level 4 Part A's Workflow Engine component sprints (4.9–4.10). Sprint 4.11 (Workflow & Device Control Integration) is next.**
