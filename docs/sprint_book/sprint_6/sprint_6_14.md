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
