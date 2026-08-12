# Sprint 6.14 — Error Handling & Recovery Hardening (Part A)

## Sprint ID

6.14

## Sprint Name

Error Handling & Recovery Hardening (Level 6 Part A)

## Purpose

Apply the Fail Gracefully Rule across Level 6 Part A's own real, newly-wired graph — matching the identical named-scenario hardening sprint every prior Level/Part has closed with (2.13, 3.13, 4.12/4.19, 5.15/5.25). Investigate each scenario against the REAL Sprint 6.13 graph first; fix what's genuinely broken, confirm-via-regression-test what's already correctly handled, and do not fabricate a fix for something that isn't actually broken.

## Engineering Rationale

Six named scenarios, chosen the same way every prior hardening sprint's own six were chosen: real, concrete failure modes this Part's own new code can actually hit, not a generic checklist. Each is investigated against the real Sprint 6.13 graph before any code changes — per this project's own established discipline, some of the six are expected to already be correctly handled (disclosed as "already correct" with a regression test, not silently skipped), matching the honest split every prior hardening sprint has reported (e.g. Sprint 5.25's real 3-fix/3-already-correct split).

## Objectives

Investigate and, where genuinely needed, fix:

**(a) `PlanningEngine.decompose_goal()`/`ReasoningEngine`'s four methods fail when Ollama is unreachable mid-turn.** Both already propagate `LlmError` by design (Sprint 6.1/6.4) — this scenario confirms `CommunicationPipeline._handle_planning_turn()`/`_handle_explanation_turn()` (Sprint 6.13) each catch it and degrade to an honest spoken "I can't reach my reasoning model right now" rather than crashing the turn, mirroring `_handle_internet_agent_turn()`'s own established `LlmError`-catching precedent.

**(b) `TaskGraphStore`/`KnowledgeGraphStore`'s SQLite calls fail.** Both were deliberately left unhardened at their own component sprints (6.2/6.6), matching every prior storage-first-sprint's identical "no real caller yet" reasoning — this sprint gives both real callers via Sprint 6.13, so this is where they get the same degrade-to-empty/`None` treatment `CalendarStore`/`UsageStore` already received at their own hardening sprints.

**(c) `ProactiveAssistant._on_tick()` raises during trigger evaluation.** Confirm `TaskScheduler`'s own existing job isolation (APScheduler's `max_instances=1`, already verified real at Sprint 4.19) absorbs a raised exception from one tick without killing the job's own future recurrence — the same "no try/except of its own by design, absorbed by TaskScheduler" pattern `_check_and_announce_due_reminder()` already established, re-verified here for a NEW job rather than assumed to transfer automatically.

**(d) `AdaptivePrioritizer.next_item()` is called concurrently with `ProactiveAssistant._on_tick()` enqueuing a new item.** A real, concrete race between "read the queue's current top" and "a new item is added" — confirm `PriorityQueueManager`'s own existing thread-safety (or lack thereof) is sufficient, or add the minimal fix if a genuine torn-state read is reproducible.

**(e) A cyclic-dependency rejection (`TaskGraph.add_dependency()`, Sprint 6.2) occurs mid-`_handle_planning_turn()`.** Confirm the turn degrades to an honest "I couldn't build a consistent plan for that" rather than a raised, user-facing stack trace — a real, concrete instance of `CyclicDependencyError` reaching a live turn for the first time (Sprint 6.2's own tests only covered it in isolation).

**(f) `SelfEvaluator.evaluate_workflow_run()` fails (LLM or store failure) immediately after a real `WorkflowRunResult` completes.** Confirm a failed evaluation never blocks or reverses the underlying `TaskGraph.mark_completed()`/`mark_failed()` call that already happened — the task's own real completion state must never be held hostage by a downstream evaluation failure, mirroring Sprint 6.10's own mechanical-outcome-first design applied here at the integration boundary.

## Dependencies

6.13 (the real, wired graph every scenario above is investigated against).

## Files to Modify

Determined by investigation — expected candidates: `voice/pipeline.py` (`_handle_planning_turn()`/`_handle_explanation_turn()`/`_finalize_workflow_run()`), `planning/task_graph_store.py`, `knowledge/knowledge_graph_store.py`, `proactive/proactive_assistant.py`. No new files expected — a hardening sprint adds resilience to existing code, it does not introduce new classes.

## Expected Classes

None new.

## Expected Functions

None new — existing functions gain `try`/`except` boundaries and degrade paths where investigation finds a genuine gap.

## Data Flow

Unchanged from Sprint 6.13 — this sprint adds failure-path branches to existing flows, not new flows.

## Implementation Tasks

1. Investigate scenario (a) against a real, induced `LlmError` at each of the two turn-handler call sites; fix or confirm-via-regression-test.
2. Investigate scenario (b) against a real induced SQLite failure for both stores' own read/write paths; fix or confirm.
3. Investigate scenario (c) against a real `TaskScheduler` with an always-raising `_evaluate_triggers()`; fix or confirm.
4. Investigate scenario (d) with a real concurrent-thread reproduction (matching this project's own "verify a race with a real minimal reproduction, don't just reason abstractly" established discipline); fix or confirm.
5. Investigate scenario (e) by forcing a real cyclic-dependency condition through a live `_handle_planning_turn()` call; fix or confirm.
6. Investigate scenario (f) with a real induced `SelfEvaluator` failure immediately following a genuine `WorkflowRunResult`; fix or confirm.
7. Regression tests for every scenario, whether fixed or already-correct — matching this project's own "confirm-already-correct still gets a test" precedent.
8. Adversarial re-read of every Sprint 6.1–6.13 file this sprint's own six scenarios touch, per this project's own established "freeze sprint finds at least one" pattern — any further genuine gap found gets fixed here (if in-scope-sized) or logged to `backlog/technical_debt.md` (if it would require new cross-file wiring beyond hardening's own scope), using the exact size-based judgment call `docs/sprint_book/sprint_5_26.md`'s own Sprint Completion Report already established as this project's precedent.

## Architecture Notes

Every fix in this sprint follows the Fail Gracefully Rule's own existing shape in this codebase: degrade to an honest, spoken statement of the limitation, log it, never crash the turn, never fabricate success. Nothing in this sprint changes what Level 6 Part A's components *do* when healthy — only what happens when a real collaborator fails.

## Integration Considerations

Sprint 6.15 (Integration Testing & Level Freeze) depends on this sprint's own hardening being complete before its own system-level acceptance pass.

## Potential Risks

- **Scenario (d)'s real concurrency reproduction may find nothing genuinely broken** — `PriorityQueueManager`'s own existing implementation may already be sufficiently safe (it has survived every prior Level's own concurrent-access scenarios without a dedicated lock); if so, this is a confirm-already-correct outcome, documented with a real regression test, not a fabricated fix.
- **The adversarial re-read (Implementation Task 8) may surface a genuine gap sized beyond this sprint's own hardening scope** — per this project's own established precedent, logged to `backlog/technical_debt.md` rather than force-fit into this sprint, if it would require new cross-file wiring rather than a same-file resilience fix.

## Acceptance Criteria

- All six named scenarios are individually investigated against the real Sprint 6.13 graph, each with a real regression test proving the actual behavior (fixed or already-correct).
- No scenario's fix (where one was needed) changes any healthy-path behavior — verified by the full existing Level 6 Part A test suite continuing to pass unchanged.
- Full project test suite (unit + integration + system, opt-in real-model marker excluded) passes with zero new regressions attributable to this sprint's own changes.
- `ruff check .` clean.

## Testing Checklist

- [ ] Regression test per scenario (six total, minimum).
- [ ] Full existing Level 6 Part A suite re-run, confirmed unaffected.
- [ ] Full project suite re-run.

## Documentation Checklist

- [ ] `docs/STATUS.md` — Level 6 Part A phase rows unchanged (a hardening-only sprint doesn't move a phase's status, matching every prior hardening sprint's own precedent), narrative paragraph added describing the real-fix-vs-already-correct split.
- [ ] `docs/sprint_book/INDEX.md` — 6.14 row → `Complete` (once implemented).
- [ ] `docs/backlog/technical_debt.md` — any further gap found during the adversarial re-read, sized beyond this sprint's own scope, logged here.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

6.15 — Integration Testing & Level Freeze (Part A).

## Future Considerations

None beyond what any prior hardening sprint has already named as out of scope — this sprint's own job is narrowly the six scenarios above plus whatever the adversarial re-read genuinely finds.

## Sprint Completion Report (2026-08-12)

Implemented as specified, authorized directly ("continue with sprint 6.14") right after Sprint 6.13 closed. A real, honest split across the six named scenarios: **2 real fixes, 3 confirmed-already-correct, 1 confirmed-unreachable** — plus one further real fix found during the mandated adversarial re-read, beyond the six scenarios' own literal scope.

**(a) LlmError mid-planning/explanation turn — one real fix.** `_propose_new_goal()` already caught `LlmError` correctly (Sprint 6.13's own original implementation). `_handle_explanation_turn()` did not: `ExplainabilityLayer.explain()` falls through to `ReasoningEngine.explain_why()` (raises `LlmError` by design, 6.4) whenever nothing composable exists for the subject, and this call was completely unguarded — left uncaught, it would propagate to `_handle_turn_complete()`'s own outer catch and end the whole session (`SessionEndReason.ERROR`), not merely degrade the one turn as scenario (a) requires. Fixed with a `try`/`except LlmError` around the `explain()` call, degrading to "I can't reach my reasoning model right now." — mirroring `_propose_new_goal()`'s own shape exactly.

**(b) TaskGraphStore/KnowledgeGraphStore SQLite failures — real fixes, both stores.** Neither store had been hardened at its own component sprint (6.2/6.6), by design — Sprint 6.13 is what finally gave each a real caller. `TaskGraphStore.list_goals()`/`get_edges()` and `KnowledgeGraphStore.find_entities()`/`get_entity()`/`_neighbor_ids()` now degrade to `[]`/`None`/`set()` on a SQLite read failure, the identical `CalendarStore.list_due_within()` idiom already established — chosen specifically because every one of these degrades composes correctly with an *already-existing* honest reply at the real call site (`_run_accepted_plan()`'s "you don't have an accepted plan," `SessionResumption.build_workflow()`'s "if not projects: return None"), needing no further pipeline.py change. The one *write* in this scope, `TaskGraphStore.save_goal()` (`_accept_pending_goal()`), got a different treatment: caught at the call site, not inside the store, since a write has no honest "empty" degrade — silently swallowing a failed save would make the pipeline falsely claim "I've saved your plan," the identical "never claim success on a lost write" reasoning `memory/memory_store.py`'s own `store()` already established for `MemoryStoreError`.

**(c) ProactiveAssistant tick isolation — confirmed already correct.** `scheduler/task_scheduler.py`'s own docstring already claims APScheduler absorbs a job's exception without killing future recurrence, verified there for a different job (4.15/4.18) — re-verified here for real, for this specific job, with a real `TaskScheduler` and a `ContextEngine` double that raises on every single tick: the job ticked 3+ times regardless, `health_check()` stayed `True` throughout. No code change needed.

**(d) AdaptivePrioritizer/ProactiveAssistant concurrency race — confirmed already correct.** `PriorityQueueManager` has no lock; `AdaptivePrioritizer.next_item()` calls `peek_next()` exactly once per call (never a two-read pattern that could observe torn state across calls). A real 8-thread stress test (1,600 concurrent `enqueue()` calls racing continuous `peek_next()` reads) found zero errors, zero lost/duplicated items, and no corrupted read, across 5 repeated runs — CPython's GIL plus `heapq`'s C-accelerated implementation over tuples that already sort uniquely on their own monotonic counter (never falling through to comparing the non-orderable `PriorityItem` payload) makes the existing code safe without a lock. No code change needed.

**(e) CyclicDependencyError mid-planning-turn — confirmed unreachable, not merely "already correct."** Investigation found this scenario's own premise, as written, does not hold against the real Sprint 6.13 graph: `TaskGraph.add_dependency()` — the only method that raises `CyclicDependencyError` — has **no caller anywhere in production code**, confirmed via a real, repo-wide AST scan (`tests/unit/planning/test_task_graph.py::test_add_dependency_has_no_production_caller_anywhere`). `PlanningEngine.decompose_goal()` never infers dependency edges (`planning/task_graph.py`'s own module docstring already discloses this, Sprint 6.2), and `TaskGraph.__init__()` accepts an edges list directly (the shape `_run_accepted_plan()` actually uses) without validating it. A stale premise from when this sprint's spec was written, before 6.13's real implementation settled the question — not fabricated a fix for. The adjacent, currently-unreachable finding (`TaskGraph.__init__()` doesn't validate an externally-supplied edge list for cycles) is logged as `backlog/technical_debt.md` item 47 rather than fixed, since nothing in production can produce such a list today — the identical "don't harden speculatively" discipline already applied to `WorkflowStore.save()`/`delete()`/`set_enabled()` at item 27, until (per finding below) a real caller actually arrived.

**(f) SelfEvaluator failure after WorkflowRunResult — confirmed already correct, strengthened tests.** `_finalize_workflow_run()`'s own two `try`/`except` blocks were already independent by Sprint 6.13's own original design: `TaskGraph.mark_completed()`/`mark_failed()` plus `save_goal()` run to completion (or fail-and-log) in the first block, entirely before `SelfEvaluator.evaluate_workflow_run()` is ever reached in the second. Strengthened `test_finalize_workflow_run_swallows_self_evaluator_failure` to actually assert the task's own status was correctly committed despite the evaluator raising (previously only asserted "must not raise"), and added a new reverse-direction test confirming a `save_goal()` failure in the first block doesn't skip the evaluator call in the second either — both directions now genuinely proven, not merely plausible by inspection.

**A further real fix, found during the mandated adversarial re-read (Implementation Task 8), beyond the six named scenarios**: `WorkflowStore.save()` (Sprint 4.9) was deliberately left unhardened at every prior sprint — `backlog/technical_debt.md` item 27 explicitly named it as having "zero production callers of any of the three" writes, to be hardened "once a workflow-authoring UI/voice surface finally calls them." Sprint 6.13 is exactly that surface: `_run_accepted_plan()` and `_resume_previous_session()` both now call `save()` for real, and neither guarded it — an uncaught failure there would hit the same coarse outer-catch/session-ending fate as (b)'s `TaskGraphStore.save_goal()` gap, before `WorkflowExecutor.run()` is ever even reached. Fixed identically: caught at both call sites in `voice/pipeline.py`, degrading to "I couldn't set up your plan to run right now." / "I couldn't set up your session to resume right now." respectively.

**Tests**: 2 new tests in `tests/unit/planning/test_task_graph_store.py` (scenario b reads), 3 new in `tests/unit/knowledge/test_knowledge_graph_store.py` (scenario b reads), 1 new in `tests/unit/decision/test_priority_queue.py` (scenario d, the concurrent stress test), 1 new in `tests/unit/planning/test_task_graph.py` (scenario e, the AST reachability proof), 1 new in `tests/unit/proactive/test_proactive_assistant.py` (scenario c), and 8 new in `tests/unit/voice/test_pipeline.py` (scenario a ×2, scenario b's `save_goal()`/`save()` ×3, scenario f's strengthened/reverse tests ×2, plus one strengthened pre-existing test) — 16 new regression tests total, at least one per scenario as required, several covering multiple angles of the same scenario.

Full suite (unit + integration + system): 2331 passing + 5 skipped + exactly 3 failures, all individually investigated and confirmed pre-existing, unrelated flakes — `test_full_level3_acceptance_scripted_conversation` (the well-documented host-load `wait_for_dormant`-class flake since Sprint 3.13, passed cleanly standalone), `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` (the well-documented real-Ollama-nondeterminism flake since Sprint 5.2, in `decision/context_analyzer.py`, untouched by this or any Level 6 sprint), and `test_level4_part_a_full_acceptance_scenario` (the identical host-load flake class already documented at Sprint 6.12's own STATUS.md entry — 3 standalone re-runs produced 1 pass and 2 failures with *two different* failure signatures, `wait_for_dormant` timeout then `spoken_event` timeout, itself sufficient evidence of environmental flakiness rather than a deterministic regression, per this project's own established "different failures each time" precedent). A first full-suite attempt this session ran anomalously long (94 minutes at Sprint 6.13, a similar pattern recurring here); a clean re-run confirmed normal (~11 minute) timing, consistent with transient host contention rather than anything this sprint's own changes caused. `ruff check .` clean repo-wide.

`docs/backlog/technical_debt.md` item 47 added (the scenario (e) disclosed finding). Per this sprint's own Documentation Checklist, `docs/STATUS.md`'s Level 6 Part A phase rows are deliberately left unchanged — a hardening-only sprint doesn't move a phase's status, matching every prior hardening sprint's own precedent (2.13, 3.13, 4.12/4.19, 5.15/5.25) — only the narrative paragraph gains this sprint's own entry. `docs/sprint_book/INDEX.md` (6.14 row → `Complete`).

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Sprints 6.1–6.13's own still-uncommitted work, the user not yet asked whether to commit. **Sprint 6.15 (Integration Testing & Level Freeze, Part A) is next — the final sprint of Level 6 Part A.**
