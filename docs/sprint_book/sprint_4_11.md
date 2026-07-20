# Sprint 4.11 — Workflow & Device Control Integration

## Sprint ID

4.11

## Sprint Name

Workflow & Device Control Integration

## Purpose

Wire every component built in Sprints 4.1–4.10 into one real system inside `main.py`, and — for the first time — give the Decision Engine's `EngineSelection.DEVICE_CONTROL`/`EngineSelection.WORKFLOW` (3.11, reserved since Level 3) a real handler, so a live conversation turn classified as an action request can actually reach the Action Engine. This is the exact role Sprint 2.12 played for Level 2 and Sprint 3.12 played for Level 3, applied to Level 4 Part A.

## Engineering Rationale

**New sprint**, following the precedent both `docs/sprint_book/INDEX.md`'s Level 2 and Level 3 breakdown-changes notes already established and named explicitly: *"Level 2's real-time, hardware-and-ML-dependent integration surface is much larger than Level 1's, so wiring... [is] given its own planned sprint"* (Level 2 note) and the identical reasoning restated for Level 3. Level 4 Part A's integration surface — ten components, five of which (4.2–4.5, 4.9–4.10) perform real, consequential, occasionally destructive actions on the user's actual machine — is at least as large and materially higher-stakes than either prior level's, so it earns the same dedicated sprint, not a fold-in to the last component sprint.

This sprint is also where `decision/authority.py`'s own module docstring is finally made accurate: it has stated since Sprint 3.11 that `DEVICE_CONTROL`/`WORKFLOW` are *"reserved: Level 4"* — this is the sprint that keeps that promise.

## Objectives

- `main.py` constructs every Level 4 Part A subsystem via DI and registers each `ManagedModule` with `CoreManager`, in dependency order, exactly as `main.py` already does for Levels 1–3.
- `decision/authority.py`'s `AuthorityEvaluator._determine_engine()` gains real logic: an `ACTION_REQUEST`-categorized `Intent` (3.7) whose `ContextAnalysis` (3.8) indicates a device-control-shaped target routes to `EngineSelection.DEVICE_CONTROL`; a request naming a stored workflow by name routes to `EngineSelection.WORKFLOW`. Every other `Intent`/`ContextAnalysis` combination keeps its exact existing Level 3 behavior — this is an additive branch, not a rewrite.
- `voice/pipeline.py`'s `CommunicationPipeline` gains a new handling branch: when `DecisionTrace.selected_engine` is `DEVICE_CONTROL`/`WORKFLOW`, build the corresponding `ActionRequest` (or resolve the named `WorkflowDefinition`) and dispatch it through the Action Engine, folding the resulting `ActionResult`/`WorkflowRunResult` into the spoken reply (via the active persona, so the user hears "Done — I opened Notepad" rather than silence).
- A real, end-to-end smoke run: a live conversation turn ("open notepad") actually launches Notepad through the full stack (Intent Detection → Context Analysis → Authority Evaluation → Action Engine → Permission Gate → Application Manager → Audit Log → spoken confirmation).
- `AuthorityEvaluator` is constructed with a real, reviewed `approved_emergency_procedures` value, per Sprint 4.7's own deferred decision.

## Dependencies

4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10 (every Level 4 Part A component sprint), 2.12 (Communication Pipeline Integration), 3.12 (Decision Engine Integration)

## Files to Create

- `tests/integration/test_action_engine_integration.py` — real (non-mocked, except at the true OS/hardware boundary where unavoidable) collaborators wired together, mirroring `tests/integration/test_communication_pipeline.py`'s (2.12) own structure.
- `tests/integration/test_workflow_integration.py` — a real multi-step workflow, defined and executed through the real stack.

## Files to Modify

- `main.py` — construct `ActionRegistry`, `PermissionGate`, `PermissionPolicyEngine`, `ConfirmationService`/`VoiceConfirmationService`, `ActionResourceGate`, `ActionAuditLog`, `ActionRecoveryManager`, `ApplicationManager`, `FileOperationsManager`, `WindowManager`, `CommandExecutionEngine`, `WorkflowStore`, `WorkflowExecutor`; register every `ManagedModule` with `CoreManager`; register every executor with `ActionRegistry`; reconstruct `AuthorityEvaluator` with the real `approved_emergency_procedures` value (Sprint 4.7).
- `decision/authority.py` — `_determine_engine()` additive extension for `DEVICE_CONTROL`/`WORKFLOW` routing; module docstring updated to remove "reserved: Level 4" language for these two values specifically (the other reserved values — `SCHEDULER`, `INTERNET_AGENT`, `WELLNESS`, `EMOTION_SUPPORT` — remain reserved, unchanged, since Level 4 Part B and Level 5 own those).
- `voice/pipeline.py` — `CommunicationPipeline` gains the `DEVICE_CONTROL`/`WORKFLOW` handling branch described above.

## Expected Classes

No new classes — this sprint composes Sprints 4.1–4.10's existing classes; `CommunicationPipeline` and `AuthorityEvaluator` are modified, not replaced.

## Expected Interfaces

None new.

## Expected Functions

- `AuthorityEvaluator._determine_engine(intent: Intent, context_analysis: ContextAnalysis) -> EngineSelection` (signature grows a `context_analysis` parameter — an additive, reviewed change to an existing Level 3 method, the same category of change Sprint 3.9's Completion Report already precedent-set for additive extensions to shipped Level 3 files) — for `IntentCategory.ACTION_REQUEST`, inspects `context_analysis`'s entities for a device-control-shaped target (an application name, a file/folder path, a stored workflow name) and returns `DEVICE_CONTROL` or `WORKFLOW` accordingly; falls back to the existing Level 3 behavior (`CONVERSATIONAL_RESPONSE`, honestly explained as a capability gap) when no concrete target can be resolved — the exact honesty precedent `_build_reasoning()`'s `_INFERRED_FUTURE_ENGINE` mapping already established, now retired for these two values specifically since the gap it named is closed.
- `CommunicationPipeline._handle_device_control_turn(trace: DecisionTrace) -> None` — internal; builds an `ActionRequest` from `trace`'s intent/context/session, dispatches via `ActionRegistry`, and passes the resulting `ActionResult` to the active persona for a spoken confirmation.
- `CommunicationPipeline._handle_workflow_turn(trace: DecisionTrace, workflow_name: str) -> None` — internal; resolves `workflow_name` via `WorkflowStore`, calls `WorkflowExecutor.run()`, and reports the `WorkflowRunResult` similarly.

## Data Flow

```
"Open Notepad" (live conversation turn)
      ↓
IntentDetector (3.7) → Intent(category=ACTION_REQUEST)
      ↓
ContextAnalyzer (3.8) → ContextAnalysis(entities=["notepad"], ...)
      ↓
MemoryRetrievalEngine (3.9) / PriorityQueueManager (3.10)
      ↓
AuthorityEvaluator.evaluate() → _determine_engine() → EngineSelection.DEVICE_CONTROL
      ↓
DecisionTrace(selected_engine=DEVICE_CONTROL, ...)
      ↓
CommunicationPipeline._handle_device_control_turn(trace)
      ↓
ActionRequest(action_type=LAUNCH_APPLICATION, parameters={"executable_path": "notepad.exe"}, context=ActionContext(decision_trace=trace))
      ↓
ActionRegistry.dispatch()  [PermissionGate → ActionResourceGate → ApplicationManager.execute() → ActionAuditLog.record()]
      ↓
ActionResult(SUCCEEDED, output=TrackedApplication)
      ↓
active_persona.compose_reply(..., action_result=result) → "Done — I've opened Notepad." → spoken via TTS
```

## Implementation Tasks

1. `main.py` — construct and register the full Level 4 Part A object graph, following the existing `_construct_level3_modules()`/`_register_level3_modules()` two-phase pattern (construction, then registration) already established for exactly this kind of late-registered, cross-cutting module set.
2. `decision/authority.py` — `_determine_engine()` extension, docstring update.
3. `voice/pipeline.py` — `_handle_device_control_turn()`, `_handle_workflow_turn()`.
4. `requirements.txt`/venv — confirm `APScheduler` remains correctly NOT yet installed (Level 4 Part B's own concern, per `backlog/technical_debt.md` item 1's per-phase policy); confirm `pyautogui`, `pywin32`, `Send2Trash` are all genuinely installed by this point (carried forward from Sprints 4.2/4.3).
5. Integration tests, plus a real, non-mocked smoke run (mirroring Sprint 2.12/3.12's own precedent) — see Testing Checklist for the safety constraints this specific smoke run requires that no prior level's did.

## Architecture Notes

This sprint's `_determine_engine()` extension is deliberately narrow: it resolves a concrete, nameable target (an installed application, an existing stored workflow) or it doesn't route to Device Control/Workflow at all, falling back to the existing conversational path. It does not attempt any general-purpose natural-language command parsing ("open the thing I was working on yesterday") — that is a real future capability with no current spec basis, and building it here would silently and speculatively expand this sprint's own scope well beyond "wire what already exists together," the exact discipline Sprint 2.12/3.12 both held to.

`CommunicationPipeline`'s existing structure (a single `_run_decision_pipeline()` call producing one `DecisionTrace`, then a reply-composition step) is preserved — this sprint adds new terminal branches after the trace is produced, it does not restructure the pipeline itself, matching this class's own stated purpose ("owns *only* the event wiring... no new business logic," Sprint 2.12's Objectives).

## Integration Considerations

- This sprint is the first live caller for `ActionRegistry`, `PermissionGate`'s real policy engine, `ActionResourceGate`, `ActionAuditLog`, `WorkflowExecutor` — every "no live caller yet" note in Sprints 4.1–4.10's own Integration Considerations sections is resolved here, explicitly, not left to accumulate as more technical-debt-log entries the way `backlog/technical_debt.md` items 11/15/17 did across Levels 2–3.
- `AuthorityEvaluator.approved_emergency_procedures`'s real value (decided during Sprint 4.7) is what this sprint's own `main.py` construction actually passes in — if Sprint 4.7 deliberately shipped an empty value pending further review (an acceptable Sprint 4.7 outcome per its own Acceptance Criteria), this sprint constructs `AuthorityEvaluator()` with that same empty default, unchanged from Level 3 — this sprint does not itself decide the whitelist's contents.
- Level 4 Part B (Scheduler, Internet Agent), when it arrives, will extend this exact same `_determine_engine()` method for `EngineSelection.SCHEDULER`/`INTERNET_AGENT` — this sprint's own additive-branch pattern is the one that future work is expected to follow, not a one-off.

## Potential Risks

- **This is the first Sprint Book integration test that can cause real, consequential, occasionally destructive effects on the machine running it** (launching real applications, real file operations under Sprint 4.3's recycle-bin-delete safety net) — unlike every prior integration test (Sprints 2.12, 3.12), which only ever read/wrote temp files or exercised in-memory/local-model state. Every destructive-shaped integration test **must** operate exclusively within a `tmp_path`-scoped `allowed_file_roots` and against test-only, disposable applications/processes (matching Sprints 4.2's and 4.3's own individual-sprint testing constraints, now exercised together at integration scale) — never against the developer's real Documents, Desktop, or running applications.
- **Real end-to-end smoke run risk is categorically higher than any prior level's** — Sprints 2.12/3.12's smoke runs risked, at worst, a slow startup or a missed audio cue; a Level 4 Part A smoke run risks a real unwanted application launch, window operation, or file change on the actual machine if a test double is misconfigured. This sprint's own real-machine verification (mirroring Sprint 2.12's "real smoke run, scratchpad, not committed" precedent) must be run with `allowed_file_roots` pointed at a disposable scratch directory and `approved_commands` left at its safe, minimal Sprint 4.7 value — not the developer's real environment's own broader configuration, if one exists.
- **`_determine_engine()`'s entity-to-target resolution is a real, if narrow, new inference surface** — a misresolved entity (e.g. "notepad" ambiguously matching both a real application and an unrelated stored workflow of the same name) needs a deterministic, tested tie-breaking rule (this sprint's own implementation decision, not specified in advance) rather than undefined behavior.

## Acceptance Criteria

- A live conversation turn requesting a concrete, safe device-control action (application launch) is correctly routed through `EngineSelection.DEVICE_CONTROL` and actually performed, with a spoken confirmation reflecting the real result.
- A live conversation turn naming a stored, enabled workflow is correctly routed through `EngineSelection.WORKFLOW` and executed via `WorkflowExecutor.run()`.
- Every Level 3 acceptance criterion (Phase 3.1/3.2/3.3, per `sprint_3_14.md`'s own Acceptance Pass) continues to pass with no regression — this sprint changes `decision/authority.py`/`voice/pipeline.py` additively, verified by the full existing test suite passing unmodified alongside the new tests.
- `main.py` still starts and stops cleanly with the full Level 1–4 Part A module set registered.
- Every Level 4 Part A module appears in the existing Status Panel via `module_states()` with zero `ui/status_panel.py` changes (mirroring Sprint 2.12's own confirmed-by-inspection precedent).

## Testing Checklist

- [ ] Integration: live-turn-to-real-action round trip for `LAUNCH_APPLICATION` (`tests/integration/test_action_engine_integration.py`), using a disposable test application and a `tmp_path`-scoped config.
- [ ] Integration: live-turn-to-real-workflow-run round trip (`tests/integration/test_workflow_integration.py`), a multi-step workflow confined entirely to `tmp_path` and disposable processes.
- [ ] Integration: a `HIGH`-risk step correctly triggers Sprint 4.7's confirmation flow within the full live-turn path, not just in Sprint 4.7's own isolated tests.
- [ ] Regression: full existing Level 1–3 test suite (623+ tests as of `v0.3.0`) passes unchanged.
- [ ] Manual/real, in a disposable scratch environment only: a live spoken "open notepad"-shaped request actually opens Notepad and JARMINEI reports it correctly — the same category of manual verification Sprint 2.12/3.12 both required and clearly separated from automated coverage.

## Documentation Checklist

- [ ] `decision/authority.py` docstring: `DEVICE_CONTROL`/`WORKFLOW` reservation language removed, replaced with a description of the real routing logic and its deliberately narrow scope.
- [ ] `voice/pipeline.py` docstring: the two new handling branches, in the same wiring-diagram style as Sprint 2.12's own docstring update.
- [ ] `docs/STATUS.md` — Phase 4.1/4.2 rows confirmed `Complete` in combination; integration-verified note added, matching Sprint 2.12/3.12's own precedent.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

High — the largest composition surface of any Level 4 Part A sprint, and the first with real-world destructive-action risk in its own testing.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

4.12 — Error Handling & Recovery Hardening.

## Future Considerations

- Richer entity-to-target resolution (fuzzy matching, disambiguation prompts for ambiguous targets) — a real future refinement of `_determine_engine()`'s own narrow scope, not built speculatively.
- Extending `_determine_engine()` for `SCHEDULER`/`INTERNET_AGENT` — explicitly Level 4 Part B's own future sprint, following this sprint's own additive-branch pattern.
