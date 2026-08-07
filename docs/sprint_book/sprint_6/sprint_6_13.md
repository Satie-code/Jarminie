# Sprint 6.13 — Autonomous Intelligence Integration

## Sprint ID

6.13

## Sprint Name

Autonomous Intelligence Integration

## Purpose

Wire every component built across Sprints 6.1–6.12 into the real, running system — `main.py`/`CoreManager` construction, `voice/pipeline.py`'s `CommunicationPipeline` live-turn routing — the same composition-root role every prior Level's own Integration sprint has played (Sprint 2.12, 3.12, 4.11/4.18, 5.14/5.24). This sprint is also where the brief's own 13th named system, **Cross-System Coordination** ("Coordinate: Memory, Emotion, Workflow, Device Control, Internet, Presentation... without tight coupling"), is realized — not as a new coordinator class, but as this sprint's own composition-root wiring, exactly as every prior Level's Integration sprint has already coordinated its own Level's subsystems without a dedicated "coordinator" class ever existing anywhere in this codebase.

## Engineering Rationale

**Cross-System Coordination is deliberately not given its own component sprint or class**, a real, disclosed departure from the brief's own suggested progression (which lists it as item 12, immediately before Integration). Building a standalone `CrossSystemCoordinator` would duplicate a role `voice/pipeline.py`'s `CommunicationPipeline` and `main.py`'s own construction sequence have played at every Level since Sprint 2.12 — a second coordination layer alongside the first would be the exact kind of tight coupling ("a coordinator that needs to know about every subsystem to coordinate them") the brief's own "without tight coupling" instruction warns against. Folding Cross-System Coordination into this sprint (rather than adding it as a 16th sprint) keeps this Book at 15 sprints, matching the brief's own "approximately 12–15" target while still delivering everything the brief named.

Every other Level's Integration sprint is this sprint's own direct precedent for scope and shape: register new `ManagedModule`s with `CoreManager`, extend `EngineSelection`/`_determine_engine()` for any new live conversational entry point, extend `voice/pipeline.py` with new `_handle_X_turn()` methods, and confirm the whole graph starts up and shuts down cleanly together.

## Objectives

- Register `TaskGraphStore` (6.2), `KnowledgeGraphStore` (6.6), `ProactiveAssistant` (6.8) as real `ManagedModule`s with `CoreManager` in `main.py`.
- Construct `PlanningEngine`, `ContextEngine`, `ReasoningEngine`, `DecisionEngineV2`, `ExplainabilityLayer`, `AdaptivePrioritizer`, `TaskGraphWorkflowAdapter`, `SessionResumption`, `SelfEvaluator` (all plain, non-`ManagedModule` classes) in `main.py`'s own composition sequence, wired with their real collaborators.
- Widen `EngineSelection` (`decision/authority.py`) with `PLANNING` and `EXPLANATION`, and `_determine_engine()`'s own keyword/intent routing for both.
- New `CommunicationPipeline._handle_planning_turn()` (routes a goal-planning request through `PlanningEngine` → `TaskGraph` → user review, and a "run my plan"/"resume my session" request through `TaskGraphWorkflowAdapter`/`SessionResumption` → `WorkflowExecutor`) and `_handle_explanation_turn()` (routes a "why?" question through `ExplainabilityLayer`).
- Wire `ProactiveAssistant`'s own enqueued items into the existing `_check_and_announce_priority_item()` dispatch table (already source-agnostic since Sprint 5.24 — confirmed, not re-verified from scratch, that no dispatch-table change is needed, only a new producer) — this is the sprint that finally, fully closes `backlog/technical_debt.md` item 17's `IMPORTANT_ALERT` gap.
- Replace `_check_and_announce_priority_item()`'s direct `priority_queue_manager.pop_next()` call with `AdaptivePrioritizer.next_item()`-informed dispatch (Sprint 6.12).
- Wire `WorkflowRunResult`s produced from a `TaskGraph`-derived workflow back onto the originating `Task`s (`TaskGraph.mark_completed()`/`mark_failed()`, deferred by Sprint 6.9 to this sprint) and onward into `SelfEvaluator.evaluate_workflow_run()` (Sprint 6.10).

## Dependencies

6.1–6.12 (all of Level 6 Part A's own component sprints), 2.12 (`CommunicationPipeline`), 3.11 (`AuthorityEvaluator`, `EngineSelection`), 5.24 (`_check_and_announce_priority_item()`'s existing dispatch table).

## Files to Create

- `tests/integration/test_autonomous_intelligence_integration.py`

## Files to Modify

- `main.py` — a new `_Level6PartAModules` bundle (mirroring `_Level5PartBModules`'s own established null-fallback-safe construction shape from Sprint 5.24), registered after Level 5 Part B's own modules.
- `decision/authority.py` — `EngineSelection` widened with `PLANNING = "planning"`, `EXPLANATION = "explanation"`; `_determine_engine()` gains keyword-gated routing for both (new keyword tuples, e.g. `_PLANNING_KEYWORDS`/`_EXPLANATION_KEYWORDS`, matching the existing `_WORKFLOW_KEYWORDS` shape exactly); the docstring correction Sprint 6.11 already flagged, applied for real here.
- `voice/pipeline.py` — `_handle_planning_turn()`, `_handle_explanation_turn()`; `_check_and_announce_priority_item()` modified to consult `AdaptivePrioritizer.next_item()` before popping; a new `_finalize_workflow_run()` step wiring `WorkflowRunResult` → `TaskGraph.mark_completed()`/`mark_failed()` → `SelfEvaluator.evaluate_workflow_run()`.
- `docs/backlog/technical_debt.md` — item 17 (`IMPORTANT_ALERT`) marked fully resolved; new entries for the five new top-level packages (`planning/`, `context/`, `reasoning/`, `knowledge/`, `proactive/`), matching the `emotion/`/`presentation/` precedent, added now that they are actually implemented.

## Expected Classes

- `_Level6PartAModules` (in `main.py`, matching every prior Level's own private construction-bundle dataclass shape) — holds every Level 6 Part A instance, `X | None` typed throughout, so a construction failure anywhere in the bundle degrades the whole Part to inert (every new turn-type falls back to "not currently available," never a half-wired partial graph) — the same all-`None` null-fallback shape `_Level5PartBModules` already established.

## Expected Interfaces

None new.

## Expected Functions

- `CommunicationPipeline._handle_planning_turn(trace: DecisionTrace) -> str` — for a fresh goal statement: calls `planning_engine.decompose_goal()`, presents the proposed `Goal` back to the user for review (spoken summary of milestones/tasks — never auto-accepted), and only constructs a `TaskGraph`/persists it via `TaskGraphStore` once explicitly accepted in a follow-up turn (`PlanningStatus.PROPOSED → ACCEPTED`, a real Human-First gate, not a formality). For a "run my plan"/"resume my session" request against an already-`ACCEPTED` `Goal`: builds a `WorkflowDefinition` via `TaskGraphWorkflowAdapter`/`SessionResumption`, saves it, and runs it through the existing `WorkflowExecutor` — any step requiring confirmation is gated exactly as any other workflow already is, unchanged.
- `CommunicationPipeline._handle_explanation_turn(trace: DecisionTrace) -> str` — resolves the subject of "why?" from the most recent non-explanation turn's own `DecisionTrace`/outcome (using `voice/context_manager.py`'s existing recent-turn window), builds an `ExplanationRequest`, calls `explainability_layer.explain()`.
- `CommunicationPipeline._check_and_announce_priority_item()` — widened: builds a `WorkingContext` via `context_engine.build()`, calls `adaptive_prioritizer.next_item(working_context)` when `adaptive_prioritizer` is available (falls back to the pre-6.12 direct `pop_next()` behavior when it is not — the Level 6 Part A degrade-to-absent discipline applied at the integration boundary itself), and only pops/announces on `SURFACE_NOW`.

## Data Flow

```
Live turn ("Help me plan X" / "Run my plan" / "Resume my session" / "Why did you...?")
      ↓
decision/authority.py's _determine_engine()  →  EngineSelection.PLANNING / EXPLANATION
      ↓
CommunicationPipeline._handle_planning_turn() / _handle_explanation_turn()
      ↓
   (planning)                                    (explanation)
PlanningEngine → TaskGraph → user review →       ExplainabilityLayer.explain()
TaskGraphWorkflowAdapter/SessionResumption →
WorkflowExecutor.run() (existing, unchanged)
      ↓
WorkflowRunResult
      ↓
_finalize_workflow_run(): TaskGraph.mark_completed()/mark_failed()  →  SelfEvaluator.evaluate_workflow_run()

--- separately, on the existing TaskScheduler-driven cadence ---

ProactiveAssistant._on_tick()  →  PriorityQueueManager.enqueue()
      ↓
_check_and_announce_priority_item()  →  ContextEngine.build() → AdaptivePrioritizer.next_item()
      ↓
SURFACE_NOW  →  pop_next() + announce (existing QuietModeController-gated mechanism, unchanged)
```

## Implementation Tasks

1. `decision/authority.py` — `EngineSelection.PLANNING`/`EXPLANATION`, keyword routing, docstring correction.
2. `main.py` — `_Level6PartAModules`, construction and `CoreManager.register_module()` calls for `TaskGraphStore`/`KnowledgeGraphStore`/`ProactiveAssistant`.
3. `voice/pipeline.py` — `_handle_planning_turn()`, `_handle_explanation_turn()`, `_finalize_workflow_run()`, `_check_and_announce_priority_item()` widened for `AdaptivePrioritizer`.
4. `docs/backlog/technical_debt.md` — item 17 closed; five new package entries added.
5. Integration tests: a full goal-planning-to-acceptance-to-execution scripted flow through the real `CoreManager` graph; a "why?" follow-up after a planning turn; a real `TaskScheduler`-cadence proof that `ProactiveAssistant` enqueues and `_check_and_announce_priority_item()` announces it while `DORMANT`; a graceful-degrade test with the entire `_Level6PartAModules` bundle `None` (every new turn type falls back to an honest "not currently available" reply, the rest of the system unaffected — matching Sprint 5.24's own identical graceful-degrade precedent).

## Architecture Notes

This sprint touches `decision/authority.py` and `voice/pipeline.py` — both files every prior Level's own Integration sprint has already touched — but never touches `personas/`, `memory/`, `device_control/`, or `presentation/` directly; every new Level 6 Part A capability reaches those subsystems exclusively through already-existing, already-hardened entry points (`WorkflowExecutor.run()`, `ActionRegistry.dispatch()`, `MemoryStore`/`PersonaScopedMemory`'s own existing read methods). This is the concrete, verifiable form of "without tight coupling": Level 6 Part A adds five new packages and widens three existing ones, and the number of *existing* files this sprint needs to modify to connect them all is exactly two.

## Integration Considerations

- This is the sprint every Level 6 Part A component sprint (6.1–6.12) has deferred its own live wiring to — consistent with the "component sprint ships untethered, the Level's Integration sprint wires it" precedent stated explicitly in each of their own files.
- Sprint 6.14 (Error Handling & Recovery Hardening) and Sprint 6.15 (Integration Testing & Level Freeze) both depend on this sprint's own real, wired graph — neither can meaningfully test failure/acceptance scenarios against components that are still standalone.

## Potential Risks

- **The largest single-sprint surface-area risk in this Book** — matching every prior Level's own "the Integration sprint is the largest" pattern (Sprint 4.18, Sprint 5.24) — a real, disclosed concentration of risk rather than spread evenly, consistent with precedent.
- **`_handle_planning_turn()`'s propose-then-accept two-step flow needs real conversational-state tracking across turns** (has this `Goal` already been proposed and is the user now responding to it, or is this a fresh request?) — the same class of multi-turn-state problem `voice/context_manager.py`'s existing recent-turn window already solves for ordinary conversation; reused here, not reinvented, but worth flagging as the sprint's own most delicate piece of new conversational logic.
- **A `Task`-Graph-derived `WorkflowDefinition`'s own steps may include an inert `SYSTEM_COMMAND`** (per Sprint 6.9's own disclosed `approved_commands`-empty-by-default consequence) — this sprint does not change that gate; a user running the brief's own worked example for the first time will see the Git-pull step require separate, deliberate allowlist approval, which is correct, safe behavior, not a bug to fix here.

## Acceptance Criteria

- A full "plan a goal → review → accept → run → evaluate" flow completes end-to-end through the real `CoreManager` graph, with a human-reviewable proposal step that is never silently auto-accepted.
- A "why did you...?" follow-up question after a planning or workflow turn produces a real, sourced `Explanation`.
- `ProactiveAssistant`'s own enqueued items are announced only when `DORMANT` and only when `AdaptivePrioritizer` resolves `SURFACE_NOW`, verified via real `TaskScheduler` cadence (not a synthetic direct call).
- With the entire Level 6 Part A module bundle absent (`None`), every pre-existing turn type (Level 1–5) continues to function exactly as before, and any Level-6-Part-A-shaped request degrades to an honest, spoken "not currently available" — never a crash, never a silent no-op.
- `backlog/technical_debt.md` item 17 is marked fully resolved.

## Testing Checklist

- [ ] Integration: full plan → accept → run → evaluate scripted flow.
- [ ] Integration: explanation follow-up after a planning/workflow turn.
- [ ] Integration: real `TaskScheduler`-cadence `ProactiveAssistant` → `AdaptivePrioritizer` → announcement flow, `DORMANT`-gated.
- [ ] Integration: entire Level 6 Part A bundle `None` — full graceful-degrade sweep across every new turn type.
- [ ] Integration: `CoreManager.startup()`/`shutdown()` with the complete Level 1–6 Part A graph registered, clean start and stop.
- [ ] Unit: `_determine_engine()` routing for `PLANNING`/`EXPLANATION` keyword sets.

## Documentation Checklist

- [ ] `docs/STATUS.md` — Level 6 Part A phases → `Developing`.
- [ ] `docs/sprint_book/INDEX.md` — 6.13 row → `Complete` (once implemented).
- [ ] `docs/backlog/technical_debt.md` — item 17 closed; five new package entries recorded.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

High.

## Estimated Development Time

3–4 days.

## Risks

See Potential Risks above.

## Next Sprint

6.14 — Error Handling & Recovery Hardening.

## Future Considerations

- A settings-UI surface for enabling/disabling individual Level 6 Part A capabilities — no basis in this brief; `ui/` untouched by this entire Sprint Book.
- Persisting the propose/accept planning-flow's own conversational state more durably than the existing recent-turn window, if real usage shows users returning to an old proposal after the window has rolled past it — not assumed necessary here.
