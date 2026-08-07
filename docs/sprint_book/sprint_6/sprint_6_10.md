# Sprint 6.10 — Self Evaluation

## Sprint ID

6.10

## Sprint Name

Self Evaluation

## Purpose

After a task or workflow finishes, evaluate whether it actually succeeded, failed, or revealed a real improvement opportunity — per the brief's own list — and record that evaluation durably, "without self-modifying code." This sprint gives Sprint 6.2's Task Graph and Sprint 6.9's Multi-Step Workflow Engine a genuine feedback loop: outcomes get looked at, not just logged and forgotten.

## Engineering Rationale

**A real gap in the brief's own suggested sprint progression, found and corrected the same way this project has corrected comparable gaps at every prior Level.** The brief's "NEW CORE SYSTEMS" section names thirteen systems including "10. Self Evaluation," but its own "Suggested progression" numbered list (6.1 Planning Engine ... 6.14 Testing & Freeze) has no corresponding entry for it at all — the twelve named component sprints in that list skip straight from Explainability-adjacent concerns to Adaptive Prioritization with no slot for Self Evaluation. This is the identical shape of gap `docs/sprint_book/INDEX.md`'s own "Level 3 breakdown changes" note already found and fixed once before (a pipeline stage, Memory Retrieval, named in the architecture but missing from the original sprint list) — resolved the same way: insert a real sprint for it rather than silently dropping the system the brief itself named. Placed here, after Sprint 6.9 (Multi-Step Workflow Engine) and before Explainability, because evaluating an outcome requires the outcome to exist first (`TaskGraph`'s completion/failure state, `WorkflowRunResult`), and Sprint 6.11 (Explainability Layer)'s own "why did that happen" answers are stronger once a real evaluation record exists to draw on.

Extends `planning/` (does not introduce a sixth new top-level package) — evaluating a `Task`/`Goal`'s outcome is Planning's own natural continuation, the identical relationship `memory/lifecycle_manager.py` has to `memory/memory_store.py`.

**The brief's own "without self-modifying code" instruction is treated as a hard, non-negotiable architectural boundary in this sprint, not a suggestion** — stated explicitly here because Self Evaluation is the one sprint in this entire Book structurally adjacent to the idea of JARMINEI changing its own behavior based on its own judgment of its own performance. `SelfEvaluator` **never** writes to any `.py` file, never calls `config/loader.py`'s write path (config is written by `ui/settings_window.py`'s user-facing save only — untouched by this sprint), and never issues any `ActionRequest`. Its only write surface is a new, append-only `EvaluationRecord` table — read by a human, or by Sprint 6.7's Learning Engine v2 as one more advisory input, never executed automatically.

## Objectives

- `EvaluationRecord` — one evaluation of one completed/failed `Task` or `WorkflowRunResult`.
- `SelfEvaluator`: produces an `EvaluationRecord` from a finished `Task`/`WorkflowRunResult`, reusing Sprint 6.4's `ReasoningEngine` for the qualitative "what went well / what didn't / what would help next time" judgment.
- `PlanningConfig` gains the field this sprint needs.

## Dependencies

6.2 (`TaskGraph`, `TaskGraphStore` — the table this sprint's own `EvaluationRecord`s are added alongside), 6.9 (`WorkflowRunResult`, the other real evaluation subject), 6.4 (`ReasoningEngine`, for the qualitative judgment — reused, not a second LLM integration).

## Files to Create

- `planning/self_evaluator.py` — `EvaluationOutcome` (Enum: `SUCCESS`, `FAILURE`, `PARTIAL`), `EvaluationRecord` (dataclass), `SelfEvaluator`.
- `tests/unit/planning/test_self_evaluator.py`

## Files to Modify

- `planning/task_graph_store.py` — gains a fifth table (`evaluation_records`) and `save_evaluation()`/`list_evaluations_for_goal()` methods — the same "caller owns its own DDL" store already established at Sprint 6.2, simply widened, not a second store class for one more table.
- `config/schema.py` — `PlanningConfig` gains `evaluation_timeout_seconds: float = 30.0` (the `ReasoningEngine` call this sprint makes needs its own timeout, mirroring every other LLM-call-owning config field in this codebase).
- `config/defaults.yaml` — matching addition to the `planning:` section.

## Expected Classes

- `EvaluationOutcome` (Enum) — `SUCCESS`, `FAILURE`, `PARTIAL` (a `WorkflowRunResult` with some steps succeeding and others skipped/failed is honestly `PARTIAL`, never rounded up to `SUCCESS` or down to `FAILURE`).
- `EvaluationRecord` (dataclass) — `record_id: str`, `subject_id: str` (a `Task.task_id` or a `WorkflowRunResult.run_id`), `outcome: EvaluationOutcome`, `summary: str` (the `ReasoningEngine`-produced qualitative judgment), `improvement_note: str | None` (populated only when a real, specific opportunity was identified — `None`, not an empty string, when there's honestly nothing to add), `evaluated_at: datetime`.
- `SelfEvaluator` — constructor DI: `(reasoning_engine: ReasoningEngine, task_graph_store: TaskGraphStore, planning_config: PlanningConfig)`. Not a `ManagedModule` — a stateless evaluation call plus a store write, matching `PlanningEngine`'s own shape.

## Expected Interfaces

None new.

## Expected Functions

- `SelfEvaluator.evaluate_task(task: Task) -> EvaluationRecord` — only called on a `Task` already in a terminal state (`COMPLETED`/`FAILED`/`ABANDONED`); raises `ValueError` immediately (a real programming-error guard, not a graceful-degrade case) if called on a non-terminal `Task` — evaluating something not yet finished is a caller bug, not a runtime condition to tolerate.
- `SelfEvaluator.evaluate_workflow_run(run_result: WorkflowRunResult) -> EvaluationRecord` — derives `EvaluationOutcome` mechanically from `run_result.step_results` (`SUCCESS` if every step succeeded and none were skipped; `FAILURE` if `aborted_early` and nothing meaningful completed; `PARTIAL` otherwise) **before** calling `reasoning_engine.explain_why()` for the qualitative summary — the outcome classification itself is never LLM-derived, only the accompanying narrative is, so a model hallucination can never flip a mechanically-`FAILURE` run into a recorded `SUCCESS`.
- `SelfEvaluator._summarize(subject_description: str, outcome: EvaluationOutcome, working_context: WorkingContext | None) -> tuple[str, str | None]` — the shared `ReasoningEngine.explain_why()`-backed call producing `(summary, improvement_note)`; on `LlmError`, degrades to a fixed, honest fallback summary ("Evaluation completed; a detailed narrative could not be generated.") with `improvement_note=None`, rather than leaving the whole `EvaluationRecord` unwritten — the mechanical `outcome` is always worth recording even when the narrative half fails.

## Data Flow

```
Sprint 6.2: Task reaches a terminal status (COMPLETED/FAILED/ABANDONED)
Sprint 6.9: WorkflowExecutor.run() returns a WorkflowRunResult
      ↓  (caller, wired at 6.13)
SelfEvaluator.evaluate_task() / evaluate_workflow_run()
      ↓
mechanical outcome classification (never LLM-derived)
      ↓
_summarize()  →  ReasoningEngine.explain_why()  →  real Ollama call (or fallback on LlmError)
      ↓
EvaluationRecord
      ↓
TaskGraphStore.save_evaluation()   →  persisted (SQLite, evaluation_records table)
      ↓
Sprint 6.7 (Learning Engine v2, future extension) / Sprint 6.11 (Explainability Layer) — both
read evaluation history; neither is called automatically by this sprint
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `PlanningConfig.evaluation_timeout_seconds`.
2. `planning/self_evaluator.py` — `EvaluationOutcome`, `EvaluationRecord`, `SelfEvaluator.evaluate_task()`/`evaluate_workflow_run()`/`_summarize()`.
3. `planning/task_graph_store.py` — `evaluation_records` table, `save_evaluation()`/`list_evaluations_for_goal()`.
4. Unit tests: `evaluate_task()` against each terminal status, and a `ValueError` for a non-terminal one; `evaluate_workflow_run()`'s mechanical classification against a hand-built all-success, all-failed/aborted-early, and mixed `WorkflowRunResult`; `_summarize()`'s `LlmError` fallback path; persistence round trip for `EvaluationRecord`.

## Architecture Notes

`SelfEvaluator` has no write access to anything outside `TaskGraphStore`'s own new table — it does not touch `config/`, does not write `.py` files, and imports nothing from `security/`'s executor-adjacent surface. This is deliberately verifiable, not just asserted: a dedicated AST-based test (mirroring `learning/recommendation.py`'s own established zero-LLM-import proof at Sprint 5.23) confirms `planning/self_evaluator.py` contains no `open()`/`Path.write_*`/`subprocess`/`ActionRegistry`/`ActionExecutor` references anywhere — the "without self-modifying code" instruction made mechanically checkable, not just documented.

The mechanical-outcome-before-narrative ordering in `evaluate_workflow_run()` is the sprint's own single most important design decision: it guarantees the *recorded fact* of success/failure can never be corrupted by a model hallucination, even though the *explanation* of why can still (honestly, disclosed) be imperfect.

## Integration Considerations

- No live caller yet. Sprint 6.13 (Integration) is where a completed `Task`/`WorkflowRunResult` actually reaches `SelfEvaluator` for the first time — likely as a step immediately following Sprint 6.9's own deferred `TaskGraph.mark_completed()`/`mark_failed()` wiring, since both need the same live `WorkflowRunResult` in hand.
- Sprint 6.7's Learning Engine v2 does **not** automatically consume `EvaluationRecord`s in this Book — no detector in that sprint reads `evaluation_records`. A future pattern type over evaluation outcomes is named in Future Considerations, not built here, since Sprint 6.7 was already closed before this sprint's own table existed in build order.

## Potential Risks

- **`_summarize()`'s qualitative judgment is still an LLM output**, carrying the same disclosed hallucination/quality-variance risk every `ReasoningEngine`-backed feature in this Book already carries — mitigated only by the mechanical-outcome guarantee above, not eliminated.
- **No de-duplication if `evaluate_task()`/`evaluate_workflow_run()` is called twice for the same subject** — each call produces a new, independent `EvaluationRecord`; a caller wanting "the latest evaluation only" must filter `list_evaluations_for_goal()`'s own result itself. Disclosed rather than silently assumed idempotent.
- **`evaluation_timeout_seconds=30.0` is an unvalidated guess**, matching every comparable default in this codebase.

## Acceptance Criteria

- `evaluate_task()` raises `ValueError` for any non-terminal `Task` status and produces a real `EvaluationRecord` for each of the three terminal statuses.
- `evaluate_workflow_run()`'s `outcome` field is derived purely mechanically from `step_results`/`aborted_early` — confirmed by a test that forces `_summarize()` to raise `LlmError` and asserts the resulting `EvaluationRecord.outcome` is still correct (only `summary`/`improvement_note` degrade).
- The AST-based zero-self-modification proof passes: `planning/self_evaluator.py` contains no file-write, subprocess, or `ActionRegistry`/`ActionExecutor` reference.
- `EvaluationRecord`s persist and are retrievable via `list_evaluations_for_goal()` across a `TaskGraphStore` close/reopen cycle.

## Testing Checklist

- [ ] Unit: `evaluate_task()` — three terminal statuses, and a non-terminal `ValueError`.
- [ ] Unit: `evaluate_workflow_run()` mechanical classification — all-success, aborted-early/all-failed, mixed/partial.
- [ ] Unit: `_summarize()` — normal case, `LlmError` fallback case.
- [ ] Unit: AST-based zero-self-modification proof.
- [ ] Unit: `EvaluationRecord` persistence round trip.
- [ ] Unit: `PlanningConfig` validation for the new field.

## Documentation Checklist

- [ ] `planning/self_evaluator.py` docstring: the mechanical-outcome-before-narrative guarantee and the zero-self-modification boundary, both stated explicitly per Architecture Notes above.
- [ ] `docs/STATUS.md` — Level 6 Part A narrative extended, noting the corrected sprint-count gap from the original brief.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

6.11 — Explainability Layer.

## Future Considerations

- A new Learning Engine `PatternType` over evaluation outcomes (e.g. "workflows of this shape tend to fail") — a real, natural future direction, not built here since it would require reopening Sprint 6.7's already-closed scope.
- De-duplication/"latest evaluation only" convenience queries — a plausible small addition once real usage shows repeated evaluation is common; not assumed necessary here.
