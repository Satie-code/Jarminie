# Sprint 4.9 — Workflow Builder

## Sprint ID

4.9

## Sprint Name

Workflow Builder

## Purpose

Implement the Workflow Engine's definition/storage half: a `WorkflowDefinition` model (an ordered sequence of steps, each an `ActionRequest`-shaped operation) and persistent storage for it, per Part 2's Workflow Engine section and its own worked example: *"Continue Project JARMINEI → Open IDE → Open project folder → Restore workspace → Display pending tasks."*

## Engineering Rationale

Corresponds unchanged to `docs/sprint_book/INDEX.md`'s original `4.5 Workflow Builder` roadmap entry — same name, same scope. Kept as a separate sprint from Workflow Executor (4.10), preserving the existing roadmap's own split rather than merging into a single "Workflow Orchestrator" sprint (this task's own suggested breakdown's terminology) — the same reasoning `docs/sprint_book/sprint_book/README.md`'s Sprint Size guidance already establishes generally ("one subsystem/feature/integration milestone per sprint") and the same split Level 2 already used for structurally analogous concerns (`ConversationSessionStore`, storage, 2.7, separate from `ContextManager`, consumption, 2.8). Definition/storage and execution are genuinely separable concerns with different risk profiles — a stored `WorkflowDefinition` that is never executed is inert and safe; execution is where Sprint 4.7's confirmation gating actually matters — so keeping them as distinct sprints keeps that risk boundary visible in the Sprint Book itself, not just in the code.

Each `WorkflowStep` is defined as directly reusing Sprint 4.1's `ActionRequest` shape, not a parallel, workflow-specific step format — a workflow is, structurally, nothing more than an ordered list of the same `ActionRequest`s any other Level 4 caller could issue individually. This is a deliberate design choice keeping `workflow/` a thin orchestration layer over `device_control/`'s Action Engine, per this Sprint Book's own established dependency direction (`workflow/` depends on `device_control/`, never the reverse — see Sprint 4.1's Engineering Rationale).

## Objectives

- `WorkflowDefinition` (a named, ordered sequence of `WorkflowStep`s, each wrapping an `ActionRequest`) and `WorkflowStep`.
- `WorkflowStore`: persistent (SQLite, via `SqliteClient`, same generic-DB-layer reuse pattern every prior storage sprint has followed) create/read/update/delete/list for `WorkflowDefinition`s.
- Basic step sequencing metadata: each step can declare `continue_on_failure: bool` (does a failed step abort the whole workflow, or continue to the next step) — the only conditional-execution primitive this sprint ships; branching/looping is explicitly out of scope (see Future Considerations).

## Dependencies

4.1 (Action Engine Foundation) for `ActionRequest`/`ActionType`; 3.11 (Authority Evaluation) per the original roadmap's own stated dependency (a workflow step's `ActionContext.decision_trace` may originate from a real Decision Engine turn).

## Files to Create

- `workflow/workflow_model.py` — `WorkflowStep` (dataclass), `WorkflowDefinition` (dataclass).
- `workflow/workflow_store.py` — `WorkflowStore`.
- `tests/unit/workflow/test_workflow_model.py`
- `tests/unit/workflow/test_workflow_store.py`

## Files to Modify

- `config/schema.py` — new `WorkflowConfig` dataclass: `max_steps_per_workflow: int = 20` (a defensive bound — Part 2's own "if many actions are about to execute, request confirmation" implies workflows are expected to have a bounded, human-reviewable size, not an unbounded script).
- `config/defaults.yaml` — matching `workflow:` section.

## Expected Classes

- `WorkflowStep` (dataclass) — `step_index: int`, `action_type: ActionType`, `parameters: dict[str, object]`, `continue_on_failure: bool = False`, `description: str` (a human-readable label, e.g. `"Open project folder"` — the Explainability Rule applied to a workflow step, shown to the user before/during execution, not just in logs).
- `WorkflowDefinition` (dataclass) — `workflow_id: str`, `name: str`, `steps: list[WorkflowStep]`, `created_by: str`, `created_at: datetime`, `is_enabled: bool = True` (a disabled workflow can be stored but never executed — Sprint 4.10 checks this before running; a soft-delete-shaped safeguard against accidentally triggering a workflow mid-edit).
- `WorkflowStore(ManagedModule)` — constructor DI: `(sqlite_client: SqliteClient, workflow_config: WorkflowConfig)`. Owns its own table DDL (`workflows`, `workflow_steps`), same "caller owns its own DDL" precedent as every prior storage class.

## Expected Interfaces

None new.

## Expected Functions

- `WorkflowStore.save(definition: WorkflowDefinition) -> None` — validates `len(steps) <= max_steps_per_workflow` before persisting, raising `ValueError` for a caller to handle (a data-integrity boundary this store enforces itself, not something deferred to a caller's own discipline).
- `WorkflowStore.get(workflow_id: str) -> WorkflowDefinition | None`
- `WorkflowStore.list_all() -> list[WorkflowDefinition]`
- `WorkflowStore.delete(workflow_id: str) -> bool`
- `WorkflowStore.set_enabled(workflow_id: str, is_enabled: bool) -> bool`

## Data Flow

```
caller (voice command, or a future authoring UI outside this sprint's scope)
      ↓
WorkflowDefinition(name, steps=[WorkflowStep(action_type=LAUNCH_APPLICATION, ...), WorkflowStep(action_type=FILE_MOVE, ...), ...])
      ↓
WorkflowStore.save(definition)  →  validated (max_steps_per_workflow), persisted (SQLite)
      ↓
(later) WorkflowStore.get(workflow_id) → WorkflowDefinition
      ↓
Sprint 4.10 (Workflow Executor)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `WorkflowConfig`.
2. `workflow/workflow_model.py` — `WorkflowStep`, `WorkflowDefinition`.
3. `workflow/workflow_store.py` — `WorkflowStore`, own DDL, full CRUD.
4. Unit tests: save/get/list/delete/set_enabled round trips, `max_steps_per_workflow` rejection, persistence across a `close()`/reopen cycle (matching `ConversationSessionStore`'s own precedent for verifying real persistence, not just an in-memory happy path).

## Architecture Notes

`WorkflowStep.parameters: dict[str, object]` deliberately mirrors `ActionRequest.parameters`'s own shape exactly — a `WorkflowStep` is not translated into an `ActionRequest` by any complex mapping logic; Sprint 4.10's executor constructs an `ActionRequest` from a `WorkflowStep` by copying `action_type`/`parameters` directly and wrapping them with a workflow-specific `ActionContext` (`requested_by = "workflow:<workflow_id>"`). Keeping the two shapes deliberately aligned is what makes that translation a one-line operation rather than its own subsystem.

`WorkflowDefinition.is_enabled` exists specifically because a workflow, once it can contain `HIGH`-risk steps (Sprint 4.7's classification), is functionally closer to a saved, reusable script than a single fire-and-forget request — a "pause this without deleting it" affordance is a real safety-relevant feature, not a nice-to-have, matching the spirit (if not the letter) of Part 2's own "request confirmation before proceeding" language applied at the definition level, before execution is even attempted.

## Integration Considerations

- Registered as a `ManagedModule` with `CoreManager` by Sprint 4.11, following the same `main.py` composition-root pattern every prior storage class (`ConversationSessionStore`, `MemoryStore`) already established.
- No authoring interface (voice or UI) is built in this sprint — `WorkflowStore.save()` is real, tested, and callable, but nothing yet constructs a `WorkflowDefinition` from a live conversation turn or a UI form; that live-caller gap is explicitly out of this Sprint Book's own scope (not every future capability needs to be crammed into Level 4 Part A) and is named here rather than silently discovered later, the same discipline this Sprint Book has applied consistently since Sprint 4.1.
- Sprint 4.10 (Workflow Executor) is the sole consumer of `WorkflowStore.get()`/`list_all()` within this Sprint Book's own scope.

## Potential Risks

- **No versioning** — `WorkflowStore.save()` on an existing `workflow_id` overwrites the prior definition outright, with no history retained. Acceptable for this sprint's own scope (Part 2 names no versioning requirement for Workflow), but a real limitation if a user edits a workflow and later wants the old version back — flagged as a Future Consideration, not built speculatively.
- **`max_steps_per_workflow` (20) is an unvalidated guess**, same caveat class as every other tuned bound in this codebase — config-driven for exactly that reason.
- **No authoring interface means this sprint's own real-world testability is limited to directly constructed `WorkflowDefinition` objects** in tests — the Master Plan's "Complex workflows execute correctly" acceptance criterion cannot be fully demonstrated end-to-end until Sprint 4.10 and, ultimately, Sprint 4.13's real verification pass exist; this sprint's own Acceptance Criteria are scoped honestly to storage correctness only.

## Acceptance Criteria

- A `WorkflowDefinition` with multiple `WorkflowStep`s round-trips through `save()`/`get()` with every field preserved exactly.
- `list_all()` accurately reflects the current set of stored workflows across save/delete operations.
- Saving a workflow exceeding `max_steps_per_workflow` raises `ValueError`, nothing is persisted.
- `set_enabled(workflow_id, False)` persists and is reflected in a subsequent `get()`.
- Data survives a `WorkflowStore` close/reopen cycle against the same SQLite file (real persistence, not just in-process state).

## Testing Checklist

- [ ] Unit: save/get round trip preserves every field, including step order.
- [ ] Unit: `list_all()` reflects save/delete correctly.
- [ ] Unit: `max_steps_per_workflow` rejection.
- [ ] Unit: `set_enabled()` persists and is readable.
- [ ] Unit: persistence survives close/reopen against a real (temp-file) SQLite database.
- [ ] Unit: `delete()` of a nonexistent `workflow_id` returns `False`, not an exception.

## Documentation Checklist

- [ ] `workflow/workflow_model.py`/`workflow/workflow_store.py` docstrings: the deliberate `WorkflowStep.parameters`-mirrors-`ActionRequest.parameters` design choice, stated explicitly.
- [ ] `docs/STATUS.md` — Phase 4.2 (Workflow Engine) row moves to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

4.10 — Workflow Executor.

## Future Considerations

- Workflow definition versioning/history — flagged above, not built now.
- Branching/conditional steps beyond the single `continue_on_failure` flag (e.g. "if file exists, do X, else Y") — a real future capability with no current spec basis (Part 2's own Workflow example is a strictly linear sequence); deliberately not built speculatively.
- A voice or UI authoring interface — the real gap named above; out of this Sprint Book's scope entirely.
