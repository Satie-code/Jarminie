# Sprint 1.2 — Configuration Manager

## Sprint ID
1.2

## Sprint Name
Configuration Manager

## Purpose
Give every future subsystem a single, typed way to read configurable values without any of them hardcoding wake phrases, intervals, thresholds, paths, or model names — the Configuration Management rule in [03_Engineering_Standards.md](../03_Engineering_Standards.md).

## Objectives
- Define a typed configuration schema covering every value Part 3 explicitly calls out as configurable (wake phrases, reminder intervals, voice selection, resource thresholds, database paths, model selection).
- Load configuration from a YAML file at startup, with environment-variable overrides.
- Provide a save path so later UI work (Sprint 1.8) can persist edits.
- Fail loudly and clearly on missing/invalid config rather than silently defaulting into a broken state.

## Engineering Rationale
This is the first "real" sprint after bootstrap, and everything downstream (Logging, Core Manager, every subsystem in Levels 2–5) will read its settings through this module. Building it first, before Logging, means Logging itself can be configured (level, output path) the same way as everything else — no special-cased bootstrapping. A typed schema (dataclasses) instead of raw dicts catches config typos at construction time instead of at some arbitrary point deep in a subsystem later.

## Prerequisites
Sprint 1.1 (Repository Bootstrap) complete — `config/` package exists.

## Dependencies
None (first functional sprint; nothing else exists yet to depend on).

## Files to Create
- `config/schema.py` — typed config dataclasses.
- `config/loader.py` — `ConfigLoader` and the `ConfigSource` interface.
- `config/defaults.yaml` — default values, safe to run out of the box.
- `tests/unit/config/test_loader.py`
- `tests/unit/config/test_schema.py`

## Files to Modify
- `config/__init__.py` — export `AppConfig`, `ConfigLoader`, `load_config`.

## Expected Classes
- `AppConfig` (dataclass) — root config object: `voice: VoiceConfig`, `resources: ResourceThresholds`, `database: DatabaseConfig`, `models: ModelConfig`, `logging: LoggingConfig`.
- `VoiceConfig` (dataclass) — wake phrase(s), voice selection defaults.
- `ResourceThresholds` (dataclass) — CPU/RAM/battery/disk warning and critical percentages.
- `DatabaseConfig` (dataclass) — SQLite path, ChromaDB persistence path.
- `ModelConfig` (dataclass) — Ollama model name, Whisper model size.
- `LoggingConfig` (dataclass) — level, log directory, max file size/backup count.
- `ConfigLoader` — orchestrates load/validate/merge/save.

## Expected Interfaces
- `ConfigSource` (Protocol): `read() -> dict`. One concrete implementation this sprint (`YamlFileConfigSource`); kept as an interface because dev/prod environments plausibly need an env-var-only source later (Part 3's Interface First Design rule) — not because a second source is needed today.

## Expected Functions
- `load_config(path: Path | None = None) -> AppConfig` — module-level convenience wrapper.
- `ConfigLoader.load() -> AppConfig`
- `ConfigLoader.save(config: AppConfig) -> None`
- `ConfigLoader._apply_env_overrides(raw: dict) -> dict`
- `AppConfig.validate(self) -> None` — raises `ConfigError` with a specific, actionable message.

## Implementation Tasks
1. Write `defaults.yaml` covering every field in the schema.
2. Implement dataclasses in `schema.py` with type hints and inline field docs.
3. Implement `YamlFileConfigSource` and `ConfigLoader.load()`: read YAML → apply env overrides (`JARMINEI_<SECTION>_<FIELD>`) → construct `AppConfig` → validate.
4. Implement `ConfigLoader.save()` serializing an `AppConfig` back to YAML, preserving comments is out of scope (acceptable loss, noted below).
5. Define `ConfigError` (in `config/schema.py` or a new `config/errors.py`) for all config-layer failures.
6. Unit tests: successful load, missing file, malformed YAML, invalid value (e.g. negative threshold), env override precedence, round-trip save→load.

## Architecture Notes
`ConfigLoader` is only ever invoked once, at the application entrypoint (`main.py`, created in Sprint 1.6) — no subsystem calls `load_config()` itself. Every subsystem receives its relevant config slice (e.g. `VoiceConfig`, not the whole `AppConfig`) through its constructor per the Dependency Injection rule. This keeps subsystems ignorant of where config comes from and easy to unit test with a hand-built config object.

## Potential Risks
- **Schema growth**: `AppConfig` will gain a new nested dataclass roughly once per Level as new subsystems arrive (voice in 2.x, memory in 3.x, etc.). Mitigate by keeping each subsystem's config in its own nested dataclass with a clear comment on which sprint/subsystem owns it, rather than a flat namespace.
- **YAML round-trip losing comments** on `save()`: acceptable for now since Sprint 1.8 (Settings Window) is the only writer and it edits discrete fields, not prose; revisit if a human is expected to hand-edit `config.yaml` directly and expects their comments preserved.

## Acceptance Criteria
- Application loads `AppConfig` from `config/defaults.yaml` (or a user override path) with zero errors on a clean checkout.
- A missing config file produces a clear, logged, non-crashing error at the call site (exact behavior — raise `ConfigError`, caller decides whether to fall back to defaults or abort).
- An environment variable override changes the loaded value; verified in a test.
- No file outside `config/` contains a hardcoded value that belongs in the schema.

## Testing Checklist
- [ ] Unit: successful load from defaults.
- [ ] Unit: missing file raises `ConfigError`.
- [ ] Unit: malformed YAML raises `ConfigError` with a useful message.
- [ ] Unit: invalid field value (e.g. threshold > 100%) raises `ConfigError` at validation.
- [ ] Unit: env override takes precedence over file value.
- [ ] Unit: save → load round-trip preserves all fields.

## Documentation Checklist
- [ ] `config/__init__.py` docstring updated with usage example.
- [ ] `docs/CODING_STANDARDS.md` — no change expected, confirm still accurate.
- [ ] This sprint file's Sprint Completion Report filled in once implemented.

## Definition of Done
Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md): implementation complete, unit tests pass, docs updated, `ruff check .` clean, no critical issues, architecture respected (DI, interface-first, no hardcoded values).

## Estimated Complexity
Low–Medium.

## Estimated Development Time
0.5–1 day.

## Next Sprint
1.3 — Logging System.

## Future Considerations
- A `ConfigWatcher` for hot-reload (change a setting without restarting JARMINEI) is explicitly out of scope for Level 1 — flag as a Level 6 performance/UX candidate, not a v1 requirement per the spec.

---

## Sprint Completion Report

### Summary

Implemented the Configuration Manager: a typed `AppConfig` schema, a `ConfigLoader` that merges `config/defaults.yaml` (checked in) → optional `config/local.yaml` (gitignored, machine-specific) → `JARMINEI_<SECTION>_<FIELD>` environment overrides, and `AppConfig.validate()` for fail-loudly validation. This was approved with the `local.yaml` overlay improvement proposed during Pass 1 review, beyond the sprint file's original minimum scope.

### Files Created

- `config/errors.py` — `ConfigError`.
- `config/schema.py` — `AppConfig`, `VoiceConfig`, `ResourceThresholds`, `DatabaseConfig`, `ModelConfig`, `LoggingConfig`, `AppConfig.validate()`.
- `config/loader.py` — `ConfigSource` protocol, `YamlFileConfigSource`, `ConfigLoader`, `load_config()`.
- `config/defaults.yaml` — shipped defaults.
- `tests/unit/config/test_schema.py` (10 tests), `tests/unit/config/test_loader.py` (9 tests).

### Files Modified

- `config/__init__.py` — exports the public API.
- `requirements.txt` — added `pyyaml>=6.0`.

### Engineering Decisions

- **`config/local.yaml` overlay** (approved during Pass 1 review): closes a gap left open since Sprint 1.1, whose `.gitignore` already reserved `config/local.*` for machine-specific overrides that nothing used yet. `ConfigLoader.save()` now targets this overlay by default — it never writes to `defaults.yaml`, which stays a checked-in, app-immutable baseline.
- **Battery threshold direction**: unlike CPU/RAM/disk (where *higher* usage is worse, so critical > warning), battery is inverted — *lower* charge is worse, so `battery_critical_percent` must be lower than `battery_warning_percent`. `AppConfig._validate_resources()` handles this as an explicit special case rather than a uniform rule, to avoid a subtle validation bug.
- **Env-var type coercion** is derived from the type already present after the YAML layers merge (int/float/bool/list/str), rather than a string-guessing heuristic — more precise and simpler to reason about than pattern-matching the raw string.
- **`ConfigLoader.save()`** gained an optional `path` parameter beyond the sprint doc's literal `save(config: AppConfig) -> None` signature, defaulting to the local overlay — kept backward-compatible with the documented call shape while supporting the overlay design.

### Tests Added

19 unit tests, all passing: 10 in `test_schema.py` (default validity, each validation rule's failure case, the battery-inversion rule specifically), 9 in `test_loader.py` (successful load, missing file, malformed YAML, invalid field surfaced through the loader, env override precedence, env type coercion, local overlay merge, env-over-local precedence, save/reload round-trip).

### Documentation Updated

This file (Sprint Completion Report). `docs/STATUS.md` Phase 1.2 row updated to reflect Sprint 1.2 progress.

### Acceptance Criteria Checklist

- ✔ Application loads `AppConfig` from `config/defaults.yaml` with zero errors on a clean checkout (verified via `pytest` and a manual `load_config()` smoke test).
- ✔ Missing config file raises `ConfigError` with a clear message, not a crash.
- ✔ Environment variable override changes the loaded value (verified, including type coercion and precedence over the local overlay).
- ✔ No file outside `config/` contains a hardcoded value belonging to the schema (nothing outside `config/` reads config yet — trivially satisfied this sprint, worth re-checking once Sprint 1.5 wires `main.py` to it).

### Remaining Risks

None blocking. `ruff check .` clean; full test suite (19/19) passes.

### Technical Debt

None introduced. The already-tracked schema-growth and YAML-comment-loss-on-save risks (see Potential Risks above) remain open by design, not by omission.

### Recommendations for Sprint 1.3

- Logging System (Sprint 1.3) should consume `AppConfig.logging` exactly as designed here — no changes to this sprint's schema anticipated.
- When Sprint 1.5 (Core Manager) writes `main.py`, confirm the "no hardcoded values outside `config/`" criterion holds project-wide, not just within this sprint's own files.
