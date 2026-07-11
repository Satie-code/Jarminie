# Sprint 1.9 — Debug Console

## Sprint ID
1.9

## Sprint Name
Debug Console

## Purpose
Complete Phase 1.3 (Desktop Interface) with an in-app log viewer, giving the user/developer a live view of exactly what JARMINEI is doing and why — reinforcing the Explainability Rule at the UI layer.

## Objectives
- A panel/window streaming live log output (from Sprint 1.3's logging system) into the GUI, not just the file/console.
- Filterable by log level.
- No impact on logging performance for the non-GUI log destinations.

## Engineering Rationale
This is the last Level 1 sprint and the natural place to close the loop between "logs exist" (1.3) and "logs are visible to the user without opening a text file" (1.9). It reuses the standard `logging` module's handler mechanism rather than inventing a parallel logging path, keeping Sprint 1.3's Single Responsibility (this module owns format/destination policy) intact.

## Prerequisites
Sprints 1.6 and 1.3 complete.

## Dependencies
1.6, 1.3

## Files to Create
- `ui/debug_console.py` — `DebugConsole(QWidget)`, `QtLogHandler(logging.Handler)`.
- `tests/unit/ui/test_debug_console.py`

## Files to Modify
- `ui/main_window.py` — add a menu/button to open `DebugConsole`.
- `core/logging_setup.py` — `configure_logging()` gains an optional hook to attach a GUI handler (confirm minimal-diff approach during implementation — prefer attaching the handler from the UI layer via `get_logger()`'s returned root logger rather than modifying `configure_logging()`'s signature, to avoid the logging module knowing anything about the UI layer).

## Expected Classes
- `QtLogHandler(logging.Handler)` — emits records as a Qt signal so `DebugConsole` can safely update from the logging thread.
- `DebugConsole(QWidget)` — a scrollable log view + a level filter dropdown.

## Expected Interfaces
None new — extends the standard `logging.Handler` extension point.

## Expected Functions
- `QtLogHandler.emit(record: logging.LogRecord) -> None` — formats and emits via Qt signal.
- `DebugConsole.set_level_filter(level: int) -> None`

## Implementation Tasks
1. Implement `QtLogHandler` with a Qt signal carrying formatted log lines (must be thread-safe — logging can happen off the GUI thread).
2. Implement `DebugConsole` UI: read-only scrolling text view + level filter.
3. Attach `QtLogHandler` to the root logger when `DebugConsole` opens; detach when closed (avoid leaking handlers).
4. Tests: a log call made anywhere appears in `DebugConsole`'s buffer at or above the selected filter level; handler detaches cleanly on close (no duplicate lines if reopened).

## Architecture Notes
`core/logging_setup.py` remains ignorant of Qt — the UI layer attaches/detaches its own handler using the public `logging` API (`logging.getLogger().addHandler(...)`), preserving the layering established in Sprint 1.6 (UI depends on Core, never the reverse).

## Potential Risks
- **Thread-safety**: log calls can originate from any thread (e.g. a future background worker); `QtLogHandler` must marshal to the GUI thread via Qt's signal/slot mechanism rather than touching widgets directly from `emit()`. Called out explicitly so it isn't missed during implementation.
- **Handler leak on repeated open/close** if detach is forgotten — covered by the "detaches cleanly" test above.

## Acceptance Criteria
- Log messages emitted anywhere in the app appear live in the Debug Console.
- Level filter correctly hides/shows messages.
- Closing and reopening the console does not duplicate or drop messages (matches Phase 1.3's "Debug console" objective).

## Testing Checklist
- [ ] Unit: `QtLogHandler.emit()` formats correctly.
- [ ] Unit: level filter hides messages below the selected level.
- [ ] Unit: handler detaches on close (no duplicate lines on reopen).
- [ ] Manual: trigger a log call from another part of the app, confirm it appears live.

## Documentation Checklist
- [ ] `ui/debug_console.py` docstring.
- [ ] `docs/STATUS.md` — mark Phase 1.3 acceptance criteria met; Level 1 / Release v0.1 marked complete once this sprint closes.

## Definition of Done
Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). Completing this sprint completes Phase 1.3 and Level 1 — Release v0.1 per [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md).

## Estimated Complexity
Low.

## Estimated Development Time
0.5–1 day.

## Next Sprint
2.1 — Wake Word Detector (Level 2 — Communication; full sprint detail to be written when Level 2 becomes current, per [INDEX.md](INDEX.md)).

## Future Considerations
- Exporting console output to a file on demand — minor UX nicety, not required for v1.
- **Release v0.1 checkpoint**: once 1.9 is done, run the full Level 1 acceptance pass (all of Phase 1.1–1.3's criteria together) before tagging `0.1.0` and writing `docs/changelog/0.1.0.md` — this is a Level-level gate, not a task of any single sprint.

---

## Sprint Completion Report

### Summary

Implemented Debug Console: `QtLogHandler` bridges Python's `logging` module to Qt via a signal (thread-safe by construction), `DebugConsole` shows a buffered, level-filterable, live scrolling view, attaching/detaching its own handler on open/close without `core/logging_setup.py` knowing anything about Qt — confirmed no change to that file was needed, exactly as the sprint doc's own preferred approach anticipated. Also proactively consolidated `VALID_LOG_LEVELS` into a single shared constant (`config/schema.py`) before a third copy of that list could accumulate across `config/schema.py`, `ui/settings_window.py`, and this sprint's `ui/debug_console.py` — directly applying the lesson from Sprint 1.8's config-section bug.

This sprint completes Phase 1.3 and **Level 1 in full** — see the Level 1 acceptance pass below.

### Files Created

- `ui/debug_console.py` — `QtLogHandler`, `DebugConsole`.
- `tests/unit/ui/test_debug_console.py` (8 tests).

### Files Modified

- `ui/main_window.py` — Debug menu, `_open_debug_console()`, and a `closeEvent()` fix (see Engineering Decisions).
- `config/schema.py` — `_VALID_LOG_LEVELS` (private set) → `VALID_LOG_LEVELS` (public tuple), single source of truth.
- `config/__init__.py`, `ui/settings_window.py` — updated to the shared constant.
- `tests/unit/ui/test_main_window.py` — Debug menu tests + a real regression test for the closeEvent fix.
- `core/logging_setup.py` — **not modified**, confirming the sprint doc's preferred minimal-diff approach was sufficient.

### Engineering Decisions / Bugs Found and Fixed

Continuing Sprint 1.8's "drive the real widget" discipline caught one more real bug, this time only visible by running the actual `app.exec()` event loop end-to-end (not caught by any unit test, mocked or otherwise):

- **Closing the main window didn't quit the app if Debug Console was still open.** `DebugConsole` is a separate top-level window, not a child dialog destroyed automatically with `MainWindow`. Qt's `app.exec()` keeps the event loop alive as long as *any* top-level window remains visible — so closing the main window left the process running invisibly, with Debug Console still on screen. Fixed by having `MainWindow.closeEvent()` explicitly close `self._debug_console` if one is open, so closing the main window always quits the whole app. A dedicated real-event-loop smoke script (auto-closing the main window after opening Debug Console) is what surfaced this — a `qtbot`-based test wouldn't have, since `qtbot` never calls `app.exec()`.

Other decisions:
- `QtLogHandler` composes a plain `QObject` for its signal rather than inheriting from both `logging.Handler` and `QObject` — avoids potential metaclass conflicts between Python's logging system and Qt's meta-object system.
- `SensitiveDataFilter` (Sprint 1.3) is explicitly attached to `QtLogHandler` too — redaction must apply uniformly across every destination (console, file, *and* this live GUI view), not just the two built in Sprint 1.3.
- The level filter re-renders from an in-memory buffer (capped at 2000 lines) on every change, so raising/lowering it retroactively hides/shows already-received lines, not just future ones — a slightly richer interpretation of "hides/shows messages" than the minimum, justified by being a small, bounded addition consistent with Resource Protection principles.

### Tests Added

8 in `test_debug_console.py` (format/emit correctness, redaction, live display, level filtering both directions — retroactive hide and retroactive show, handler attach/detach, reopen-without-duplication), 3 new in `test_main_window.py` (Debug menu exists, opening it shows a real console with real live logs, and the closeEvent regression test). 88/88 total passing, `ruff` clean, plus three real event-loop smoke scripts (Sprints 1.6, 1.8, 1.9) all passing after this sprint's fix.

### Documentation Updated

This file (Sprint Completion Report). See the Level 1 Acceptance Pass and `docs/STATUS.md` / `docs/changelog/0.1.0.md` below.

### Acceptance Criteria Checklist

- ✔ Log messages emitted anywhere in the app appear live in the Debug Console (verified via unit tests and a real event-loop run).
- ✔ Level filter correctly hides/shows messages (both directions, retroactively).
- ✔ Closing and reopening the console does not duplicate or drop messages.

### Remaining Risks

None blocking.

### Technical Debt

None introduced.

### Recommendations for Level 2

- The "drive the real widget / real event loop" verification discipline (established Sprint 1.8, reinforced here) should carry into Level 2 — voice pipeline sprints will have even more real-world integration surface (audio hardware, model inference) where mocks alone will under-test.
- `ManagedModule`'s fit for the Voice Engine's dormant/wake-word lifecycle (flagged as an open risk back in Sprint 1.5) should be revisited at the start of Sprint 2.1, before writing code against it.

---

## Level 1 Acceptance Pass (Release v0.1 checkpoint)

Per this sprint's own Future Considerations, before tagging `0.1.0`:

| Phase | Acceptance Criteria (from 04_Master_Implementation_Plan.md) | Status |
|---|---|---|
| 1.1 | Project builds successfully; no warnings; repository organized | ✔ `ruff check .` clean, 88/88 tests pass |
| 1.2 | JARMINEI launches; JARMINEI exits cleanly; logging works; configuration loads | ✔ Verified via `main.py` real runs across Sprints 1.5-1.9 |
| 1.3 | Application launches with GUI; settings persist | ✔ Real window opens (1.6), settings genuinely survive a simulated restart (1.8) |

Full suite: 88/88 passing, `ruff check .` clean. Three real event-loop smoke scripts (window open/close, settings persistence, debug console) all pass. `main.py` is a real, working PySide6 desktop application: it loads config, initializes logging, starts Core, shows a window with live module/resource status, lets the user edit and persist settings, and lets the user watch live logs — then shuts down cleanly on close.

**Level 1 — Foundation is complete. Release v0.1.**
