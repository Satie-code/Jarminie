# Sprint 6.2 — Task Graph

## Sprint ID

6.2

## Sprint Name

Task Graph

## Purpose

Give a `Goal` produced by Sprint 6.1's `PlanningEngine` somewhere durable to live, and turn its flat `Milestone`/`Task` tree into a real graph: dependencies between tasks, which tasks can run in parallel, which are currently blocked, and which are done — per the brief's own literal requirement ("Represent: dependencies, parallel work, blocked tasks, completion state"). This is the sprint that makes a plan something JARMINEI (and the user) can track over time, across sessions, not just a one-shot LLM answer that evaporates at the end of a turn.

## Engineering Rationale

Directly extends Sprint 6.1's `planning/` package rather than introducing a second new top-level directory — `Task Graph` is not a separate subsystem from Planning in any architectural sense named by the brief; it is Planning's own persistence and dependency layer, the identical relationship `analytics/usage_store.py`(storage) had to `analytics/usage_tracker.py`(collection) at Sprint 5.17, or `memory/memory_store.py` had to the four memory-type sprints built on top of it.

**A real modeling decision, made explicitly**: dependencies are edges between `Task`s *within* a `Goal`, not between arbitrary tasks across different goals — Part 2 of the original spec never describes cross-goal dependency management, and inventing it here would be unrequested scope beyond what this brief's own "Task Graph" section describes ("dependencies, parallel work, blocked tasks, completion state" — all phrased in the singular, task-graph-of-one-goal shape the brief's own `Goal → Milestones → Tasks → Actions` diagram implies). A future cross-goal dependency concept is named in Future Considerations, not built speculatively.

**Reused, not reinvented**: persistence follows the exact `SqliteClient`-via-`ManagedModule`, caller-owns-its-own-DDL pattern every prior store in this codebase already established (`CalendarStore`, `WorkflowStore`, `UsageStore`, `ActionAuditLog`) — no new persistence idiom is introduced.

## Objectives

- `TaskNode`/`TaskEdge` — the graph representation wrapping Sprint 6.1's `Task` with dependency edges and derived readiness state.
- `TaskGraph`: an in-memory graph operating over one `Goal`'s tasks — dependency validation (rejects a cycle rather than allowing one), `ready_tasks()` (topological — every dependency already `COMPLETED`), blocked/parallel-work queries, completion-state transitions.
- `TaskGraphStore(ManagedModule)`: persists `Goal`/`Milestone`/`Task`/`TaskEdge` to SQLite, survives a restart.
- `PlanningConfig` gains its second sprint's worth of fields.

## Dependencies

6.1 (`Goal`/`Milestone`/`Task`/`PlanningStatus`), 3.1 (`database/sqlite_client.py`'s `SqliteClient`, the same generic layer every prior store reuses — confirmed already generic enough per `docs/sprint_book/INDEX.md`'s own Recommendations section).

## Files to Create

- `planning/task_graph.py` — `TaskEdge`, `TaskGraph`.
- `planning/task_graph_store.py` — `TaskGraphStore`.
- `tests/unit/planning/test_task_graph.py`
- `tests/unit/planning/test_task_graph_store.py`

## Files to Modify

- `config/schema.py` — `PlanningConfig` gains `max_task_dependencies: int = 20` (a defensive upper bound on edges per task, preventing a pathological or LLM-hallucinated dependency explosion from ever being accepted — mirrors `WellnessConfig`'s/`AnalyticsConfig`'s own established "defensive upper bound, not a product requirement" field shape).
- `config/defaults.yaml` — matching addition to the `planning:` section.

## Expected Classes

- `TaskEdge` (dataclass) — `from_task_id: str` (the dependency), `to_task_id: str` (the dependent task — cannot run until `from_task_id` is `COMPLETED`).
- `TaskGraph` — constructed from one `Goal` (in-memory, not itself persisted — `TaskGraphStore` owns persistence; `TaskGraph` is the query/mutation layer over an in-memory copy, the same in-memory-representation-over-a-persisted-source split `decision/priority_queue.py`'s `PriorityQueueManager` already uses for its own queue).
- `TaskGraphStore(ManagedModule)` — constructor DI: `(sqlite_client: SqliteClient, planning_config: PlanningConfig)`. Owns its own DDL: `goals`, `milestones`, `tasks`, `task_edges` tables (four tables, one per model level — matching `WorkflowStore`'s own `workflows`/`workflow_steps` two-table precedent, scaled to this sprint's own three-level-plus-edges shape).

## Expected Interfaces

None new.

## Expected Functions

- `TaskGraph.add_dependency(from_task_id: str, to_task_id: str) -> None` — raises `CyclicDependencyError` (new, `planning/errors.py`) if adding the edge would create a cycle (a real depth-first-search cycle check, not a heuristic) — never silently accepts a graph that could deadlock `ready_tasks()`.
- `TaskGraph.ready_tasks() -> list[Task]` — every `Task` whose status is `PROPOSED`/`ACCEPTED` (not yet `IN_PROGRESS`/`COMPLETED`/`ABANDONED`) and whose every incoming `TaskEdge` points at an already-`COMPLETED` task. Two or more ready tasks with no edge between them are real, honest parallel-work candidates — `TaskGraph` never orders them relative to each other.
- `TaskGraph.blocked_tasks() -> list[Task]` — the complement: tasks with at least one incoming edge from a non-`COMPLETED` task.
- `TaskGraph.mark_completed(task_id: str) -> None` / `TaskGraph.mark_failed(task_id: str) -> None` — status transitions; completing a `Task` that leaves every sibling `Task` in its `Milestone` `COMPLETED` cascades the `Milestone`'s own status to `COMPLETED`, and completing every `Milestone` in a `Goal` cascades the `Goal` to `COMPLETED` — the same "derived state recomputed from real children, never a separately-settable flag that could disagree" discipline `wellness/escalation.py`'s `is_hard_limited()` already established at Sprint 5.19.
- `TaskGraphStore.save_goal(goal: Goal) -> None` / `TaskGraphStore.get_goal(goal_id: str) -> Goal | None` / `TaskGraphStore.list_goals(status: PlanningStatus | None = None) -> list[Goal]` / `TaskGraphStore.save_edges(goal_id: str, edges: list[TaskEdge]) -> None`.

## Data Flow

```
Sprint 6.1: PlanningEngine.decompose_goal(statement)  →  Goal (PROPOSED, no edges)
      ↓
(caller, wired at 6.13) constructs a TaskGraph(goal) and optionally calls add_dependency()
for any ordering implied by the tasks themselves (e.g. LLM-suggested ordering, or user-stated
ordering) — this sprint does not infer dependencies automatically; see Potential Risks
      ↓
TaskGraphStore.save_goal(goal) / save_edges(goal_id, edges)   →  persisted (SQLite)
      ↓
(later, on demand) TaskGraph.ready_tasks() / blocked_tasks()
      ↓
Sprint 6.9 (Multi-Step Workflow Engine) — dispatches ready_tasks() as real Actions
Sprint 6.10 (Self Evaluation) — reads completed/failed tasks for outcome analysis
Sprint 6.12 (Adaptive Prioritization) — ready_tasks() output competes with other priority sources
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `PlanningConfig.max_task_dependencies`.
2. `planning/errors.py` — `CyclicDependencyError`.
3. `planning/task_graph.py` — `TaskEdge`, `TaskGraph` (`add_dependency()` with real DFS cycle detection, `ready_tasks()`/`blocked_tasks()`, `mark_completed()`/`mark_failed()` with cascade).
4. `planning/task_graph_store.py` — `TaskGraphStore`, four-table DDL, `save_goal()`/`get_goal()`/`list_goals()`/`save_edges()`.
5. Unit tests: cycle rejection (direct A→B→A, and a longer A→B→C→A chain); `ready_tasks()`/`blocked_tasks()` against a hand-built multi-branch graph including a genuine parallel-work case (two ready tasks, no edge between them); completion cascade (task→milestone→goal); persistence round trip including edges, surviving a store close/reopen.

## Architecture Notes

`TaskGraph.add_dependency()`'s cycle check is a real, non-negotiable safety property — an accepted cycle would make `ready_tasks()` return an empty list forever for the affected tasks with no way to recover except manual data surgery, a genuinely bad failure mode for a system whose whole purpose is helping the user make progress. This is Level 6's own "Safe Failure" design principle applied concretely: reject the bad input at the boundary (`add_dependency()`) rather than letting it corrupt state that only manifests as a confusing silent stall later.

Dependency edges are **not** inferred automatically from a `PlanningEngine` decomposition in this sprint — the LLM's own proposed task ordering (if any, expressed only as list order in the source text) is not parsed into real `TaskEdge`s here. Automatic dependency inference is real, additional LLM-reasoning work (closer to Sprint 6.4's Reasoning Engine territory — "what does this task actually require to be done first?") than a graph-storage concern; building it here would conflate two different jobs. Left as an explicit, disclosed gap — see Potential Risks and Future Considerations.

## Integration Considerations

- No live caller yet. Sprint 6.9 (Multi-Step Workflow Engine) is this Sprint Book's own real consumer of `ready_tasks()`; Sprint 6.13 (Integration) registers `TaskGraphStore` as a real `ManagedModule` with `CoreManager` in `main.py`, the same composition-root pattern every prior storage class has used.
- Sprint 6.10 (Self Evaluation) and Sprint 6.11 (Explainability Layer) both read completed/failed task history from `TaskGraphStore` — neither writes to it.

## Potential Risks

- **No automatic dependency inference** — a `TaskGraph` built directly from Sprint 6.1's output has zero edges (every task immediately "ready") unless a caller explicitly adds them. This is honest (no invented ordering presented as fact) but means naive use produces an all-parallel plan even when real-world ordering obviously matters (e.g. "write the code" before "test the code") — disclosed here rather than silently assumed acceptable; a real candidate for Sprint 6.13's own integration-time prompt design (asking the LLM for ordering hints as part of decomposition) or a later sprint, not decided in this Sprint Book.
- **`TaskGraphStore`'s own SQLite calls have no Fail Gracefully hardening this sprint** — deliberate, matching `CalendarStore`'s/`UsageStore`'s identical precedent (no real caller exists yet to meaningfully degrade for); Sprint 6.14's job once 6.9/6.13 give it real callers.
- **Cascade completion (task→milestone→goal) assumes every task in a milestone is known up front** — a `Milestone` whose task list is mutated after creation (not supported by any function in this sprint) is out of scope; `TaskGraph` treats a `Goal`'s structure as fixed once built, matching the "revision is a Future Consideration" boundary Sprint 6.1 already drew.

## Acceptance Criteria

- `add_dependency()` rejects any 2-cycle or longer cycle with `CyclicDependencyError`, leaving the graph unchanged (not partially applied).
- `ready_tasks()` returns exactly the tasks with no incomplete incoming dependency, including correctly identifying two or more independent ready tasks as parallel candidates.
- `blocked_tasks()` is the exact complement of `ready_tasks()` among non-terminal tasks.
- Completing every task in a milestone cascades that milestone to `COMPLETED`; completing every milestone in a goal cascades the goal to `COMPLETED`. Failing a task does **not** cascade a failure upward automatically (a failed task blocks its own dependents via `blocked_tasks()`, but a `Milestone`/`Goal` is never auto-marked `ABANDONED` — that is a human or Sprint 6.10 judgment call, not a mechanical one).
- A `Goal` with its full milestone/task/edge structure survives a `TaskGraphStore` close/reopen cycle against the same SQLite file, unchanged.

## Testing Checklist

- [ ] Unit: `TaskEdge` construction.
- [ ] Unit: `add_dependency()` — valid edge accepted; direct cycle rejected; longer transitive cycle rejected; graph unchanged after a rejected edge.
- [ ] Unit: `ready_tasks()`/`blocked_tasks()` against a hand-built graph with a genuine parallel-work branch, a linear chain, and an isolated (no-edge) task.
- [ ] Unit: `mark_completed()` cascade (task → milestone → goal), and confirmation that `mark_failed()` does not auto-cascade.
- [ ] Unit: `TaskGraphStore` round trip (goal/milestones/tasks/edges) surviving close/reopen against a real temp-file SQLite database.

## Documentation Checklist

- [ ] `planning/task_graph.py`/`task_graph_store.py` docstrings: the no-automatic-dependency-inference boundary, stated explicitly (per Architecture Notes above).
- [ ] `docs/STATUS.md` — Level 6 Part A narrative extended.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

6.3 — Context Engine.

## Future Considerations

- Automatic dependency inference from a `PlanningEngine` decomposition — named above as a real, disclosed gap; natural territory for Sprint 6.4 (Reasoning Engine) or a later revision, not this sprint.
- Cross-goal dependencies (Task Graph B cannot start until Goal A completes) — no basis in this brief's own singular-goal framing; not built speculatively.
- Goal/task revision after acceptance (adding, removing, or re-ordering tasks mid-flight) — deferred, matching Sprint 6.1's identical boundary.

## Sprint Completion Report (2026-08-06)

Implemented as specified, authorized directly ("continue with the sprint 6.2") right after Sprint 6.1 closed in the same conversation — built directly on 6.1's own just-implemented, uncommitted work, no re-check needed (Sprint 6.1's own files were already confirmed via the tool trace, not memory).

Delivered `planning/errors.py` (`CyclicDependencyError`), `planning/task_graph.py` (`TaskEdge`, `TaskGraph` — real depth-first-search cycle detection via `_can_reach()`, `ready_tasks()`/`blocked_tasks()`, `mark_completed()`/`mark_failed()` with task→milestone→goal cascade), `planning/task_graph_store.py` (`TaskGraphStore` — a `ManagedModule`, real four-table SQLite schema via `SqliteClient`, delete-then-reinsert `save_goal()` mirroring `WorkflowStore`'s own established precedent exactly), and `PlanningConfig.max_task_dependencies` (`config/schema.py`/`config/defaults.yaml`, `_validate_planning()` widened).

**Two real, disclosed additions beyond this sprint file's own literal Expected Classes/Expected Functions text, both found to be genuinely necessary while implementing rather than optional embellishments:**

1. **`TaskGraphStore.get_edges(goal_id) -> list[TaskEdge]`** — the Expected Functions list names only `save_edges()`, no read counterpart. Without it, this sprint's own Acceptance Criteria ("A `Goal` with its full milestone/task/edge structure survives a `TaskGraphStore` close/reopen cycle... unchanged") is literally unsatisfiable — a `Goal` object has no `edges` field of its own (edges are a separate `TaskGraph`-level concept per this sprint's own Engineering Rationale), so nothing else in the store could ever read persisted edges back. Added as the obvious, symmetric counterpart to `save_edges()`, matching every other store's own get/save pairing in this codebase.
2. **`TaskGraph.__init__()` gained `planning_config: PlanningConfig | None = None`** (defaulting to `PlanningConfig()`) — the Expected Classes text describes the constructor only as "constructed from one `Goal`," but `add_dependency()`'s own `max_task_dependencies` bound (this sprint's own Files to Modify field) has to read that value from somewhere, and `TaskGraph` is the only class that calls `add_dependency()`. The same "found a necessary constructor gap, resolved it directly, disclosed it" precedent `WellnessTracker`'s `escalation_manager` (Sprint 5.19) already established for this codebase.

**A real design question resolved directly, not left ambiguous**: which "edges per task" the `max_task_dependencies` bound counts. Chosen: incoming edges into `to_task_id` (a task's own prerequisite count) — the dimension `_is_blocked()`/`ready_tasks()` actually iterate over, so this is the one that matters for correctness/complexity of the graph queries this sprint's own methods perform; outgoing edges (how many other tasks depend on one task) are left unbounded, since nothing in this sprint's own logic scales with that count.

Cycle detection was verified against all three named cases from this sprint's own Testing Checklist (direct 2-cycle, longer transitive 3-cycle, and — added beyond the checklist's own literal list — a self-loop, a degenerate case worth covering since `add_dependency("a", "a")` is a real, plausible caller mistake) — each confirmed to leave `TaskGraph.edges` completely unchanged after a rejected call, not partially applied.

29 new tests: `tests/unit/planning/test_task_graph.py` (16 tests — cycle rejection in all three shapes, the `max_task_dependencies` bound, `ready_tasks()`/`blocked_tasks()` against a genuine parallel-work case/a linear chain/terminal-status exclusion, the completion cascade through all three levels, `mark_failed()`'s deliberate non-cascade, and a dedicated test proving a permanently-`ABANDONED` prerequisite leaves its dependent blocked forever — a real, disclosed consequence of the "no automatic failure cascade" design, not a bug); `tests/unit/planning/test_task_graph_store.py` (13 tests — full round trip including milestone/task ordering, a `None` `estimated_effort` round-tripping correctly, `list_goals()` status filtering, edges round-tripping including the close/reopen persistence case, `health_check()`). Plus 1 more `PlanningConfig` validation test in `tests/unit/config/test_schema.py`.

Full suite verification: `tests/unit/planning/` (29/29) and the widened `test_schema.py` run individually first; then the complete `tests/unit` + `tests/integration` suite (opt-in real-model marker excluded, `test_text_to_speech.py` deselected per its own already-documented unrelated failures) — 1859 passing (1829 + 30 new), zero failures, zero new flakiness. `ruff check .` clean repository-wide.

`docs/STATUS.md` (Level 6 Part A narrative extended, Part A header → "2/15 implemented," Planning & Reasoning phase notes → "6.1–6.2 Complete"), `docs/sprint_book/INDEX.md` (6.2 row → `Complete`) both updated. No `backlog/technical_debt.md` entry needed this sprint — no new top-level package (this sprint extends `planning/`, per its own Engineering Rationale), and the two disclosed additions above are resolved gaps, not open ones.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Sprint 6.1's own still-uncommitted work, the user not yet asked whether to commit. **Sprint 6.3 (Context Engine) is next.**
