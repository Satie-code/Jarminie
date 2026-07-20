# Sprint 4.2 — Application Manager

## Sprint ID

4.2

## Sprint Name

Application Manager

## Purpose

Implement the first real `ActionExecutor` (Sprint 4.1): launching, listing, focusing, and closing desktop applications. This is Part 2's Device Control Engine "Applications" control surface and Part 4 Phase 4.1's "Application control" task.

## Engineering Rationale

Corresponds to `docs/sprint_book/INDEX.md`'s original `4.1 Application Control` roadmap entry, renamed to `Application Manager` to match this task's own terminology and to avoid the word "Control" appearing in three different sprint names (Application, File, Window) with no consistent noun — `Manager`/`Operations`/`Management` are used instead, matching this project's existing naming style (`MicrophoneManager`, `ConversationSessionStore`, `MemoryLifecycleManager`). No functional scope changes from the original roadmap entry.

Deliberately the **first** concrete executor built (not File Operations or Window Management) because it is the lowest-risk, most reversible of the three: launching an application has no destructive failure mode (worst case, nothing opens), unlike File Operations (data loss) or a mis-issued Window operation (a lost/off-screen window). Building the least risky executor first lets `ActionRegistry`/`PermissionGate` (4.1) get their first real exercise against a real, if low-stakes, executor before Sprint 4.3 raises the stakes — an ordering choice, not named by any prior spec, made here because it's a deliberately safer implementation sequence.

## Objectives

- `ApplicationManager` (`ActionExecutor`): launch an application by path/name, list currently-running managed-launch applications, focus one, close one.
- Real Windows process launch/enumeration via `psutil` (already a dependency since Sprint 1.4) and `pywin32` (declared in `requirements.txt` for Phase 4.1, installed this sprint).
- Every launched process is tracked so "close" and "focus" can target something this session actually started, not an arbitrary system process by guessed PID.

## Dependencies

4.1 (Action Engine Foundation)

## Files to Create

- `device_control/application_manager.py` — `ApplicationManager`, `TrackedApplication` (dataclass).
- `tests/unit/device_control/test_application_manager.py`

## Files to Modify

- `config/schema.py` — `DeviceControlConfig` gains `application_allowlist: list[str] | None` (default `None` = no allowlist restriction at this sprint; Sprint 4.7 is what makes an allowlist a real enforced policy) and `max_tracked_applications: int` (default `50`, a defensive bound matching `PriorityQueueManager`'s `_MAX_SANE_QUEUE_DEPTH` convention).
- `config/defaults.yaml` — matching `device_control:` fields.
- `requirements.txt` — move `pywin32` from "declared, not yet installed" to actually installed in this sprint's venv (mirrors `backlog/technical_debt.md` item 1's per-phase install-order policy).

## Expected Classes

- `TrackedApplication` (dataclass) — `process_id: int`, `executable_path: str`, `launched_at: datetime`, `launched_via: str` (the `ActionContext.requested_by` value that launched it, for audit — Sprint 4.8 consumes this).
- `ApplicationManager(ActionExecutor)` — constructor DI: `(device_control_config: DeviceControlConfig)`. Implements `ActionExecutor.can_handle()` for `LAUNCH_APPLICATION`/`CLOSE_APPLICATION`; internally routes `LIST`/`FOCUS` as sub-operations of the same two action types via `ActionRequest.parameters` (no new `ActionType` values needed — listing/focusing are read/low-risk variants of the same "application" concern, not distinct enough to warrant separate enum members per this sprint's own judgment).

## Expected Interfaces

None new — implements `device_control.action_engine.ActionExecutor` (4.1).

## Expected Functions

- `ApplicationManager.can_handle(action_type: ActionType) -> bool`
- `ApplicationManager.execute(request: ActionRequest) -> ActionResult` — dispatches internally on `request.parameters["operation"]` (`"launch"`, `"close"`, `"focus"`, `"list"`); catches every `OSError`/`psutil.Error` and returns `ActionStatus.FAILED` with `error_message`, never raises past this boundary (Fail Gracefully).
- `ApplicationManager.launch(executable_path: str, requested_by: str) -> TrackedApplication` — internal; `subprocess.Popen`-based launch, records a `TrackedApplication`.
- `ApplicationManager.close(process_id: int) -> bool` — internal; only closes a `process_id` present in this manager's own tracked set (never an arbitrary system PID — a real safety boundary, not just a convenience default).
- `ApplicationManager.list_tracked() -> list[TrackedApplication]`
- `ApplicationManager.focus(process_id: int) -> bool` — `pywin32`-based window-activation call against the tracked process's main window.

## Data Flow

```
ActionRegistry.dispatch(ActionRequest(action_type=LAUNCH_APPLICATION, parameters={"executable_path": ..., "operation": "launch"}))
      ↓
PermissionGate.check() → ALLOW (Sprint 4.1 default; Sprint 4.7 makes this real)
      ↓
ApplicationManager.execute()
      ↓
subprocess.Popen / psutil enumeration / pywin32 focus call
      ↓
TrackedApplication recorded (launch) or looked up (close/focus/list)
      ↓
ActionResult(status, output=TrackedApplication | list[TrackedApplication] | None)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `DeviceControlConfig` additions.
2. `device_control/application_manager.py` — `TrackedApplication`, `ApplicationManager`.
3. `requirements.txt`/venv — install `pywin32`.
4. Unit tests: launch (via a real, harmless executable — see Potential Risks), close, focus, list, close-of-untracked-PID rejection, launch failure (bad path) degrading to `FAILED` not an exception.

## Architecture Notes

`ApplicationManager` never closes or focuses a process it did not itself launch and track — this is a deliberate, structural safety boundary (not merely a default), matching the same "default-deny, whitelist-gated" discipline `AuthorityEvaluator` (3.11) already established for emergency procedures. A future sprint could add "close any running application by name," but that is a materially higher-risk capability requiring its own explicit Permission & Confirmation System (4.7) review, not something to fold in here quietly.

`ApplicationManager` does not itself decide *whether* an application launch is permitted — that remains `PermissionGate`'s job (4.1, formalized 4.7). This keeps Single Responsibility intact: `ApplicationManager` only knows how to launch/track/close/focus, never why it was or wasn't allowed to.

## Integration Considerations

- Registered with `ActionRegistry` for real by Sprint 4.11 (`main.py` construction) — not self-registering, matching `ManagedModule`'s own "the composition root registers, subsystems don't register themselves" convention (`main.py`'s own docstring, Sprint 1.5).
- Sprint 4.6 (System Monitoring, Action-Aware) will add a resource-pressure check that `ApplicationManager.launch()` consults before proceeding — not built in this sprint, since Sprint 4.6 doesn't exist yet at this point in the build order; `execute()` is written so that check slots in as one additional guard, not a restructure.
- Sprint 4.7's application allowlist enforcement reads `DeviceControlConfig.application_allowlist` — the field exists from this sprint onward but is unenforced until then (same "field present, policy arrives later" pattern as `AuthorityEvaluator.approved_emergency_procedures`).

## Potential Risks

- **Real process launch in tests is inherently more consequential than any prior sprint's tests** (Sprints 1.1–3.14 never launched real OS processes). Tests must launch something genuinely harmless and universally present on the target platform (e.g. `notepad.exe` or a small bundled no-op script under `scripts/`) and must reliably close it in teardown even on assertion failure — a real, new testing-infrastructure requirement, not a hypothetical.
- **`pywin32`'s window-focus API is Windows-only**, consistent with the project's `sys_platform == "win32"` requirement pin — this sprint has no cross-platform fallback path and none is required (Part 1: "Windows laptops" is the only V1 target).
- **A launched application that never actually starts a visible window** (a background/CLI tool) makes `focus()` meaningless for it — `focus()` degrades to `ActionStatus.FAILED` with a clear message in that case, not a crash or a silent no-op.

## Acceptance Criteria

- Launching a real, known-safe executable succeeds and returns a `TrackedApplication` with a real `process_id`.
- Launching a nonexistent path degrades to `ActionStatus.FAILED`, never raises past `execute()`.
- Closing a tracked process succeeds and removes it from `list_tracked()`.
- Closing an untracked/arbitrary PID is rejected (`ActionStatus.DENIED` or `FAILED` with a clear message — not silently attempted).
- `list_tracked()` accurately reflects launch/close state across a launch → list → close → list sequence.
- Matches Part 4 Phase 4.1's Master Plan acceptance language for this slice: "Safe desktop control."

## Testing Checklist

- [ ] Unit: launch succeeds, returns correct `TrackedApplication`.
- [ ] Unit: launch of a bad path degrades to `FAILED`.
- [ ] Unit: close of a tracked process succeeds; process no longer in `list_tracked()`.
- [ ] Unit: close of an untracked PID is rejected.
- [ ] Unit: `focus()` on a tracked process succeeds (or degrades cleanly on a headless/CI environment without a real window — a real CI-environment caveat to resolve during implementation, matching Sprint 2.1's "no physical mic in CI" precedent).
- [ ] Unit: `max_tracked_applications` bound enforced (further launches rejected past the cap, not silently unbounded growth).

## Documentation Checklist

- [ ] `device_control/application_manager.py` docstring: the "only ever acts on what it itself tracked" safety boundary, stated explicitly.
- [ ] `docs/STATUS.md` — Phase 4.1 row notes Application Manager complete.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

4.3 — File & Folder Operations.

## Future Considerations

- Closing/focusing an untracked (externally launched) application by name/title, if a real user need emerges — a materially higher-risk capability deferred until Permission & Confirmation (4.7) exists to gate it properly, not built speculatively now.
- CPU/RAM usage per tracked application (feeds Level 5's Analytics/Usage Tracking, Sprint 5.6) — out of this sprint's scope, noted for that future sprint's own Dependencies list.

---

## Sprint Completion Report (2026-07-20)

### Summary

Implemented `device_control/application_manager.py` (`TrackedApplication`, `ApplicationManager`) as Level 4's first real `ActionExecutor`, per this file's own spec, plus `application_allowlist`/`max_tracked_applications` on `DeviceControlConfig` and real `pywin32` installation. 89/89 targeted tests passing; full-suite run showed 665/666 (one pre-existing, unrelated system-level timing flake — see Remaining Risks), `ruff check .` clean.

### Files Created

- `device_control/application_manager.py` — `TrackedApplication`, `ApplicationManager`.
- `tests/unit/device_control/test_application_manager.py` — 22 tests.

### Files Modified

- `config/schema.py` — `DeviceControlConfig.application_allowlist: list[str] | None = None`, `max_tracked_applications: int = 50`; `AppConfig._validate_device_control()` added (first real validation for this section — positivity check on the cap, no-blank-entries check on the allowlist).
- `config/defaults.yaml` — `device_control:` section gains both real fields.
- `requirements.txt` — no change needed; `pywin32>=306; sys_platform == "win32"` was already declared (Sprint 1.1's bootstrap). Actually installed into this sprint's venv (`pywin32==312`).
- `docs/backlog/technical_debt.md` — item 1 updated: `pywin32` moved from "Remaining" to "Done so far."
- `tests/unit/config/test_schema.py` — 3 new tests for the new `_validate_device_control()` checks.
- `docs/STATUS.md` — Phase 4.1 row updated with this sprint's completion.

### Tests Added

25 total. In `test_application_manager.py` (22): `can_handle()` correctness; real launch (via a `sys.executable` + `time.sleep()` child process, not a GUI app — see Engineering Decisions) tracks a real `TrackedApplication`; a bad launch path raises `OSError` directly and degrades to `FAILED` through `execute()`; missing-parameter validation for every operation (`launch`/`close`/`focus`); `max_tracked_applications` cap enforcement; `close()` of a tracked process actually terminates it; `close()` of an untracked PID is refused (`False` directly, `DENIED` through `execute()`); `close()` of a process that already exited on its own is still treated as a successful close (a real scenario found during implementation, not hypothetical); `list_tracked()` reflects launch/close state; `focus()` of an untracked process is refused; `focus()` of a tracked but windowless process returns `False` (a real, verified-in-this-environment case); `focus()` of a tracked process with a window found calls `SetForegroundWindow` (verified via mocking `_find_window_for_process`, not a real window — see Engineering Decisions); unknown/missing `operation` degrades to `FAILED`. In `test_schema.py` (3): `max_tracked_applications` positivity, `application_allowlist=None` validity, blank-entry rejection.

### Documentation Updated

This file (Sprint Completion Report). `device_control/application_manager.py`'s module/class docstrings and its test file's own module docstring (documenting the notepad.exe finding in detail, so it isn't rediscovered). `config/schema.py`'s `DeviceControlConfig` docstring updated to reflect the two new fields are real-but-unenforced. `docs/backlog/technical_debt.md` item 1. `docs/STATUS.md` Phase 4.1 row. `docs/sprint_book/INDEX.md` (this sprint's row marked Complete).

### Acceptance Criteria Checklist

- ✔ Launching a real, known-safe executable succeeds and returns a `TrackedApplication` with a real `process_id`.
- ✔ Launching a nonexistent path degrades to `ActionStatus.FAILED`, never raises past `execute()` (raises directly from the public `launch()`, as documented — a deliberate distinction from the `execute()` boundary, not an oversight).
- ✔ Closing a tracked process succeeds and removes it from `list_tracked()`.
- ✔ Closing an untracked/arbitrary PID is rejected (`DENIED` via `execute()`, `False` via direct `close()` — not silently attempted).
- ✔ `list_tracked()` accurately reflects launch/close state across a launch → list → close → list sequence.
- ✔ Matches Part 4 Phase 4.1's "Safe desktop control."

### Engineering Decisions

- **Real GUI-app testing pivoted from `notepad.exe` to a `sys.executable` + `time.sleep()` child process.** Empirically verified during implementation (not assumed): on this Windows 11 environment, `subprocess.Popen(["notepad.exe"])` spawns a process whose own PID exits almost immediately — Windows 11 redirects the classic `notepad.exe` invocation through a packaged-app host, so the PID `Popen` hands back is not the long-lived process. `win32gui.EnumWindows` found no window for that PID, and `psutil.Process(pid)` raised `NoSuchProcess` within ~1.5s. A `sys.executable -c "import time; time.sleep(N)"` child needs no console/desktop station to stay alive and behaves deterministically, so it replaced notepad.exe as this sprint's own real-launch test target for `launch()`/`close()`/`list_tracked()`. Documented in the test file's own module docstring so this doesn't need rediscovering.
- **`ApplicationManager.launch()` gained an `args: list[str] | None = None` parameter**, not present in this sprint's own original Expected Functions signature (`launch(executable_path, requested_by)`). Required to make the pivot above possible at all (a bare `notepad.exe`-style single-path launch can't express `python -c "..."`), and independently justified as a real product need — launching "notepad with `report.txt`" is a natural request a zero-args `launch()` could never support. Additive and backward-compatible (defaults to `None`, preserving the original no-args call shape).
- **`close()` treats a process that already exited on its own as a successful close, not a failure.** Not specified either way by this sprint's own spec. Decided in favor of "successful" after the notepad.exe finding above made this a real, observed scenario (a short-lived spawned process can legitimately exit between `launch()` and a later `close()` call) — the end state (`process_id` no longer running, no longer tracked) is identical to a close this manager itself performed, so treating it as anything other than success would be a distinction without a difference from the caller's point of view.
- **`focus()`'s "window found" path is tested via mocking `_find_window_for_process()`, not a real discovered window.** Empirically verified during implementation: `win32gui.EnumWindows` does not reliably find windows for processes spawned from this specific tool-execution environment (no attached interactive desktop/window station in this automation context) — exactly the "headless/CI environment" caveat this sprint's own Testing Checklist anticipated in advance. The "no window found → `False`" path is still verified for real (a real spawned sleeper process genuinely has no window here); the "window found → `SetForegroundWindow` called" path is verified at the mock boundary instead. This is an environment-of-execution limitation, not a code limitation — the same real pywin32 calls are what actually run in a normal interactive user session (which is where JARMINEI itself will run).
- **`close(process_id)`/`focus(process_id)` re-check `process_id not in self._tracked` independently from `_handle_close()`/`_handle_focus()`'s own identical check**, rather than having the public method raise/signal a distinguishable "untracked" condition for the `execute()`-level wrapper to map to `DENIED`. A deliberate, simple choice: both public methods remain directly usable (and return an honest `bool`) without needing an internal exception type invented solely to communicate one bit of information across a two-line gap.

### Remaining Risks

- **One system-level test (`tests/system/test_level2_acceptance.py::test_full_level2_acceptance_scripted_conversation`) failed once during a full-suite run, then passed both in isolation and on a full-suite re-run.** This test touches only Level 2 (voice/personas) code this sprint never modified; the failure ("Timed out waiting for Quiet Mode Controller to return to DORMANT") matches this project's own documented history of real, timing-sensitive test races under load (see `sprint_3_12.md`'s own completion report for the precedent). Confirmed unrelated to this sprint's changes via isolated re-run (passed) and a full second full-suite run (see this sprint's own STATUS.md note for the final count) — not silently dismissed, verified.
- **`ApplicationManager.launch()`'s bad-path behavior is asymmetric on purpose**: it raises `OSError` directly (a real exception, for a direct caller), while `execute()` catches that same exception and converts it to `ActionStatus.FAILED` (never raising past the `ActionExecutor` boundary). Both are correct for their own callers, but worth flagging for Sprint 4.11's integration work to route through `execute()`, not `launch()` directly, when building real `ActionRequest`s from live conversation turns.
- This sprint's own flagged risks (real process launch being more consequential than any prior sprint's tests, `pywin32` being Windows-only, a launched-but-windowless application making `focus()` meaningless) all held as anticipated; none surfaced as worse than expected.

### Technical Debt

None new. The `notepad.exe` finding is documented as an Engineering Decision (a real, permanent testing-strategy choice) rather than technical debt, since the underlying `ApplicationManager.launch()` implementation itself is unaffected by which executable a test happens to use.

### Recommendations

- **For Sprint 4.3 (File & Folder Operations)**: this sprint's `execute()` routing pattern (a single `parameters["operation"]` dispatch, each branch delegating to a small, independently-testable public method) worked well and is worth reusing rather than re-deriving — `FileOperationsManager` has a naturally larger operation set (six, not four) but the same shape should scale.
- **For Sprint 4.7 (Permission & Confirmation System)**: `DeviceControlConfig.application_allowlist` is real, validated, and ready to be consulted — `PermissionGate.check()` just needs to start reading it.
- **For Sprint 4.11 (Integration)**: prefer routing every real caller through `ActionRegistry.dispatch()` → `ApplicationManager.execute()`, never `ApplicationManager.launch()`/`close()`/`focus()` directly, so the `OSError`-raises-vs-`FAILED`-returns asymmetry noted above never becomes a live production concern.
- **General, for any future sprint writing tests that spawn real GUI-shaped processes**: use the `sys.executable` + `time.sleep()` pattern established here, not `notepad.exe` or another packaged-app-redirected executable — see this sprint's own Engineering Decisions and the test file's module docstring.

**Sprint 4.2 (Application Manager) is complete.** **Sprint 4.3 (File & Folder Operations) is next.**
