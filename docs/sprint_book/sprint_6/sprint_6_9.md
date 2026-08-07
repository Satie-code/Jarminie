# Sprint 6.9 — Multi-Step Workflow Engine

## Sprint ID

6.9

## Sprint Name

Multi-Step Workflow Engine

## Purpose

Extend the existing Workflow Engine (`workflow/`, Sprint 4.9/4.10) so a Task Graph (Sprint 6.2) can become a real, dispatchable multi-step run — the brief's own worked example (Open VS Code → Open project → Pull Git repository → Launch Ollama → Open documentation → Resume previous session) — and give it two small, genuinely new capabilities that example needs and the existing Action Engine does not yet have: opening a URL, and resuming a previously-known project/session using Sprint 6.6's Knowledge Graph.

## Engineering Rationale

**Extends `workflow/`, does not fork it.** `WorkflowExecutor`/`WorkflowStore`/`WorkflowDefinition`/`WorkflowStep` (Sprint 4.9/4.10) all stay exactly as they are — this sprint adds a *source* for a `WorkflowDefinition` beyond hand-authoring (a `TaskGraph`'s `ready_tasks()`, translated), and two small, disclosed additions to the underlying Action Engine vocabulary.

**A real capability gap, checked against the actual implementation rather than assumed**: `device_control/application_manager.py`'s `ApplicationManager.launch()` calls `subprocess.Popen([executable_path, *args])` directly — it launches an executable, not a URL, and Windows cannot `Popen` a bare URL the way it can an `.exe`. "Open documentation" (a URL) is therefore a genuine, new capability, not something `LAUNCH_APPLICATION` already silently covers. This sprint adds `ActionType.OPEN_URL` (widening the existing, closed-by-design `ActionType` enum — the same kind of deliberate, disclosed enum widening Sprint 6.5 already flagged for `EngineSelection`) and a small `ApplicationManager.open_url()` method using Python's standard `webbrowser.open()` — never a shell/`cmd` invocation, avoiding any command-injection-shaped risk for what is fundamentally a "hand a URL to the OS's default handler" operation.

**"Pull Git repository" and "Launch Ollama" need no new capability** — both already fit `ActionType.SYSTEM_COMMAND` (existing, Sprint 4.5) and `ActionType.LAUNCH_APPLICATION` respectively, gated exactly as every other command/launch already is by `DeviceControlConfig.approved_commands`'s own existing empty-by-default allowlist (`backlog/technical_debt.md` item 20) — a `git pull` step in a generated workflow is **inert** (denied by the allowlist) until the user deliberately approves it, the correct default per that item's own established reasoning, not a new gap this sprint introduces.

**"Resume previous session" reuses Sprint 6.6's Knowledge Graph and Sprint 6.3's Context Engine rather than inventing a third persistence mechanism** — it is a *query composition*, not new storage: find the most recently-referenced `EntityType.PROJECT` (`KnowledgeGraphStore.find_entities()`, sorted by `last_referenced_at`), then build ordinary `LAUNCH_APPLICATION`/`OPEN_URL`/`SYSTEM_COMMAND` steps from whatever that project's own related entities/relationships describe.

## Objectives

- `ActionType.OPEN_URL` (new member) + `ApplicationManager.open_url()`.
- `TaskGraphWorkflowAdapter`: translates a `TaskGraph`'s `ready_tasks()` into a real `WorkflowDefinition` the existing `WorkflowExecutor` can run.
- `SessionResumption`: composes `KnowledgeGraphStore` + `ContextEngine` into a `WorkflowDefinition` for "resume my previous session."
- `WorkflowConfig` gains the small set of fields this sprint's two new capabilities need.

## Dependencies

4.9/4.10 (`WorkflowStore`/`WorkflowExecutor`/`WorkflowDefinition`/`WorkflowStep`), 4.2 (`ApplicationManager`, extended), 6.2 (`TaskGraph.ready_tasks()`), 6.5 (`DecisionEngineV2.rank_actions()` — the translated steps are ranked/risk-classified before becoming a `WorkflowDefinition`, not dispatched blind), 6.6 (`KnowledgeGraphStore`, for session resumption), 6.3 (`ContextEngine`).

## Files to Create

- `workflow/task_graph_adapter.py` — `TaskGraphWorkflowAdapter`.
- `workflow/session_resumption.py` — `SessionResumption`.
- `tests/unit/workflow/test_task_graph_adapter.py`
- `tests/unit/workflow/test_session_resumption.py`
- `tests/unit/device_control/test_open_url.py`

## Files to Modify

- `device_control/action_engine.py` — `ActionType` widened with `OPEN_URL = "open_url"`.
- `device_control/application_manager.py` — `ApplicationManager.open_url(url: str, requested_by: str) -> ActionResult`, and its own `execute()`/`can_handle()` dispatch widened to route `ActionType.OPEN_URL`.
- `config/schema.py` — `WorkflowConfig` gains `max_steps_from_task_graph: int = 15` (a defensive bound, mirroring `PlanningConfig`'s own bounding shape — a pathologically large `TaskGraph` should never silently produce an unreviewable giant workflow), `allowed_url_schemes: tuple[str, ...] = ("https", "http")` (an explicit allowlist for `open_url()` — never `file://`/`javascript:`/other schemes, a real, deliberate safety boundary for a brand-new action type that hands a string to the OS).
- `config/defaults.yaml` — matching `workflow:` additions.

## Expected Classes

No new dataclasses beyond what's already listed — `TaskGraphWorkflowAdapter` and `SessionResumption` are both plain classes (no lifecycle, matching `WorkflowExecutor`'s own "orchestrates already lifecycle-managed collaborators" shape), constructor DI: `TaskGraphWorkflowAdapter(decision_engine_v2: DecisionEngineV2, workflow_config: WorkflowConfig)`; `SessionResumption(knowledge_graph_store: KnowledgeGraphStore, context_engine: ContextEngine, workflow_config: WorkflowConfig)`.

## Expected Interfaces

None new.

## Expected Functions

- `ApplicationManager.open_url(url: str, requested_by: str) -> ActionResult` — validates `url`'s scheme against `workflow_config.allowed_url_schemes` (rejecting, as `ActionStatus.FAILED`, anything else — never raises for a bad scheme, matching every other executor's own "a bad request is a `FAILED` result, not an exception" convention), then `webbrowser.open(url)`.
- `TaskGraphWorkflowAdapter.build_workflow(task_graph: TaskGraph, created_by: str) -> WorkflowDefinition` — for each of `task_graph.ready_tasks()` (bounded to `max_steps_from_task_graph`), constructs a candidate `ActionRequest` from the `Task`'s own title/description (a small, literal keyword-to-`ActionType` mapping — "open"/"launch" → `LAUNCH_APPLICATION`, "pull"/"run"/"execute" → `SYSTEM_COMMAND`, a URL-shaped string in the description → `OPEN_URL` — the same "small, literal, config-driven-where-it-matters" classification discipline `decision/authority.py`'s own keyword tuples already established, deliberately not a second LLM call), ranks the candidates via `decision_engine_v2.rank_actions()`, and emits one `WorkflowStep` per candidate in ranked order, each `description` copied from the originating `Task.title` (preserving the Explainability Rule's own existing "step description is human-readable, shown before/during execution" property `workflow/workflow_model.py` already established).
- `SessionResumption.build_workflow(created_by: str) -> WorkflowDefinition | None` — queries `knowledge_graph_store.find_entities(EntityType.PROJECT)`, picks the entity with the most recent `last_referenced_at`; returns `None` (not an empty `WorkflowDefinition`) when no `PROJECT` entity exists yet — an honest "there is no previous session to resume," never a fabricated one-step no-op workflow. When a project entity exists, builds steps from its own `related_entities()` (e.g. a `FILE` entity `PART_OF` the project becomes a `LAUNCH_APPLICATION`/`OPEN_URL` step).

## Data Flow

```
Sprint 6.2: TaskGraph.ready_tasks()  (a proposed, accepted plan's currently-runnable tasks)
      ↓
TaskGraphWorkflowAdapter.build_workflow(task_graph, created_by)
      ↓
   keyword classification  →  candidate ActionRequests
      ↓
DecisionEngineV2.rank_actions(candidates)   (existing, Sprint 6.5 — risk/confidence/priority ranked)
      ↓
WorkflowDefinition (steps in ranked order)
      ↓
WorkflowStore.save()  →  WorkflowExecutor.run()   (both existing, Sprint 4.9/4.10 — completely unchanged)
      ↓
Sprint 6.2: TaskGraph.mark_completed()/mark_failed() per WorkflowStepResult (wired at 6.13)

--- separately ---

SessionResumption.build_workflow(created_by)
      ↓
KnowledgeGraphStore.find_entities(EntityType.PROJECT)  →  most-recently-referenced project
      ↓
related_entities()  →  WorkflowDefinition  →  WorkflowStore.save()  →  WorkflowExecutor.run()
```

## Implementation Tasks

1. `device_control/action_engine.py` — `ActionType.OPEN_URL`.
2. `device_control/application_manager.py` — `open_url()`, dispatch widened.
3. `config/schema.py`/`config/defaults.yaml` — `WorkflowConfig.max_steps_from_task_graph`/`allowed_url_schemes`.
4. `workflow/task_graph_adapter.py` — keyword classifier, `build_workflow()`.
5. `workflow/session_resumption.py` — `build_workflow()`, the `None`-when-nothing-to-resume case.
6. Unit tests: `open_url()` against an allowed scheme, a disallowed scheme (rejected, `FAILED`, never raises), and a real `webbrowser.open()` call verified via monkeypatch (not an actual browser launch in CI); `TaskGraphWorkflowAdapter` classification against representative `Task` titles for each of the three mapped `ActionType`s, plus an unclassifiable title (falls back to a default, disclosed `ActionType`, never silently dropped); truncation at `max_steps_from_task_graph`; `SessionResumption` against a populated Knowledge Graph and against an empty one (`None` returned, not a fabricated workflow).

## Architecture Notes

`TaskGraphWorkflowAdapter`'s keyword classifier is deliberately small and literal, not a second reasoning pass — a `Task.title` is already human-authored (LLM-decomposed, per Sprint 6.1) text, not raw conversational input, so the same lighter-weight classification discipline `decision/authority.py`'s own keyword tuples use for a similarly-already-structured input is the right level of machinery, not `ReasoningEngine`. If a future sprint finds the keyword classifier too coarse, escalating to a `ReasoningEngine`-assisted classification is a disclosed Future Consideration, not built preemptively here.

Every `WorkflowDefinition` this sprint produces (from either adapter) still goes through `WorkflowExecutor.run()`'s own completely unchanged permission/confirmation/audit pipeline (`PermissionPolicyEngine`, `ConfirmationService`, `ActionAuditLog`) — this sprint adds new *sources* of a `WorkflowDefinition`, never a new *execution path* that could bypass Level 4 Part A's own already-hardened safety machinery.

## Integration Considerations

- No live turn-triggered caller yet — `TaskGraphWorkflowAdapter`/`SessionResumption` are both fully implemented and unit-tested in isolation. Sprint 6.13 (Integration) is where "resume my previous session" and "run my plan" become real conversational requests, routed through the new `EngineSelection.PLANNING` member that sprint introduces.
- `TaskGraph.mark_completed()`/`mark_failed()` are **not** called by this sprint automatically after a `WorkflowRunResult` — wiring a completed/failed `WorkflowStepResult` back onto the originating `Task` is Sprint 6.13's own composition-root job (it is the sprint with visibility into both `TaskGraph` and a live `WorkflowRunResult` at once); this sprint's adapter is a one-way `TaskGraph → WorkflowDefinition` translation only, disclosed as such rather than silently assumed bidirectional.

## Potential Risks

- **The keyword classifier can misclassify an ambiguous `Task.title`** (e.g. a title containing both "open" and "run") — the same class of risk `decision/authority.py`'s own keyword-based engine routing already carries and already accepts; a misclassified step still passes through the full permission/confirmation pipeline unchanged, so a misclassification's worst case is "asks for confirmation on the wrong `ActionType`," not "silently does the wrong risky thing."
- **`SYSTEM_COMMAND` steps derived from a Task Graph are inert by default** (empty `approved_commands` allowlist) — correct and safe, but means the brief's own worked example ("Pull Git repository") produces a real workflow that will not actually run the pull step until the user has separately approved that specific command, worth stating plainly so it isn't mistaken for a bug at verification time.
- **`open_url()`'s scheme allowlist is a real, if narrow, safety-relevant surface** — `webbrowser.open()` itself does not validate schemes; this sprint's own `allowed_url_schemes` check is the only thing standing between a malformed/malicious URL and the OS's default handler. Kept intentionally small (`https`/`http` only) rather than permissive.

## Acceptance Criteria

- `open_url()` succeeds for an `https`/`http` URL and returns `ActionStatus.FAILED` (never raises) for any other scheme.
- `TaskGraphWorkflowAdapter.build_workflow()` produces a `WorkflowDefinition` whose steps are ordered by `DecisionEngineV2.rank_actions()`'s own output, bounded to `max_steps_from_task_graph`.
- `SessionResumption.build_workflow()` returns `None` when no `PROJECT` entity exists, and a real, non-empty `WorkflowDefinition` when one does.
- Every `WorkflowDefinition` produced by either new class runs through the existing, unmodified `WorkflowExecutor.run()` without any new bypass of `PermissionPolicyEngine`/`ConfirmationService`/`ActionAuditLog`.

## Testing Checklist

- [ ] Unit: `open_url()` — allowed scheme, disallowed scheme, real `webbrowser.open()` call verified via monkeypatch.
- [ ] Unit: `TaskGraphWorkflowAdapter` keyword classification for `LAUNCH_APPLICATION`/`SYSTEM_COMMAND`/`OPEN_URL`-shaped titles and an unclassifiable fallback case.
- [ ] Unit: `build_workflow()` truncation at `max_steps_from_task_graph`.
- [ ] Unit: `SessionResumption` against a populated and an empty Knowledge Graph.
- [ ] Unit: `WorkflowConfig` validation for the two new fields.
- [ ] Integration-shaped unit test (still in `tests/unit/`, against fakes): a full `TaskGraph → WorkflowDefinition → WorkflowStore.save()` round trip confirming the existing store/executor accept this sprint's own output unchanged.

## Documentation Checklist

- [ ] `workflow/task_graph_adapter.py`/`session_resumption.py` docstrings: the "translates only, never bypasses `WorkflowExecutor`'s existing safety pipeline" boundary, and the deliberate `SYSTEM_COMMAND`-inert-by-default consequence for the Git-pull example, both stated explicitly.
- [ ] `docs/STATUS.md` — Level 6 Part A narrative extended.
- [ ] `docs/backlog/technical_debt.md` — cross-reference item 20 (`approved_commands` empty by design), noting a Task-Graph-derived `SYSTEM_COMMAND` step inherits that same gate.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

6.10 — Self Evaluation.

## Future Considerations

- Escalating the keyword classifier to a `ReasoningEngine`-assisted one, if real usage shows it's too coarse — disclosed above, not built here.
- Automatic `TaskGraph.mark_completed()`/`mark_failed()` wiring from a `WorkflowRunResult` — named above as Sprint 6.13's own job, not this sprint's.
- A second, richer URL-scheme policy (e.g. per-domain allow/deny) — no basis in this brief; the current allowlist is deliberately minimal.
