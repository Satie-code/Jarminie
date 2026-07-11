# Sprint 1.7 — Status Panel

## Sprint ID

1.7

## Sprint Name

Status Panel

## Purpose

Surface Core Manager's module registry and the Health Monitor's resource readings inside the main window, giving the user (and the developer) live visibility into what JARMINEI is doing — a concrete instance of the Explainability Rule applied to system state, not just individual actions.

## Objectives

- A widget showing each registered module's name and state (running / stopped / restarting).
- A live CPU/RAM/battery/disk readout sourced from `ResourceMonitor`.
- Updates on a timer without polling faster than useful (Part 3's performance guidance).

## Engineering Rationale

This is the first sprint where the UI layer reads from more than one subsystem (`CoreManager`'s registry and `ResourceMonitor`), so it's a good first test of whether the Sprint 1.5/1.6 DI boundaries hold up in practice. It's ordered before Settings/Debug Console because it's pure read-only display — lower risk than Settings' read/write path.

## Prerequisites

Sprints 1.6 and 1.4 complete.

## Dependencies

1.6, 1.4

## Files to Create

- `ui/status_panel.py` — `StatusPanel(QWidget)`.
- `tests/unit/ui/test_status_panel.py`

## Files to Modify

- `ui/main_window.py` — embed `StatusPanel` as (part of) the central widget.
- `core/manager.py` — add a read-only `CoreManager.module_states() -> dict[str, str]` accessor if not already sufficient from Sprint 1.5 (confirm during implementation; only modify if the existing `ModuleRegistry` API doesn't already expose this cleanly).

## Expected Classes

- `StatusPanel(QWidget)` — constructor takes `CoreManager` and `ResourceMonitor`; internal `QTimer` triggers periodic refresh.

## Expected Interfaces

None new.

## Expected Functions

- `StatusPanel.refresh() -> None` — pulls current module states + a fresh `ResourceMonitor.sample()`, updates labels.

## Implementation Tasks

1. Implement `StatusPanel` layout: a module list + a resource readout row.
2. Wire a `QTimer` (default interval from `AppConfig`, e.g. every 2–5 seconds — configurable, not hardcoded, per the Configuration Management rule) calling `refresh()`.
3. Embed in `MainWindow`.
4. Tests: `refresh()` correctly updates displayed values given mock `CoreManager`/`ResourceMonitor` data; timer interval is read from config, not a literal.

## Architecture Notes

`StatusPanel` only reads — it never calls `restart_module()` or otherwise mutates state (that stays a Core Manager internal decision for now; a manual "restart" button is a plausible future sprint, not this one, to keep this sprint's scope to display only).

## Potential Risks

- **Timer interval too aggressive** could itself become a resource drain, ironically undermining Resource Protection — default to a conservative interval (few seconds) and make it configurable so it can be tuned without a code change.

## Acceptance Criteria

- Status Panel visibly updates module states and resource readings on the configured interval.
- No polling faster than the configured interval (verified by counting `refresh()` calls in a timed test).

## Testing Checklist

- [ ] Unit: `refresh()` updates panel state from mock data.
- [ ] Unit: timer interval matches `AppConfig` value, not hardcoded.
- [ ] Manual: visually confirm live updates.

## Documentation Checklist

- [ ] `ui/status_panel.py` docstring.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Low.

## Estimated Development Time

0.5 day.

## Next Sprint

1.8 — Settings Window.

## Future Considerations

- Manual module restart/stop controls from the panel — flagged as a future UX improvement, not part of the official v1 roadmap unless added to the spec.

---

## Sprint Completion Report

### Summary

Implemented Status Panel: live module states (from `CoreManager.module_states()`) and a resource readout (from `CoreManager.check_resources()`), refreshed on a configurable `QTimer`. Also implemented both recommendations accepted after Sprint 1.6: `StatusPanel` depends only on `CoreManager` (not a separate `ResourceMonitor`), and `MainWindow`'s central widget is now a `QVBoxLayout` container ready for Sprints 1.8–1.9. Added `UIConfig` to the schema so the refresh interval is genuinely configurable, not hardcoded, and gave `CoreManager._config` (unused since Sprint 1.5) its first real use via a new `ui_config()` accessor. Verified with the real Qt event loop, sampling actual hardware.

### Files Created

- `ui/status_panel.py` — `StatusPanel(QWidget)`.
- `tests/unit/ui/test_status_panel.py` (8 tests), `tests/unit/ui/conftest.py` (shared fixtures).

### Files Modified

- `ui/main_window.py` — central widget is now a `QVBoxLayout` container; embeds `StatusPanel`.
- `core/manager.py` — added `ui_config() -> UIConfig`.
- `config/schema.py` — added `UIConfig` (`status_refresh_interval_ms`, default 3000, validated to [250, 60000]) and wired it into `AppConfig`/`validate()`.
- `config/defaults.yaml`, `config/__init__.py` — `ui:` section and `UIConfig` export.
- `tests/unit/config/test_schema.py`, `tests/unit/core/test_manager.py` — coverage for the new config field and accessor.
- `tests/unit/ui/test_main_window.py` — updated to use a properly-configured mock `CoreManager` (a bare `MagicMock()` no longer suffices now that `MainWindow` constructs a real `StatusPanel` that calls `module_states()`/`check_resources()`/`ui_config()` during `__init__`).

### Engineering Decisions

- **`StatusPanel(core_manager)` only** — deviates from the sprint doc's literal "constructor takes `CoreManager` and `ResourceMonitor`," per the recommendation you approved after Sprint 1.6. Keeps the "UI layer only knows about CoreManager" boundary intact.
- **New `UIConfig` schema section** — the sprint doc required the refresh interval be config-driven, but no such field existed yet. Added following the exact pattern established in Sprint 1.2 (own nested dataclass, own validation method), with bounds (250ms–60s) directly addressing the sprint's own "Timer interval too aggressive" risk.
- **`core/manager.py`'s previously-unused `_config`** (flagged as "retained for forward compatibility" back in Sprint 1.5) **now has a real caller** — `ui_config()`. Noted explicitly since it closes a loop opened two sprints ago.
- **Shared test fixtures via `conftest.py`, not a plain helper import**: first attempt imported a helper function across test files with `from .conftest import ...`, which fails because `tests/` has no `__init__.py` (an established convention since Sprint 1.1) — relative imports need a real package. Fixed by exposing the shared builder as a pytest fixture (`resource_snapshot_factory`) instead, which pytest auto-discovers regardless of package structure. Caught immediately by running the suite, not left broken.

### Tests Added

8 new in `test_status_panel.py` (module/resource label rendering, no-modules placeholder, missing-battery handling, initial refresh on construction, interval sourced from config not hardcoded, and a bounded poll-rate check), 1 in `test_main_window.py` (Status Panel embedded and actually calling into Core Manager), 3 in `test_schema.py` (interval too low/high/valid), 1 in `test_manager.py` (`ui_config()` returns the right slice). 64/64 total passing, `ruff` clean.

### Documentation Updated

This file (Sprint Completion Report). `docs/STATUS.md` Phase 1.3 row.

### Acceptance Criteria Checklist

- ✔ Status Panel visibly updates module states and resource readings on the configured interval (verified via real event-loop run and unit tests).
- ✔ No polling faster than the configured interval (`test_timer_does_not_poll_faster_than_configured_interval`, bounded call-count check over a timed window).

### Remaining Risks

None blocking. The "no modules registered" placeholder will remain accurate-but-uninteresting until Level 2+ sprints actually register real subsystems with Core Manager — expected, not a defect.

### Technical Debt

None introduced.

### Recommendations for Sprint 1.8

- Settings Window should add a form section for `UIConfig.status_refresh_interval_ms` alongside the other config sections, now that it exists.
- No changes anticipated to `StatusPanel` or `CoreManager`'s public API.
