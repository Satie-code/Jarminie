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

- [x] `TaskScheduler` resource-sensitive skip-on-CRITICAL, real induced reading.
- [x] Non-sensitive job continues normally during the same CRITICAL window.
- [x] Item 33 regression test.
- [x] Item 39 regression test.
- [x] System-level `ResourceMonitor`/`ActionResourceGate` re-confirmation (relies on Sprint 6.18's own already-passing `test_recovery_resource_critical_then_normal`, not a duplicate).
- [x] Full project suite re-run.

## Documentation Checklist

- [x] `docs/STATUS.md` — narrative describing the resource-awareness mechanism and both Fail-Gracefully fixes.
- [x] `docs/sprint_book/INDEX.md` — 6.19 row → `Complete`; the Recommendations section's own Sprint-4.6-era entry marked resolved.
- [x] `docs/backlog/technical_debt.md` — items 33/39/53 marked resolved (53 folded into this sprint's own scope per an explicit `AskUserQuestion` decision — see Sprint Completion Report below); the mid-sprint `resource_aware_scheduler` design correction logged as part of item 53's own resolution notes.

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

## Sprint Completion Report (2026-08-16)

Implemented as specified, continued from a prior session's own "continue with sprint 6.19." One real, up-front scope question was resolved via `AskUserQuestion` before implementation began: Sprint 6.18's own Integration Considerations had promised this sprint would close "any genuine resource-pressure-driven gap" its own recovery scenarios surfaced, but this sprint's own literal spec (written 2026-08-12, before `backlog/technical_debt.md` item 53 existed) never named it. The user chose to fold item 53 into this sprint's own scope rather than defer it further.

**Objective 1 (TaskScheduler resource-awareness) — implemented.** `scheduler/task_scheduler.py`'s `TaskScheduler` gained an optional, keyword-only `resource_monitor` constructor collaborator and `add_job()` a new `resource_sensitive: bool = False` parameter; when both are present, a flagged job is wrapped so a real `ResourceMonitor.critical_alerts()` reading (CRITICAL severity, the same check `ActionResourceGate` already uses, not the lower warning-level `breached_resources()`) skips that single tick, logged once. `main.py`'s `_construct_level4_part_b_modules()` threads `resource_monitor` straight into `TaskScheduler`'s own construction.

**Objective 2 (job classification) — implemented, exactly matching this sprint's own named list.** Six job_ids marked `resource_sensitive=True`: `memory_lifecycle_cleanup_pass`/`memory_lifecycle_monthly_review` (`voice/pipeline.py`), `pattern_detection_pass`/`recommendation_generation` (`voice/pipeline.py`), `usage_tracker_sample` (`analytics/usage_tracker.py`), `wellness_tracker_idle_check` (`wellness/wellness_tracker.py` — disambiguated directly from the differently-named, real-user-facing `wellness_prompt_enqueue` job by reading `_on_tick()`'s own body: purely internal accumulator bookkeeping, no external side effect). The other 7 jobs (`conversation_store_purge`, `action_audit_log_purge`, `proactive_priority_item_announcement`, `wellness_prompt_enqueue`, `runtime_housekeeping`, `ReminderEngine`'s poll, `ProactiveAssistant`'s own tick) were deliberately left unmarked — not named in this sprint's own Objectives text, each individually a real user-facing-lateness-cost case, or (for `runtime_housekeeping`) the resource-pressure relief mechanism itself.

**Objectives 3/4 (items 33/39) — both fixed exactly as each item's own note already anticipated.** `decision/llm_client.py`'s `OllamaClient.generate()` now accesses `response.response` inside its own `try` block; `voice/pipeline.py`'s `_update_workspace_profile()` now resets its own bookkeeping before, not after, `JarvisRenderer.apply_workspace_profile()`. One new regression test each (`test_llm_client.py`, `test_pipeline.py`).

**Item 53 (folded in per the user's own decision) — fixed via the second of that item's own three named options.** `MemoryLifecycleManager` gained an optional `runtime_manager` collaborator; `run_cleanup_pass()`/`run_monthly_review()`/`apply_user_override()` each call `ensure_started("memory_store")` first — the third real call path (`apply_user_override()`, a live per-turn call from `CommunicationPipeline._handle_turn_complete()`) that item's own original finding hadn't named, found while reading the class fully rather than assumed from the backlog text alone. `health_check()`'s own need for `MemoryStore`'s real, non-Protocol method is why the first option (threading `LazyMemoryStore` itself through) was not taken. Two now-stale docstrings (`main.py`'s `_construct_level3_modules()`, `LazyMemoryStore`'s own in `memory/memory_store.py`) carrying the original, now-corrected Runtime-Phase-6-era "not a correctness need" reasoning were both updated to point at this resolution. `test_sustained_load_all_jobs_active_no_hang_no_crash_bounded_rss` (Sprint 6.18) now passes for the first time.

**A real, mid-sprint design correction, caught before it could land as a false regression in this file's own narrative.** An early version of the `resource_monitor` wiring threaded it into every `tests/system/`/`tests/integration/` harness's own `TaskScheduler` unconditionally, mirroring `main.py`'s real production wiring exactly. Running the broader regression suite surfaced two failures with a distinctive shape (`test_level4_part_b_full_acceptance_scenario`: `{'cleanup_pass': 1, 'monthly_review': 1, 'conversation_purge': 93, 'audit_purge': 93}`; `test_all_four_level5_part_b_jobs_genuinely_recur`: all four resource-sensitive jobs stuck at 0) — real, transient host CPU/RAM pressure during the test run legitimately triggering the new skip mechanism inside tests that assert unconditional recurrence and have nothing to do with resource protection. Root-caused, not guessed: reverted the global wiring, gave `_app_harness_impl()` (both conftest.py files) a new `resource_aware_scheduler: bool = False` parameter, and made only the one new harness that exists specifically to exercise this mechanism (`fast_resource_protection_app_harness`) opt in. `stress_app_harness` (Sprint 6.18) was deliberately left at the default (unwired) to avoid re-opening that sprint's own already-verified, already-documented behavior. Re-run confirmed both previously-broken tests pass again.

**System-level proof (Implementation Task 5).** New `tests/system/test_level6_part_b_resource_protection.py` (2 tests) with a new dedicated `fast_resource_protection_app_harness` fixture — deliberately not `stress_app_harness`, to avoid `backlog/technical_debt.md` item 53's own disclosed cross-test contamination risk and because this mechanism needs only two jobs accelerated plus a monkeypatched `ResourceMonitor.sample()`, not real sustained load. Both tests initially failed for a real, findable reason (not a mechanism bug): `UsageTracker._on_tick`/`ReminderEngine._poll_due_items` are captured as bound methods the instant `TaskScheduler.add_job()` runs during harness setup, so instance-level monkeypatching after the harness is handed back never took effect — fixed by patching at the class level before the harness fixture is requested (`job_tick_counts` fixture, mirroring `tests/integration/test_scheduler_integration.py`'s own established `maintenance_call_counts` pattern exactly), listed before the harness fixture in each test's own parameter list. A second, narrower fix was needed once that landed: fixture setup itself (real model loading, 50-90s+ on this machine) already exceeds the harness's own 0.3s job interval many times over, so both jobs had already ticked before the test body ever ran — fixed by resetting the tick counts immediately after patching `resource_monitor.sample()` to CRITICAL, not before the test body starts. Both tests then passed reliably.

**Adversarial re-read (Implementation Task 6)** of `core/resource_monitor.py`, `device_control/resource_gate.py`, and every job-registration call site touched by this sprint found no further genuine gap sized for a fix or a new backlog item — one minor, low-severity observation only (each `resource_sensitive` job's own `critical_alerts()` check logs independently on every tick during a sustained CRITICAL period; not a new problem, mirrors `ActionResourceGate`'s own already-accepted identical per-check logging shape).

Full regression suite, run per-tier per Sprint 6.17's own established isolation precedent: `tests/unit/` 2260 passed + 1 skipped (12 new tests, zero regressions from the 2248+1 baseline); `tests/integration/` 75 passed, fully clean; `tests/system/` (excluding `test_level6_part_b_stress.py`, separately verified) clean apart from the already-long-documented `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` Ollama-nondeterminism flake. `ruff check .` clean repo-wide. No git commit made — sits uncommitted alongside all of 6.1-6.18's own backlog.
