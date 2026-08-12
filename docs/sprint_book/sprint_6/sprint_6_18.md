# Sprint 6.18 — Stress & Recovery Testing

## Sprint ID

6.18

## Sprint Name

Stress & Recovery Testing

## Purpose

Deliver Phase 6.2's own first named task pair, "Stress testing. Recovery testing," as real, runnable test infrastructure — a category that has never existed in this codebase before this sprint. Confirmed by research: zero matches anywhere in the repo for "stress"/"load_test"/"long_duration"/"endurance"/"soak" as test infrastructure (the only "stress" hits are unrelated `EmotionalState`/persona "stress level" fields). The closest precedent is Sprint 6.14 scenario (d)'s own real, minimal 8-thread/1,600-item `PriorityQueueManager` concurrency reproduction — this sprint generalizes that same "verify a real, concrete reproduction, don't just reason abstractly" discipline from one collaborator to the whole system.

## Engineering Rationale

Two distinct concerns, each with its own real test shape: **stress** (sustained, concurrent load — does the system stay correct and responsive, not just "not crash"), and **recovery** (a real failure is induced mid-run, then cleared — does the system come back on its own, or does it stay degraded after the cause is gone). Neither has been exercised at the whole-system level before; every prior hardening sprint's own scenarios (2.13 through 6.14) tested individual failure modes in isolation, never sustained concurrent load across the full, real `CoreManager` graph. Interval-scaling for a practical automated run mirrors this project's own already-established `fast_*_harness` convention (accelerated `TaskScheduler` intervals for a test's own patience) rather than a literal multi-hour endurance run, which no CI exists to host anyway (Sprint 6.23's own Future Considerations).

## Objectives

- `tests/system/test_level6_part_b_stress.py` — a sustained-load scenario: all 13 recurring `TaskScheduler` jobs (Sprint 6.17's own audited inventory) active at accelerated intervals, concurrent conversation turns driven through `CommunicationPipeline` for a bounded but genuinely sustained window (target: several minutes of real wall-clock activity, not a few seconds), watching for unhandled exceptions, RSS growth beyond a documented bound (reusing Sprint 6.16's own measurement approach), and any hang (every wait bounded with a timeout, matching this project's own established `wait_until()`/`wait_for_dormant()` convention).
- Recovery scenarios, each inducing a real failure mid-run and confirming the system recovers once the cause clears, without requiring a restart: (a) Ollama becomes unreachable mid-session, then reachable again — confirm `PlanningEngine`/`ReasoningEngine`/`IntentDetector` calls resume succeeding once it's back, not permanently degraded by the earlier failure; (b) the SQLite database file becomes temporarily locked/unwritable, then clears — confirm writes resume once unlocked; (c) a simulated `ResourceMonitor` CRITICAL reading clears back to normal — confirm gated behavior (Sprint 4.6's `ActionResourceGate`, and Sprint 6.19's own resource-aware scheduling once that sprint lands) resumes normal operation, not a stuck-degraded state.
- A documented, generous pass/fail threshold for the stress scenario's own RSS-growth and hang-timeout bounds, matching Sprint 6.16's own established tolerance for real-machine variability.

## Dependencies

6.16, 6.17 (the audited job/thread inventory this sprint's stress scenario drives).

## Files to Create

- `tests/system/test_level6_part_b_stress.py`

## Files to Modify

None expected beyond test fixtures (`tests/system/conftest.py`, extended with a new accelerated-interval harness mirroring `fast_level5_part_b_app_harness`'s/`fast_level6_part_a_...`'s own precedent, if one doesn't already cover all 13 jobs at once).

## Expected Classes

None new.

## Expected Functions

None new in production code — this sprint is test infrastructure only.

## Data Flow

No new production data flow — this sprint exercises every existing flow simultaneously and under sustained load, a new *test* shape over unchanged production code.

## Implementation Tasks

1. `tests/system/conftest.py` — an accelerated-interval, all-jobs-active harness (extending, not duplicating, the existing `fast_*_harness` fixtures Sprints 4.19/5.24/5.25/6.13 each already established their own version of).
2. The sustained-load stress scenario per Objectives, with real, documented RSS/timeout bounds.
3. The three recovery scenarios per Objectives, each a real induced failure with a real, confirmed clean recovery.
4. Investigate any genuine gap the stress/recovery scenarios surface; fix if narrowly same-file, log to `backlog/technical_debt.md` if it would need cross-file wiring beyond this sprint's own "build and run the test" scope — the identical size-based judgment call every prior hardening/freeze sprint has already used.

## Architecture Notes

This sprint adds no new production resilience mechanism of its own — Sprint 6.19 is where a genuine gap this sprint's own scenarios surface gets a real fix (if it's a Fail-Gracefully-shaped gap) or a resource-aware scheduling mechanism (if it's a Resource-Protection-shaped one). This sprint's own job is narrowly to build the real test infrastructure and run it, disclosing what it finds.

## Integration Considerations

- Sprint 6.19 consumes this sprint's own recovery-scenario findings directly — any genuine resource-pressure-driven gap this sprint surfaces is that sprint's own scope to close.
- Sprint 6.23 (Full Test Suite Pass) extends this sprint's own bounded-duration stress scenario into the locked spec's own "Long-duration tests"/"Resource tests" Final Testing categories.

## Potential Risks

- **A real, sustained-load stress run may surface a genuine, previously-latent race or resource leak** — the whole point of this sprint, not treated as a surprise if it happens; sized and routed per Implementation Task 4's own judgment call.
- **Real recovery scenario (b) (a locked/unwritable SQLite file) is the hardest to induce safely and cleanly on Windows** — if a real, reliable induction technique isn't found, disclose the limitation explicitly rather than fabricate a weaker substitute test that doesn't actually prove recovery.

## Acceptance Criteria

- `test_level6_part_b_stress.py`'s sustained-load scenario passes against the real, complete system, with RSS growth and no hang within documented bounds.
- All three recovery scenarios pass, each proving a real return to normal operation after a real induced failure clears, without a restart.
- Any genuine gap found is either fixed (if narrowly scoped) or logged to `backlog/technical_debt.md` (if not).
- Full test suite (unit + integration + system, opt-in real-model marker excluded) passes.
- `ruff check .` clean.

## Testing Checklist

- [ ] Sustained-load stress scenario.
- [ ] Recovery scenario (a): Ollama unreachable → reachable.
- [ ] Recovery scenario (b): SQLite locked → unlocked.
- [ ] Recovery scenario (c): resource CRITICAL → normal.
- [ ] Full project suite re-run.

## Documentation Checklist

- [ ] `docs/STATUS.md` — narrative describing the stress/recovery scenarios and their outcomes.
- [ ] `docs/sprint_book/INDEX.md` — 6.18 row → `Complete` (once implemented).
- [ ] `docs/backlog/technical_debt.md` — any finding sized beyond this sprint's own scope.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

2.5–3.5 days.

## Risks

See Potential Risks above.

## Next Sprint

6.19 — Resource Protection & Fail-Gracefully Verification.

## Future Considerations

- A genuine multi-hour (or longer) endurance run is real future-shaped work this sprint's own accelerated-interval scenario deliberately substitutes for — would need a CI/scheduled-runner environment this project doesn't have (Sprint 6.23's own Future Considerations names the same gap).
