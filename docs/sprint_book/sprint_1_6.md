# Sprint 1.6 — Desktop Shell & Main Window

## Sprint ID

1.6

## Sprint Name

Desktop Shell & Main Window

## Purpose

Begin Phase 1.3 (Desktop Interface): a native PySide6 window that hosts the Core Manager lifecycle, satisfying the first half of the phase's acceptance criteria — "Application launches with GUI."

## Objectives

- A `QApplication` bootstrap that replaces `main.py`'s placeholder wait-loop from Sprint 1.5 with a real GUI event loop.
- A `MainWindow` that starts Core Manager on open and shuts it down cleanly on close.
- Establish the UI layer's DI pattern: `MainWindow` receives a `CoreManager` instance, it does not construct one.

## Engineering Rationale

This is the first sprint to actually install and exercise PySide6 (deferred as documented technical debt since Sprint 1.1 — see [../backlog/technical_debt.md](../backlog/technical_debt.md) item 1, partially resolved here). Keeping the window itself "dumb" (delegates lifecycle to Core Manager, owns no business logic) follows the same Single Responsibility discipline as Core Manager itself.

## Prerequisites

Sprint 1.5 (Core Manager) complete.

## Dependencies

1.5

## Files to Create

- `ui/app.py` — `run_app(core_manager: CoreManager) -> int`.
- `ui/main_window.py` — `MainWindow(QMainWindow)`.
- `tests/unit/ui/test_main_window.py`

## Files to Modify

- `main.py` — replace the placeholder wait/exit with `ui.app.run_app(core_manager)`.
- `requirements.txt` — no schema change, but this sprint is when `pip install PySide6` actually happens in the dev venv (resolves part of backlog item 1).

## Expected Classes

- `MainWindow(QMainWindow)` — constructor takes a `CoreManager`; `closeEvent()` calls `core_manager.shutdown()` before accepting the close.

## Expected Interfaces

None new — PySide6's `QMainWindow` is the framework's own extension point; no additional abstraction needed for a single-window v1 UI.

## Expected Functions

- `run_app(core_manager: CoreManager) -> int` — constructs `QApplication`, constructs `MainWindow(core_manager)`, calls `core_manager.startup()`, shows the window, runs `app.exec()`, returns the exit code.

## Implementation Tasks

1. `pip install PySide6` into `.venv`, confirm import works.
2. Implement `MainWindow` with a placeholder central widget (title bar "JARMINEI", empty body — Status Panel/Settings/Debug Console fill it in Sprints 1.7–1.9).
3. Wire `closeEvent()` to `CoreManager.shutdown()`.
4. Implement `run_app()` and update `main.py` to call it.
5. Tests: `MainWindow` construction doesn't raise; `closeEvent()` triggers `shutdown()` on a mock `CoreManager` (PySide6 widget tests run via `pytest-qt` — add as a dev dependency this sprint).

## Architecture Notes

`main.py` remains the sole composition root (per Sprint 1.5's note) — it now additionally decides GUI vs. future headless mode, but for Level 1 GUI is the only path. `MainWindow` never imports `config`, `core.logging_setup`, or `core.resource_monitor` directly — it only knows about `CoreManager`, keeping the UI layer decoupled from infrastructure details (it can ask Core Manager for status instead, which Sprint 1.7 will do).

## Potential Risks

- **`pytest-qt` adds a new dev dependency** not previously declared — add to `requirements-dev.txt` this sprint, note in Files to Modify above and call out explicitly rather than silently expanding scope.
- **First heavy GUI dependency install** — PySide6 is ~200MB; confirm CI/dev-machine install time is acceptable (should be, it's a single well-packaged wheel, unlike the ML dependencies still deferred).

## Acceptance Criteria

- Running `main.py` opens a native window titled "JARMINEI".
- Closing the window triggers `CoreManager.shutdown()` and the process exits cleanly (matches Phase 1.3's "Application launches with GUI").

## Testing Checklist

- [ ] Unit: `MainWindow` constructs without error given a mock `CoreManager`.
- [ ] Unit: `closeEvent()` calls `core_manager.shutdown()` exactly once.
- [ ] Manual: visually confirm the window opens and closes cleanly on this machine (per the project's "test the golden path in a browser/app" practice, adapted to desktop).

## Documentation Checklist

- [ ] `ui/app.py` and `ui/main_window.py` docstrings.
- [ ] `README.md` "Development Setup" — note that `requirements-dev.txt` now includes `pytest-qt`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1 day.

## Next Sprint

1.7 — Status Panel.

## Future Considerations

- A headless/voice-only run mode (no GUI) is architecturally implied by the Voice Engine's Quiet Mode but explicitly out of scope until it's actually needed — likely Level 2.

---

## Sprint Completion Report

### Summary

Installed PySide6 for real (resolving part of backlog item 1) and built the desktop shell: `MainWindow` hosts Core Manager's lifecycle, `run_app()` drives the Qt event loop, and `main.py` was rewritten to compose config → logging → resource monitor → Core Manager → `run_app()`. Verified with a real `app.exec()` run (auto-closing after 1s to simulate a user closing the window), not just mocked unit tests — window opened, ran, closed, and Core shut down cleanly, exit code 0.

### Files Created

- `ui/main_window.py` — `MainWindow(QMainWindow)`.
- `ui/app.py` — `run_app(core_manager) -> int`.
- `tests/unit/ui/test_main_window.py` (2 tests, via `pytest-qt`'s `qtbot` fixture).

### Files Modified

- `main.py` — restructured from `try/startup/finally/shutdown` to delegating the whole lifecycle to `run_app()`; shutdown now happens inside `MainWindow.closeEvent()`, triggered by the Qt event loop, not by `main.py` directly.
- `requirements-dev.txt` — added `pytest-qt>=4.4`.
- `README.md` — "Development Setup" now notes `pytest-qt` is part of the dev install.

### Engineering Decisions

- **Real bug caught by actually running the app, not just unit tests**: the `closeEvent()` log message originally used an em dash (`—`), which rendered as mojibake in the Windows console (the file handler is explicit UTF-8 and was unaffected, but the console `StreamHandler` uses the console's default codepage). Fixed by using a plain hyphen, matching the ASCII-only convention already used in every other runtime log message across the codebase (docstrings/comments still use em dashes freely — those never pass through logging). Confirms the value of the "test the golden path, don't just trust unit tests" practice for UI-adjacent work.
- **Manual verification approach**: since a terminal-based agent can't visually inspect a GUI, verification used a real `QApplication.exec()` run with `QTimer.singleShot` auto-closing the window after 1 second — this exercises the actual event loop and real `closeEvent()` path that `qtbot`'s `.close()` call in unit tests approximates but doesn't fully replicate (unit tests never call `app.exec()`). The verification script itself was a throwaway file in the scratchpad, not committed to the repo.
- **`# noqa: N802` on `closeEvent`**: PySide6's Qt override methods use `camelCase` (`closeEvent`, not `close_event`), which conflicts with the project's `snake_case` function-naming rule — this is a framework-mandated override, not a naming choice, so it's suppressed with a comment explaining why rather than silently violating or silently suppressing without explanation.

### Tests Added

2 unit tests via `pytest-qt`: `MainWindow` constructs without error and has the correct title; closing the window calls `core_manager.shutdown()` exactly once. Plus the real-event-loop manual verification described above.

### Documentation Updated

This file (Sprint Completion Report). `README.md` dev setup note. `docs/STATUS.md` Phase 1.3 row.

### Acceptance Criteria Checklist

- ✔ Running `main.py` opens a native window titled "JARMINEI" (verified both via unit test and a real `app.exec()` run).
- ✔ Closing the window triggers `CoreManager.shutdown()` and the process exits cleanly (verified via unit test and real run — exit code 0, full shutdown sequence logged).

### Remaining Risks

None blocking. The console-encoding class of bug (non-ASCII characters in log messages breaking on Windows' default console codepage) is worth remembering for any future log message — flagged here for visibility, not because it's expected to recur given the ASCII-only convention already in place elsewhere.

### Technical Debt

None introduced. Backlog item 1 (deferred full dependency install) is now partially resolved — PySide6 is installed; Whisper/openWakeWord/coqui-tts/ChromaDB remain deferred to their respective Level 2/3 sprints.

### Recommendations for Sprint 1.7

- Status Panel should read from `CoreManager.module_states()` and `CoreManager.check_resources()` (both already built in Sprint 1.5) — no new Core Manager methods anticipated.
- Consider whether the `MainWindow`'s placeholder `QLabel` central widget should become a `QVBoxLayout`-based container now, so Sprints 1.7-1.9 can each add their widget without restructuring the layout — worth deciding at the start of Sprint 1.7 rather than each sprint patching around a single-label central widget.
