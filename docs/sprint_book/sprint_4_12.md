# Sprint 4.12 — Error Handling & Recovery Hardening

## Sprint ID

4.12

## Sprint Name

Error Handling & Recovery Hardening

## Purpose

Apply the Fail Gracefully Rule deliberately and exhaustively across the now-complete Level 4 Part A action/workflow surface, mirroring Sprint 2.13's role for Level 2 and Sprint 3.13's role for Level 3.

## Engineering Rationale

Level 4 Part A's failure surface is categorically different from, and in one specific way worse than, both prior levels': Level 2's failures degrade a conversation (annoying, never destructive); Level 3's failures degrade a decision's quality (Sprint 3.13's own "fail safe-down, never safe-up" standard). Level 4 Part A's failures can leave **real, external, partially-completed state** — a file half-moved, a process launched but untracked, a multi-step workflow stopped after step 3 of 7. A hardening pass here is not optional polish; it is where "recovering gracefully from failed actions" (this task's own Level 4 Goal) either becomes real or doesn't. Planned in advance as its own sprint, exactly like Sprints 2.13/3.13, rather than left to a retroactive review.

## Objectives

- Enumerate and close every realistic Level 4 Part A failure mode with a specific, tested recovery behavior — not generic `try/except: log` blocks.
- No failure anywhere in the Action Engine, Permission System, or Workflow Executor should ever leave `ActionRegistry.dispatch()`/`WorkflowExecutor.run()` in a state where the caller cannot tell what actually happened.
- Confirm that a failure in the audit/logging layer (Sprint 4.8) never blocks or corrupts the actual action's execution or its reported result to the user — logging must be a side effect of an action, never a precondition for it completing.

## Dependencies

4.11 (Workflow & Device Control Integration)

## Files to Create

None expected — this sprint hardens existing files rather than adding new ones, matching Sprint 2.13's/3.13's own precedent. (If a genuinely new shared concept emerges during implementation, document it here as a deviation before implementing, per `05_Claude_Development_Guide.md`'s Step 4 planning discipline.)

## Files to Modify

- `device_control/application_manager.py` — launch-hang detection (scenario a, below).
- `device_control/file_operations.py` — partial-operation isolation for multi-step OS calls (scenario b).
- `device_control/command_executor.py` — verified already correctly handles timeout (Sprint 4.5's own scope) — this sprint adds a regression test proving it under adversarial conditions, the same "verify under adversarial conditions rather than assume the earlier design holds" treatment Sprint 2.13 gave `ConversationSessionStore` (scenario c).
- `workflow/workflow_executor.py` — an internal exception mid-run (not just a step's own `ActionResult.FAILED`) is caught and resolved to an honest, partial `WorkflowRunResult` rather than propagating and losing all prior step results (scenario d).
- `security/confirmation_service.py` — `VoiceConfirmationService` failure when the underlying `VoiceSessionManager` itself is unavailable/erroring (scenario e).
- `device_control/action_log.py` — `ActionAuditLog.record()` write failure isolation: a failed audit write is logged and does not raise back into `ActionRegistry.dispatch()` (scenario f).
- `device_control/action_engine.py` — ensures a failure at any dispatch step (permission, resource gate, executor, audit) always ends in a well-formed `ActionResult`, never an unhandled exception escaping `dispatch()` itself.

## Expected Classes

None new by default, matching Sprint 2.13's/3.13's own precedent.

## Expected Interfaces

No changes to `ActionExecutor`/`ManagedModule` unless this sprint's implementation finds a specific, demonstrated gap — and if so, that gap and its proposed resolution must be presented as a plan before any interface change, per this task's own constraint against unilateral architecture changes.

## Expected Functions

No new public functions expected; existing functions across the Files to Modify list gain additional caught-exception paths and corresponding regression tests, in the same style as Sprint 2.13's/3.13's own hardening fixes.

## Data Flow

Not a new pipeline — this sprint adds recovery branches at existing Data Flow points from Sprints 4.1–4.11. Representative failure-path additions:

```
(a) ApplicationManager.launch() spawns a process that never becomes responsive (hung at OS level)
      → a bounded readiness check (not a blocking wait) marks the TrackedApplication launched-but-unconfirmed
      → ActionResult(SUCCEEDED, output=TrackedApplication(...)) still returned (the process DID launch — reporting
        FAILED would be dishonest) but with a clear status note; Sprint 4.8's audit record reflects this distinction

(b) FileOperationsManager.move() succeeds copying but fails deleting the source (a two-step OS operation under the hood)
      → detected via explicit post-copy verification before the delete step
      → on delete failure: ActionResult(FAILED, error_message="copied but could not remove original — manual cleanup
        may be needed"), never silently reported as a clean SUCCEEDED move with a leftover duplicate unexplained

(c) CommandExecutionEngine's subprocess exceeds command_timeout_seconds (Sprint 4.5's own designed behavior)
      → verified here under an adversarial, intentionally-hanging test command
      → CommandResult(timed_out=True, exit_code=None); the underlying process is confirmed terminated
        (Popen.kill()), not just abandoned as an orphaned process — a real gap Sprint 4.5's own spec did not
        explicitly require verifying, closed here

(d) WorkflowExecutor.run() raises internally partway through a multi-step run (a bug, not a step's own ActionResult.FAILED)
      → caught at the top of run()'s own loop
      → WorkflowRunResult returned with every already-completed step's real WorkflowStepResult intact,
        aborted_early=True, and a clear indication the abort was due to an executor-level fault, not a step
        being denied/failed normally — distinguishable in the result, not conflated

(e) VoiceConfirmationService.request_confirmation() called while VoiceSessionManager itself is erroring/unavailable
      → degrades to ConfirmationOutcome.TIMED_OUT immediately (per Sprint 4.7's own "timeout defaults to denial"
        rule) rather than raising or hanging — verified here under a real induced VoiceSessionManager failure,
        not just the "no active session" case Sprint 4.7 already tested

(f) ActionAuditLog.record() fails (SQLite write error — disk full/locked, the same real failure class Sprint 3.14
    found MemoryStore had never handled for its own SQLite operations)
      → caught inside record(), logged as a WARNING, ActionRegistry.dispatch() still returns the real
        ActionResult to the caller unchanged — an audit-logging failure never blocks or alters the actual
        action's outcome or the user-facing report of it
```

## Implementation Tasks

1. Work through scenarios (a)–(f) above, one at a time, each with: the fix, a regression test proving the failure is now handled, and a note in the owning sprint's own file (matching Sprint 2.2's "Post-Sprint Fix" precedent) if the fix belongs to a specific earlier sprint's file.
2. Confirm no failure path anywhere in `ActionRegistry.dispatch()`/`WorkflowExecutor.run()` can raise past their own boundary — an explicit code-level audit of every `try`/`except` in both, not just the six named scenarios.
3. Full regression run against the entire existing suite (Levels 1–4 Part A) to confirm zero unintended behavior changes outside the six scenarios.

## Architecture Notes

Every fix in this sprint is a **caught-exception path added to already-shipped Level 4 Part A code**, not a redesign — matching Sprint 2.13's/3.13's own explicit scope boundary ("this sprint hardens existing files rather than adding new ones"). If implementation discovers a fix that requires a real interface or architecture change, that is flagged as a plan for user review before proceeding, per this task's own explicit instruction not to modify approved architecture without flagging it separately.

Scenario (f)'s principle — **audit/logging must never gate or corrupt the primary operation it's observing** — generalizes a rule already implicit in `docs/CODING_STANDARDS.md`'s logging guidance but never previously tested under an induced logging-layer failure anywhere in this codebase; this sprint is the first to actually prove it holds for Level 4's specific audit-log shape.

## Integration Considerations

- These fixes apply within the already-integrated Sprint 4.11 object graph — no new wiring, only new caught-exception branches inside existing wired call paths.
- Sprint 4.13 (Integration Testing & Level Freeze) re-confirms all six scenarios at the system/integration level, the same two-tier verification (unit-level hardening here, system-level re-confirmation at freeze) Sprints 2.13→2.14 and 3.13→3.14 both used.

## Potential Risks

- **Scenario (a)'s "launched-but-unconfirmed" status is inherently ambiguous** — OS-level process readiness has no universal, reliable signal across arbitrary applications; this sprint's own bounded readiness check is a best-effort heuristic, not a guarantee, and must be documented as such rather than presented as definitive.
- **Scenario (b)'s partial-move detection adds real latency** (an explicit post-copy verification step before every delete) — an accepted, deliberate trade-off given the alternative (an undetected, silently duplicated or lost file) is far worse; not solved by skipping verification for speed.
- **Fixing scenario (d) changes `WorkflowExecutor.run()`'s own exception-handling shape** — care must be taken that this doesn't silently swallow a bug that should have been visible during Sprint 4.10's own testing; the added top-level catch is scoped as narrowly as possible (wrapping only the per-step dispatch call, not the entire method) to avoid masking unrelated implementation errors.

## Acceptance Criteria

- All six named scenarios (a–f) are demonstrated fixed via a dedicated regression test each, run against a real induced failure (not just a mocked exception where a real one is feasible to induce — matching Sprint 2.13's/3.13's own "real failure, not just a mock" standard where practical).
- No failure anywhere in `ActionRegistry.dispatch()` or `WorkflowExecutor.run()` propagates as an unhandled exception — verified by a dedicated adversarial test sweeping every internal call site with an injected failure.
- Zero regressions in the full existing test suite (Levels 1–4 Part A).

## Testing Checklist

- [ ] Regression: scenario (a) — hung/slow-starting process handling.
- [ ] Regression: scenario (b) — partial file-move detection and honest reporting.
- [ ] Regression: scenario (c) — command timeout under an adversarial hanging command, with confirmed process termination (no orphaned process left running).
- [ ] Regression: scenario (d) — `WorkflowExecutor` internal fault mid-run preserves prior step results.
- [ ] Regression: scenario (e) — `VoiceConfirmationService` degrades to `TIMED_OUT` under an induced `VoiceSessionManager` failure.
- [ ] Regression: scenario (f) — `ActionAuditLog.record()` write failure never blocks or alters the returned `ActionResult`.
- [ ] Full existing suite (Levels 1–4 Part A) passes with zero regressions.

## Documentation Checklist

- [ ] Each modified file's docstring updated with its new failure-handling behavior, in the same style as Sprint 2.13's/3.13's own hardening documentation.
- [ ] `docs/backlog/technical_debt.md` — any genuinely deferred edge case found but not fixed this sprint, recorded per the Technical Debt Policy (matching this project's consistent practice, e.g. items 9, 10, 12, 13 from Level 2's own hardening pass).
- [ ] `docs/STATUS.md` — Phase 4.1/4.2 rows note hardening complete.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

4.13 — Integration Testing & Level Freeze (Part A).

## Future Considerations

- Any scenario found during implementation that reveals a deeper design gap (rather than a straightforward caught-exception fix) is deferred to `docs/backlog/technical_debt.md`, not fixed under this sprint's own narrower hardening scope — matching Sprint 2.13's/3.13's own precedent for handling out-of-scope discoveries.

## Sprint Completion Report (2026-07-22)

Implemented as specified, authorized directly ("proceed with sprint 4.12") — same pattern as 4.2-4.11. No stop-and-ask gates; every fix stayed within this sprint's own explicit boundary ("a caught-exception path added to already-shipped code, not a redesign"). Investigated each scenario's current code before writing anything, mirroring Sprint 3.13's own discipline — one scenario (c) needed no production code change at all, matching the "already correctly handled, write the regression test" precedent Sprint 3.13 established for four of its own six scenarios.

**(a) `device_control/application_manager.py`** — `launch()` gained `_confirm_process_alive()`, a bounded (`DeviceControlConfig.application_launch_readiness_check_seconds`, default 0.5s), non-blocking-on-exit poll of `process.poll()`. `TrackedApplication` gained `readiness_confirmed: bool = True` (default preserves every pre-existing call site unmodified). `ActionStatus` is always still `SUCCEEDED` once `Popen()` itself succeeds — reporting `FAILED` would be dishonest, since the process genuinely did spawn; the distinction lives entirely in the new field. 4 new tests, both directions verified with a real process (a long-running `sys.executable` sleeper vs. one that exits via `-c "pass"`), not mocked.

**(b) `device_control/file_operations.py`** — `_handle_move()` rewritten from a single `shutil.move()` call into an explicit copy, a post-copy `destination.exists()` verification, then a separately-guarded delete of the original. A real, induced test (`source.chmod(0o444)`, which Windows genuinely refuses to delete) proves the destination copy survives intact and the caller gets a specific "copied but could not remove the original... manual cleanup may be needed" message naming both paths — never a generic failure hiding a silently-duplicated file.

**(c) `device_control/command_executor.py`** — no code change. `_run_subprocess()`'s use of `subprocess.run(timeout=...)` already guarantees `Popen.kill()` runs before `TimeoutExpired` re-raises, per CPython's own documented behavior — confirmed by reading the standard library's own source, not assumed. Sprint 4.5's own test suite verified `CommandResult.timed_out=True` was reported correctly but never verified the real OS process was actually gone afterward; closed with one new adversarial test — the hanging script writes its own real PID to a file before sleeping, and the test verifies via `psutil.pid_exists()` that it's genuinely terminated, independent of anything `CommandResult` itself reports.

**(d) `workflow/workflow_executor.py`** — three individually-narrow `try/except` guards added around `run()`'s own internal call sites (`workflow_store.get()`, the whole-workflow confirmation call inside `_maybe_request_whole_workflow_confirmation()`, and the per-step `action_registry.dispatch()` call) — deliberately three separate, narrow catches rather than one blanket wrapper around the whole method, per this sprint's own Potential Risk warning against masking unrelated bugs. Each degrades to an outcome already meaningful within `WorkflowRunResult`'s own existing shape (the same reportable abort already used for "not found"; `ConfirmationOutcome.TIMED_OUT`; a `FAILED` step result whose `error_message` explicitly names it an "internal executor fault," never conflated with a normal step failure/denial). 5 new tests, including one parametrized sweep test explicitly named after this sprint's own Acceptance Criteria wording.

**(e) `security/confirmation_service.py`** — `VoiceConfirmationService.request_confirmation()`'s speak-then-listen sequence is now wrapped; any unexpected failure (a `VoiceSessionManager` erroring mid-request, not just the already-tested "no active session" case) degrades to `ConfirmationOutcome.TIMED_OUT`, the same fail-safe-down value every other denial path already uses. 2 new tests using a locally-extended `_FakeSessionManager` (`raise_on_speak`/`raise_on_capture`), matching this test file's own established local-double convention.

**(f) `device_control/action_log.py` / `device_control/action_engine.py`** — `ActionAuditLog.record()`'s own `try/except` previously wrapped only the SQLite `INSERT`, not the `ActionAuditRecord` construction before it (`_build_parameters_summary()` included) — widened to guard the entire method body, genuinely fulfilling the docstring's own pre-existing "never raises" promise rather than partially implementing it. `record()`'s return type widened to `ActionAuditRecord | None` (safe: no production caller inspects the return value). `ActionRegistry.dispatch()` also gained its own outer guard around `self._audit_log.record(...)` — deliberate defense in depth on top of `record()`'s own now-complete guarding, matching this class's established "an outer catch for anything a narrower one doesn't already cover" discipline. `_build_parameters_summary()` additionally surfaces scenario (a)'s new `readiness_confirmed` field in the audit trail. 5 new tests: a real closed-SQLite-connection failure, a real `__str__`-raising parameter value, and a `dispatch()`-level test proving a raising audit log never affects the real returned `ActionResult`.

**Exhaustive sweep (Implementation Task 2 / Acceptance Criteria)**: one parametrized test each for `ActionRegistry.dispatch()` and `WorkflowExecutor.run()`, each case forcing exactly one internal collaborator to raise (`permission_gate`/`resource_gate`/`audit_log` for the former; `workflow_store`/`confirmation_service`/`action_registry` for the latter), confirming every case degrades gracefully rather than propagating — directly naming the Acceptance Criteria's own wording in both tests' docstrings.

**Two real, additional findings from this sprint's own exhaustive audit, both logged rather than silently fixed or expanded into**: `backlog/technical_debt.md` item 27 (`WorkflowStore` itself — `save()`/`list_all()`/`delete()`/`set_enabled()` — still has no Fail Gracefully wrapping of its own; this sprint's actual Files to Modify never named `workflow_store.py` directly, so the fix landed one layer up, at `WorkflowExecutor`'s own single call site to `get()`, closing what this sprint's own Acceptance Criteria actually required without expanding into a file outside its own stated scope) and item 28 (`ApplicationManager.execute()`'s `except (OSError, psutil.Error)` doesn't catch `pywintypes.error` — confirmed via `pywintypes.error.__mro__` that it isn't an `OSError` subclass, found while cross-checking `window_manager.py`'s own docstring, which explicitly names this same type for the identical reason; not a live safety gap, since `ActionRegistry._dispatch_once()`'s own pre-existing blanket `except Exception` around `executor.execute()` already catches it, satisfying this sprint's own Acceptance Criteria one layer up).

**A real, unrelated test-fragility bug found and fixed while running the full regression suite, as a Post-Sprint Fix on Sprint 4.11's own two integration/system harnesses**: `tests/integration/conftest.py`'s `pipeline_harness` and `tests/system/conftest.py`'s `app_harness` both left `DeviceControlConfig.resource_gate_action_types` at its real default (`["launch_application", "system_command"]`), meaning `ActionResourceGate` sampled the *actual* host machine's real CPU/RAM via `ResourceMonitor` for any dispatched `launch_application` — a genuine, non-deterministic environmental dependency neither harness's own docstring ever intended, unlike every other collaborator in them (deliberately faked at the hardware/model boundary specifically to avoid this). Concretely reproduced, not theorized: this development machine's own real RAM usage was genuinely at 90-96% during this sprint's full-suite run, causing `test_full_wake_to_device_control_round_trip` (Sprint 4.11) to fail exactly as `ActionResourceGate` is designed to behave under real critical resource pressure — confirmed by checking `psutil.virtual_memory()` directly rather than assuming a flake. Fixed by setting `resource_gate_action_types=[]` in both harnesses (resource-gate-blocking behavior itself is already covered by `tests/unit/device_control/test_resource_gate.py`'s own dedicated, deterministic suite — neither harness needs to exercise it for real).

904/904 full-suite tests passing (one pre-existing, timing-sensitive `test_full_level3_acceptance_scripted_conversation` flake under full-suite system load — the same known flake class as every prior Level 4 sprint, unrelated to this sprint's own changes, confirmed passing standalone), `ruff check .` clean. `docs/STATUS.md` updated (a new Sprint 4.12 paragraph after the Level 4 Part A phase table, mirroring Sprint 2.13/3.13's own style). **Sprint 4.13 (Integration Testing & Level Freeze, Part A) is next — the last sprint before Level 4 Part A itself formally freezes.**
