# Sprint 1.8 — Settings Window

## Sprint ID

1.8

## Sprint Name

Settings Window

## Purpose

A UI over the Configuration Manager (Sprint 1.2) so the user can view and edit settings without hand-editing YAML, satisfying the second half of Phase 1.3's acceptance criteria: "Settings persist."

## Objectives

- A dialog exposing the editable fields of `AppConfig` (wake phrase, resource thresholds, voice selection, model selection, etc.).
- Saving writes through `ConfigLoader.save()` and the change survives an app restart.
- Invalid input is rejected with a clear message before it ever reaches `ConfigLoader.save()`.

## Engineering Rationale

This is the first read _and write_ path from the UI layer, and the first place user input reaches the configuration system — validation matters more here than in Status Panel. Building on `ConfigLoader.save()` (already speced in Sprint 1.2) rather than inventing a second persistence path keeps configuration writes single-sourced.

## Prerequisites

Sprints 1.6 and 1.2 complete.

## Dependencies

1.6, 1.2

## Files to Create

- `ui/settings_window.py` — `SettingsWindow(QDialog)`.
- `tests/unit/ui/test_settings_window.py`

## Files to Modify

- `ui/main_window.py` — add a menu/button to open `SettingsWindow`.
- `config/loader.py` — only if `save()` needs adjustment once exercised by a real caller (confirm during implementation).

## Expected Classes

- `SettingsWindow(QDialog)` — constructor takes the current `AppConfig` and a `ConfigLoader`; builds form fields per config section.

## Expected Interfaces

None new.

## Expected Functions

- `SettingsWindow.load_from_config(config: AppConfig) -> None` — populates form fields.
- `SettingsWindow.to_config() -> AppConfig` — builds a candidate config from current form values.
- `SettingsWindow.on_save() -> None` — validates (`AppConfig.validate()` from Sprint 1.2), and on success calls `ConfigLoader.save()`; on failure shows the validation error inline and does not close the dialog.

## Implementation Tasks

1. Build the form UI grouped by config section (Voice, Resources, Database, Models, Logging).
2. Implement `to_config()` / `load_from_config()`.
3. Wire `on_save()` through `AppConfig.validate()` before `ConfigLoader.save()`.
4. Tests: valid edit round-trips through save/reload correctly; invalid edit (e.g. threshold > 100) is rejected and does not call `save()`.

## Architecture Notes

Validation happens in `AppConfig.validate()` (Sprint 1.2), reused here rather than re-implemented in the UI layer — a single source of truth for "what makes a config valid," consistent with avoiding duplicated logic.

## Potential Risks

- **Comment loss on YAML round-trip** (already flagged in Sprint 1.2) becomes user-visible here for the first time — if the user hand-edited `config/defaults.yaml` with comments before ever opening Settings, saving from this dialog will silently drop them. Worth a one-line warning in the dialog or docs; not a blocker for v1.

## Acceptance Criteria

- Changing a setting in the dialog and clicking Save persists it to the config file.
- Restarting the app reflects the previously saved value (the literal Phase 1.3 acceptance criterion: "Settings persist").
- An invalid value is rejected with a visible error and not written to disk.

## Testing Checklist

- [ ] Unit: `to_config()`/`load_from_config()` round-trip.
- [ ] Unit: `on_save()` with valid data calls `ConfigLoader.save()`.
- [ ] Unit: `on_save()` with invalid data does not call `save()` and surfaces an error.
- [ ] Manual: edit a setting, restart `main.py`, confirm persistence.

## Documentation Checklist

- [ ] `ui/settings_window.py` docstring.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint closes out Phase 1.3's "Settings persist" acceptance criterion.

## Estimated Complexity

Low–Medium.

## Estimated Development Time

1 day.

## Next Sprint

1.9 — Debug Console.

## Future Considerations

- Per-field help text / tooltips explaining what each setting does — nice-to-have, not required for v1.

---

## Sprint Completion Report

### Summary

Implemented Settings Window: a dialog exposing all six `AppConfig` sections (Voice, Resources, Database, Models, Logging, and UI — the last per the recommendation accepted after Sprint 1.7), validated through `AppConfig.validate()` before ever reaching `ConfigLoader.save()`. `CoreManager` was extended (a new `config_loader` constructor parameter) to expose the full config and the loader, so `MainWindow` can open Settings while still only depending on `CoreManager`. This sprint closes Phase 1.3's "Settings persist" acceptance criterion — verified with a real, non-mocked persistence test that simulates an app restart, which is what actually surfaced three real bugs (below), none of which the earlier unit tests caught.

### Files Created

- `ui/settings_window.py` — `SettingsWindow(QDialog)`.
- `tests/unit/ui/test_settings_window.py` (6 tests).

### Files Modified

- `ui/main_window.py` — Settings menu, `_open_settings()`.
- `core/manager.py` — new `config_loader` constructor param; `config()` and `config_loader()` accessors.
- `main.py` — constructs `ConfigLoader` explicitly (was: `load_config()` convenience wrapper) so the loader instance can be handed to `CoreManager`.
- `config/loader.py` — three real bug fixes (see below).
- `tests/unit/core/test_manager.py` — updated all `CoreManager(...)` call sites for the new constructor param; added `config()`/`config_loader()` tests.
- `tests/unit/ui/conftest.py` — `mock_core_manager` now also configures `config()`/`config_loader()`.
- `tests/unit/config/test_loader.py` — 3 new regression tests for the bugs below.

### Engineering Decisions / Bugs Found and Fixed

This sprint's real (non-mocked) persistence test — `SettingsWindow` → real `ConfigLoader.save()` → fresh `ConfigLoader.load()` — caught three genuine, pre-existing bugs that every earlier mocked/unit test had missed:

1. **`ConfigLoader.save(config)` (no explicit path) wrote to the wrong file.** It defaulted to the module-level `LOCAL_CONFIG_PATH` constant instead of the `local_path` the specific loader instance was constructed with. Every prior test that exercised `save()` happened to pass an explicit `path=`, so this never surfaced — until Settings Window became the first real caller of the bare `save(config)` form. Fixed by storing `self._local_path` and defaulting to it. **Side effect**: this bug, while still present, caused a stray `config/local.yaml` to be written into the actual project directory during test debugging (not a test fixture, the _real_ one) — found and deleted; it was never committed (already gitignored) and contained no meaningful data.
2. **`_dict_to_config()` never constructed the `ui` section at all.** Sprint 1.7 added `UIConfig` to `AppConfig` but the loader's dict-to-dataclass conversion was never updated, so it silently fell back to `UIConfig()`'s default every time regardless of what `defaults.yaml`/`local.yaml` actually said. Invisible in Sprint 1.7 because the default (3000) happened to match what was in `defaults.yaml`.
3. **Env-var overrides for `ui` fields (and any field whose section is entirely absent from the loaded YAML) silently failed to coerce**, staying as raw strings and crashing validation with a `TypeError`. The old coercion heuristic inferred the target type from whatever value was already loaded — with nothing loaded, it guessed `str`.

**Root cause, fixed once**: bugs 2 and 3 both stemmed from the same design flaw — three separate hardcoded lists (`AppConfig`'s dataclass fields, the old `_SECTION_NAMES` tuple, and `_dict_to_config`'s explicit kwargs) all had to be kept in sync by hand, and Sprint 1.7 only updated one of them. Rather than patch each symptom, consolidated to a single `_SECTION_SCHEMAS: dict[str, type]` mapping that both `_dict_to_config()` and `_apply_env_overrides()` now derive from, and switched env-var type coercion to resolve the target type from the schema's own `typing.get_type_hints()` rather than inferring it from already-loaded data. A future new config section only needs adding to this one dict.

### Tests Added

6 in `test_settings_window.py` (field population, edit round-trip, UI-section round-trip, valid save calls `ConfigLoader.save()`, invalid save is rejected with a visible inline error, and a real-`ConfigLoader` persistence round-trip), 3 in `test_loader.py` (regression coverage for all three bugs above), 2 in `test_manager.py` (`config()`/`config_loader()` accessors), 2 in `test_main_window.py` (Settings menu exists; opening it pulls config/loader from Core Manager). 77/77 total passing, `ruff` clean.

Two additional PySide6-specific issues were caught and fixed only by driving the _real_ widgets (not mocks): a `QMenuBar.addMenu(str)` ownership-tracking quirk that deleted the menu's C++ object despite a live Python reference (fixed by constructing `QMenu(title, self)` explicitly and using the object-overload of `addMenu()`), and a `QWidget.isVisible()` test that only reflects reality once the widget's whole ancestor chain is actually shown (fixed by calling `dialog.show()` in the relevant tests).

### Documentation Updated

This file (Sprint Completion Report). `docs/STATUS.md` Phase 1.3 row.

### Acceptance Criteria Checklist

- ✔ Changing a setting and clicking Save persists it to the config file.
- ✔ Restarting the app reflects the previously saved value — verified with a real simulated-restart script (`smoke_test_sprint_1_8.py`, scratchpad, not committed), which is what caught the three bugs above.
- ✔ An invalid value is rejected with a visible error and not written to disk.

### Remaining Risks

None blocking. The YAML-comment-loss-on-save limitation (flagged since Sprint 1.2) is now user-visible for the first time via this dialog, exactly as anticipated in this sprint's own Potential Risks — not a new issue.

### Technical Debt

None introduced. Three pre-existing bugs were fixed, not deferred.

### Recommendations for Sprint 1.9

- Debug Console should follow the same "drive the real widget, not just qtbot + mocks" verification discipline — this sprint is strong evidence that mocked `CoreManager`/`ConfigLoader` tests alone miss real integration bugs.
- No changes anticipated to `CoreManager`'s or `ConfigLoader`'s public API.
