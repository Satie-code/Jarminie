# Sprint 6.19 — Resource Protection & Fail-Gracefully Verification

## Sprint ID

6.19

## Sprint Name

Resource Protection & Fail-Gracefully Verification

## Purpose

Close Phase 6.2's own second task pair, "Resource Protection verification. Fail Gracefully verification," including a real, named debt this Sprint Book's own INDEX.md has carried since Sprint 4.6: *"Sprint 4.6 (System Monitoring & Resource Protection, Action-Aware) deliberately narrowed the original roadmap's '(full)' scope to Action Engine dispatch-gating only... Level 6['s Resource Protection sprint] should treat closing that specific gap as part of its own scope, not assume Sprint 4.6 already delivered it in full"* (INDEX.md Recommendations, 2026-07-20). This sprint is that closing.

## Engineering Rationale

Two real, distinct gaps this sprint closes, both already known rather than newly discovered: **(1) Resource Protection's own cross-cutting half was never built.** `device_control/resource_gate.py`'s `ActionResourceGate` (Sprint 4.6/4.11) only gates `ActionRegistry.dispatch()` — the 13 recurring `TaskScheduler` jobs and 8 raw threads Sprint 6.17 inventoried have no resource-pressure awareness of their own at all, directly contradicting Part 2's own "If thresholds are exceeded, background work is reduced before the system becomes unresponsive" Resource Protection rule for every mechanism except Action dispatch. **(2) Two real, already-disclosed Fail Gracefully gaps remain open, deliberately deferred at their own discovery time as outside a narrowly-scoped sprint's own Files to Modify**: `backlog/technical_debt.md` item 33 (`decision/llm_client.py`'s `OllamaClient.generate()` accesses `response.response` immediately AFTER its own try/except block, the identical shape of gap item 32 already fixed for `BraveSearchProvider`) and item 39 (`voice/pipeline.py`'s `_update_workspace_profile()` resets its own bookkeeping AFTER calling `apply_workspace_profile()`, so a synchronous raise leaves stale state). Both were explicitly deferred pending a sprint whose own scope is genuinely cross-cutting Fail Gracefully verification rather than a single Level's own narrowly-bounded hardening pass — this is that sprint.

## Objectives

- Give `TaskScheduler` an optional `resource_monitor: ResourceMonitor | None = None` constructor collaborator (the same "optional, degrades to prior unthrottled behavior when absent" pattern every other cross-cutting collaborator in this codebase already uses) — when supplied, a job whose own config marks it `resource_sensitive=True` is skipped for that tick (not removed, not delayed to a specific later time — simply not run this cycle, cheapest and safest) whenever `resource_monitor.sample()` reports CRITICAL, logged once per skipped tick.
- Mark the correct subset of Sprint 6.17's own 13-job inventory `resource_sensitive=True` — the genuinely deferrable ones (pattern detection, recommendation generation, usage sampling, wellness idle-check, memory lifecycle passes) — never the ones whose own lateness has real user-facing cost (`ReminderEngine`'s poll, `_check_and_announce_priority_item`), matching Part 2's own "reduce work before the system becomes unresponsive," not "silence the user."
- Fix `backlog/technical_debt.md` item 33: move `response.response` access inside `OllamaClient.generate()`'s own existing try/except.
- Fix `backlog/technical_debt.md` item 39: reorder `_update_workspace_profile()`'s bookkeeping resets to before the `apply_workspace_profile()` call.
- Re-confirm `ResourceMonitor` (Sprint 1.4) and `ActionResourceGate` (Sprint 4.6) still degrade honestly at the system level, against the real, complete Level 1–6 Part A graph, not merely their own original component-level tests.

## Dependencies

1.4 (`ResourceMonitor`), 4.6 (`ActionResourceGate`), 6.17 (the job inventory this sprint's resource-awareness wiring targets), 6.18 (real induced-CRITICAL recovery scenario (c) is this sprint's own direct proof point).

## Files to Create

None expected.

## Files to Modify

- `scheduler/task_scheduler.py` (optional `resource_monitor` collaborator, `resource_sensitive` job flag)
- `voice/pipeline.py` (marks the correct job subset `resource_sensitive=True`; the `_update_workspace_profile()` reorder)
- `decision/llm_client.py` (item 33 fix)
- `main.py` (threads `resource_monitor` into `TaskScheduler` construction)

## Expected Classes

None new.

## Expected Functions

None new — `TaskScheduler.add_job()` gains one new optional keyword argument (`resource_sensitive: bool = False`); no new methods.

## Data Flow

`ResourceMonitor.sample()` → (new) `TaskScheduler`'s own pre-tick CRITICAL check → skip-this-tick for any `resource_sensitive=True` job, unchanged execution for every other job. No other flow changes.

## Implementation Tasks

1. `TaskScheduler.add_job(..., resource_sensitive: bool = False)` and the optional `resource_monitor` constructor collaborator; a pre-tick CRITICAL check that skips (never removes) a flagged job's own single tick.
2. Classify each of Sprint 6.17's own 13 jobs `resource_sensitive=True`/`False` per Objectives, threaded through `main.py`'s/`voice/pipeline.py`'s own job-registration call sites.
3. `decision/llm_client.py` — item 33 fix, with a regression test confirming `generate()` degrades to `LlmError` (not a raw `AttributeError`) on a malformed/`None`-shaped response, mirroring `test_brave_search_provider.py`'s own item-32 regression test shape exactly.
4. `voice/pipeline.py` — item 39 fix, with a regression test confirming `_current_workspace_profile` stays consistent even when `apply_workspace_profile()` raises synchronously.
5. System-level re-confirmation: a real induced CRITICAL reading (reusing Sprint 6.18's own recovery scenario (c) infrastructure) proves a `resource_sensitive=True` job genuinely skips its tick, while a non-sensitive job (e.g. `ReminderEngine`'s poll) keeps running normally throughout.
6. Adversarial re-read of `core/resource_monitor.py`, `device_control/resource_gate.py`, and every job-registration call site touched by this sprint, per this project's own established "hardening sprint finds at least one more thing" pattern — any further genuine gap found gets fixed here (if narrowly scoped) or logged (if not).

## Architecture Notes

Resource-awareness is opt-in per job (`resource_sensitive`), not a blanket throttle — matching Part 2's own explicit "background work is reduced," not "background work stops," and preserving every job whose own lateness has real user-facing cost. `TaskScheduler` itself stays the one shared scheduling mechanism (Sprint 6.17's own Architecture Notes); this sprint extends it, it does not introduce a second, parallel resource-aware scheduler.

## Integration Considerations

- Sprint 6.23 (Full Test Suite Pass) re-confirms this sprint's own resource-awareness mechanism as part of its own closing system acceptance pass, the same "system-level re-confirmation" every prior freeze sprint has given its own immediately-preceding hardening sprint's work.

## Potential Risks

- **Classifying a job `resource_sensitive=True` that turns out to have real user-facing lateness cost** would be a genuine regression disguised as a resource-protection improvement — each classification is justified individually in this sprint's own eventual completion report, not applied as a blanket default.
- **The adversarial re-read (Implementation Task 6) may surface a further genuine gap sized beyond this sprint's own scope** — logged to `backlog/technical_debt.md` rather than force-fit, per this project's own established precedent.

## Acceptance Criteria

- A real induced CRITICAL `ResourceMonitor` reading causes every `resource_sensitive=True` job to skip its own next tick, while every other job continues normally — proven by a real system-level test, not merely unit-level.
- `backlog/technical_debt.md` items 33 and 39 are both closed with real regression tests.
- `ResourceMonitor`/`ActionResourceGate` are re-confirmed correct at the system level.
- Full test suite (unit + integration + system, opt-in real-model marker excluded) passes with zero regressions to any healthy-path behavior.
- `ruff check .` clean.

## Testing Checklist

- [ ] `TaskScheduler` resource-sensitive skip-on-CRITICAL, real induced reading.
- [ ] Non-sensitive job continues normally during the same CRITICAL window.
- [ ] Item 33 regression test.
- [ ] Item 39 regression test.
- [ ] System-level `ResourceMonitor`/`ActionResourceGate` re-confirmation.
- [ ] Full project suite re-run.

## Documentation Checklist

- [ ] `docs/STATUS.md` — narrative describing the resource-awareness mechanism and both Fail-Gracefully fixes.
- [ ] `docs/sprint_book/INDEX.md` — 6.19 row → `Complete` (once implemented); the Recommendations section's own Sprint-4.6-era entry marked resolved.
- [ ] `docs/backlog/technical_debt.md` — items 33/39 marked resolved; any further adversarial-re-read finding logged.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

6.20 — Permission & Encryption Audit.

## Future Considerations

- A per-job resource-cost *estimate* (rather than a flat sensitive/not-sensitive classification) is real future-shaped refinement, not built speculatively here — the binary classification is Part 2's own literal "reduced," which this sprint delivers honestly without over-engineering a cost model no real data yet justifies.
