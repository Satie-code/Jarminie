# Sprint 4.4 — Window Management

## Sprint ID

4.4

## Sprint Name

Window Management

## Purpose

Implement the third `ActionExecutor` (Sprint 4.1): enumerate, focus, move, resize, minimize, maximize, and close windows — Part 2's Device Control Engine "Windows" control surface and Part 4 Phase 4.1's "Window management" task.

## Engineering Rationale

Corresponds unchanged to `docs/sprint_book/INDEX.md`'s original `4.3 Window Management` roadmap entry. Included in this Sprint Book's scope even though this task's own Level 4 Goal list does not name windows explicitly — Part 2's Device Control Engine section and Part 4's Phase 4.1 task list both name it directly ("Windows" / "Window management"), so it is squarely "already part of the approved architecture," the explicit carve-out this task's own instructions grant. Omitting it here would leave Device Control's approved scope incomplete for no documented reason.

Built after Application Manager (4.2) and File & Folder Operations (4.3), not before, because window operations are frequently *about* a process `ApplicationManager` already tracks (its own launched application's window) — while this sprint does not have a hard dependency on 4.2 (window enumeration works over any window on the system, tracked or not), building it third lets `WindowManager.focus_for_application()` (a convenience the spec below defines) reuse `TrackedApplication.process_id` directly rather than inventing a second process-tracking mechanism.

## Objectives

- `WindowManager` (`ActionExecutor`): enumerate open windows, focus/move/resize/minimize/maximize/close a specific window.
- Window identification is by real, stable window handle (`HWND`), never fragile title-string matching alone — title matching is offered only as a convenience lookup that resolves to an `HWND` before any operation runs.
- A convenience method to focus the main window of a `TrackedApplication` (Sprint 4.2), reusing that sprint's own process tracking rather than duplicating it.

## Dependencies

4.1 (Action Engine Foundation); soft dependency on 4.2 (Application Manager) for the `TrackedApplication` convenience lookup only — `WindowManager` itself does not require 4.2 to function.

## Files to Create

- `device_control/window_manager.py` — `WindowInfo` (dataclass), `WindowManager`.
- `tests/unit/device_control/test_window_manager.py`

## Files to Modify

- `config/schema.py` — `DeviceControlConfig` gains `window_operation_timeout_seconds: float = 5.0` (a real Windows API call can hang against an unresponsive window; every `WindowManager` call is bounded by this).
- `config/defaults.yaml` — matching field.

## Expected Classes

- `WindowInfo` (dataclass) — `handle: int` (the `HWND`, `pywin32`'s native window identifier), `title: str`, `process_id: int`, `is_minimized: bool`, `is_maximized: bool`, `bounds: tuple[int, int, int, int]` (left, top, right, bottom).
- `WindowManager(ActionExecutor)` — constructor DI: `(device_control_config: DeviceControlConfig)`. Handles `WINDOW_FOCUS`, `WINDOW_MOVE`, `WINDOW_RESIZE`, `WINDOW_MINIMIZE`, `WINDOW_CLOSE`.

## Expected Interfaces

None new — implements `ActionExecutor` (4.1).

## Expected Functions

- `WindowManager.can_handle(action_type: ActionType) -> bool`
- `WindowManager.execute(request: ActionRequest) -> ActionResult` — resolves the target window (`parameters["handle"]`, or `parameters["title_contains"]` as a convenience lookup via `list_windows()`, or `parameters["process_id"]` for the `TrackedApplication` convenience path) to a real `HWND` before dispatching to the operation-specific `pywin32` call; catches every `pywin32.error` and returns `ActionStatus.FAILED`, never raises.
- `WindowManager.list_windows() -> list[WindowInfo]` — enumerates all top-level, visible windows via `win32gui.EnumWindows`.
- `WindowManager.find_by_title(title_contains: str) -> WindowInfo | None` — case-insensitive substring match over `list_windows()`; returns the first match (documented as "first match," not "best match" — no fuzzy ranking, matching this project's consistent "plain substring match, no NLU" discipline for similar lookups, e.g. `PersonaManager`'s trigger phrases).
- `WindowManager.find_for_process(process_id: int) -> WindowInfo | None` — the `TrackedApplication` convenience path.

## Data Flow

```
ActionRequest(action_type=WINDOW_FOCUS, parameters={"process_id": tracked_app.process_id})
      ↓
PermissionGate.check() → ALLOW (Sprint 4.1 default; Sprint 4.7 makes this real)
      ↓
WindowManager.execute()
      ↓
find_for_process(process_id) → WindowInfo | None
      ↓ (found)
win32gui.SetForegroundWindow(handle)  /  MoveWindow  /  ShowWindow(minimize/maximize)  /  PostMessage(WM_CLOSE)
      ↓
ActionResult(status, output=WindowInfo)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `window_operation_timeout_seconds`.
2. `device_control/window_manager.py` — `WindowInfo`, `WindowManager`, every method above.
3. Unit tests, against real windows spawned by the test suite itself (e.g. a launched `notepad.exe`, reusing the same "genuinely harmless, universally present" testing pattern Sprint 4.2 establishes) — never against arbitrary pre-existing user windows.

## Architecture Notes

`WindowManager` operates on *any* visible window, not only ones `ApplicationManager` launched — unlike `ApplicationManager`'s "only ever acts on what it itself tracked" boundary (4.2), a window-move/resize/minimize is a far less consequential, far more reversible action than closing or killing a process, so the stricter tracked-only boundary is not applied here. `WINDOW_CLOSE` is the one operation in this set with a real, if usually reversible (most applications prompt to save), destructive shape — Sprint 4.7's risk classification treats it accordingly, distinctly from the other four window operations.

Window resolution (`find_by_title`/`find_for_process`) happens once, producing a stable `HWND`, before any operation — never re-resolved mid-operation — so a title/process match cannot silently drift to a different window between lookup and action under system window-churn.

## Integration Considerations

- Registered with `ActionRegistry` by Sprint 4.11.
- Sprint 4.2's `TrackedApplication.process_id` is the intended input to `find_for_process()` — this sprint's own tests exercise `find_for_process()` directly with a real spawned process, not through `ApplicationManager` itself (keeping the two executors' test suites independent, per Single Responsibility).
- Sprint 4.6 (System Monitoring, Action-Aware)'s resource-pressure gate does not apply to window operations — they are not resource-intensive in the way an application launch or command execution can be; noted here explicitly so a future reader doesn't assume the gate is missing by oversight.

## Potential Risks

- **`pywin32`'s `SetForegroundWindow` is subject to real Windows focus-stealing restrictions** — a background process cannot always steal foreground focus from the currently active window (a deliberate OS security behavior, not a bug). `execute()` must treat a focus call that Windows silently ignores as a genuinely ambiguous outcome (the call didn't error, but focus may not have actually changed) — resolved by verifying the resulting foreground window via `win32gui.GetForegroundWindow()` after the call and reporting `FAILED` if it doesn't match, rather than optimistically reporting `SUCCEEDED`.
- **`WINDOW_CLOSE` via `WM_CLOSE` is a polite request, not a guaranteed termination** — an application with unsaved changes may show its own "save changes?" prompt and never actually close. This sprint's own `execute()` reports `SUCCEEDED` for "the close message was sent," not "the window is confirmed gone" — documented explicitly so Sprint 4.8's audit log records an honest claim, not an overstated one.
- **Multi-monitor coordinate systems** for `WINDOW_MOVE`/`WINDOW_RESIZE` (negative coordinates on a monitor positioned left of/above the primary) are a real Windows behavior this sprint's bounds-handling must account for, verified against the actual multi-monitor target laptop if available, not assumed from single-monitor testing alone.

## Acceptance Criteria

- `list_windows()` returns real, currently-open windows with accurate `WindowInfo` fields.
- Focus/move/resize/minimize/maximize/close all succeed against a real spawned test window.
- An operation against a stale/closed `handle` degrades to `ActionStatus.FAILED` with a clear message, never raises.
- `find_by_title`/`find_for_process` correctly return `None` (not an exception) when no match exists.
- Matches Part 4 Phase 4.1's "Safe desktop control."

## Testing Checklist

- [ ] Unit: `list_windows()` includes a real spawned test window.
- [ ] Unit: focus/move/resize/minimize/maximize/close each succeed against a real spawned test window.
- [ ] Unit: operation against a stale `handle` (window already closed) degrades to `FAILED`.
- [ ] Unit: `find_by_title`/`find_for_process` no-match cases return `None`.
- [ ] Unit: `window_operation_timeout_seconds` bound is respected (simulated via a mocked slow `pywin32` call, since a real hang isn't reproducible on demand).

## Documentation Checklist

- [ ] `device_control/window_manager.py` docstring: the "polite `WM_CLOSE` request, not guaranteed termination" caveat, stated explicitly.
- [ ] `docs/STATUS.md` — Phase 4.1 row notes Window Management complete.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Low–Medium.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

4.5 — Command Execution Engine.

## Future Considerations

- Window snapping/tiling (e.g. "snap left half") — a real productivity feature named nowhere in Part 2/4's approved architecture; not built speculatively, flag for discussion if a real user need surfaces post-Level-4.
- Multi-window layout save/restore (Part 2's own Workflow Engine example, "Restore workspace") — this is genuinely Workflow-shaped functionality, not Window Management's own concern; `WindowManager`'s primitives (move/resize/list) are what a future Workflow step would compose, not something this sprint builds directly.

## Sprint Completion Report (2026-07-20)

Implemented as specified, authorized directly ("proceed with sprint 4.4") — same no-separate-Pass-1 pattern as 4.2/4.3 since this sprint's spec was already complete. Delivered `device_control/window_manager.py` (`WindowInfo`, `WindowManager`), `tests/unit/device_control/test_window_manager.py` (20 tests), `DeviceControlConfig.window_operation_timeout_seconds` (default 5.0, validated `> 0`). 715/715 full-suite tests passing, `ruff check .` clean.

**One real design gap in the spec itself, resolved during implementation**: `action_engine.py`'s `ActionType` enum (Sprint 4.1) declares `WINDOW_FOCUS`/`WINDOW_MOVE`/`WINDOW_RESIZE`/`WINDOW_MINIMIZE`/`WINDOW_CLOSE` — no `WINDOW_MAXIMIZE`, even though this sprint's own Objectives and Potential Risks both name "maximize" as a real, required operation. Adding a new enum value would have meant modifying `action_engine.py`, which this sprint's own Files to Modify excludes. Resolved by reusing `ApplicationManager`'s own established precedent (Sprint 4.2): `parameters["operation"]`, not the `ActionType` tag, is the real dispatch key — `execute()` dispatches on `operation` (`"focus"`/`"move"`/`"resize"`/`"minimize"`/`"maximize"`/`"close"`) regardless of which of the five handled `ActionType`s the request carries, so "maximize" needed no new enum member. Consistent with an existing pattern, not a new one — no separate check-in needed.

**Two real bugs found only by running the implementation for real against actual Win32 windows, not by reasoning about the API docs**:

- **Cross-thread window-message hang, found via the test suite's own first real run.** `_call_with_timeout()` runs every native call (`SetForegroundWindow`/`MoveWindow`/`ShowWindow`) on a helper thread so a hung call can't block `WindowManager` itself — correct in principle, but the first test run against an in-process synthetic test window hung on every operation until the configured timeout. Root cause: these Win32 APIs are synchronous sends to the *target window's own owning thread's message queue* — a thread modifying a window it itself created gets a same-thread fast path with no queue involved, which is why early manual verification scripts (single-threaded, no wrapper) worked instantly; routing through `_call_with_timeout`'s separate worker thread turns every call into a genuine cross-thread send that only completes if the window-owning thread is actively pumping messages. The test's synthetic window, created directly on pytest's main thread with no message loop, never pumped — so every wrapped call legitimately hung. **This is a real property of Win32, not a `WindowManager` bug**: every actual target window in production belongs to some other already-running application, whose own UI thread is always pumping its message queue independently of anything `WindowManager`'s caller thread is doing — so this only ever affected the test double. Fixed at the test level, not the production code: `_TestWindow` (in `test_window_manager.py`) now creates and message-pumps (`win32gui.PumpMessages()`) each test window on its own dedicated thread, faithfully simulating how a real target window actually behaves, and in doing so exercises `_call_with_timeout`'s real cross-thread path rather than accidentally bypassing it via a same-thread special case. **Generalizable pattern**: any future test double for a Win32 window (or any other OS object with thread-affinity/its-own-message-loop semantics) needs its own owning+pumping thread to be a faithful stand-in, not just a same-process, same-thread construction.
- **`SetForegroundWindow` cannot be verified as genuinely succeeding in this automation environment** — a real call from this environment raised `pywintypes.error` rather than silently no-op'ing (the "focus-stealing restriction" scenario the sprint's own Potential Risks anticipated, just manifesting as an error here instead of a silent no-op). The same class of real-desktop-session restriction `ApplicationManager`'s own focus test (Sprint 4.2) already hit and worked around. Resolved identically: the "focus succeeds" test mocks `SetForegroundWindow`/`GetForegroundWindow` and asserts on the resolved target + call arguments, matching `test_application_manager.py`'s own established precedent for this exact situation, rather than asserting on real OS focus state this environment cannot grant.

**Testing deviation from the sprint's own literal suggestion, not from its intent**: the spec's Implementation Tasks suggested testing "against real windows spawned by the test suite itself (e.g. a launched `notepad.exe`)." Verified empirically before writing tests that spawning an external process's window is unreliable for automated testing in this environment — the same class of flakiness that made Sprint 4.2 move its own tests from `notepad.exe` to a `sys.executable` child process. `WindowManager` operates on *any* visible window, so an in-process window created directly via `win32gui.CreateWindow` (on its own dedicated, message-pumping thread — see above) is an equally real, actually more reliable and more deterministic test target, exercising the exact same `pywin32` calls `WindowManager` itself makes. Confirmed and documented in the test module's own docstring rather than silently substituted.

**Verified for real, not just via fakes**: every operation (list/find_by_title/find_for_process/move/resize/minimize/maximize/close/stale-handle) runs against a real Win32 window and real `pywin32` calls; only the two focus-specific tests mock at the exact boundary this environment cannot grant (see above). `window_operation_timeout_seconds`'s bound is verified via a mocked slow call per the sprint's own Testing Checklist, since a real hang isn't reproducible on demand.

Not yet wired into `main.py`/`ActionRegistry` — per this sprint's own Integration Considerations, that's Sprint 4.11's job. **Sprint 4.5 (Command Execution Engine) is next.**
