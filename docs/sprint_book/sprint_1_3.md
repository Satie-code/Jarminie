# Sprint 1.3 — Logging System

## Sprint ID

1.3

## Sprint Name

Logging System

## Purpose

Give every subsystem structured, consistent logging per the Logging Strategy in [03_Engineering_Standards.md](../03_Engineering_Standards.md): levels DEBUG–CRITICAL, each entry carrying timestamp + subsystem + severity + message, with sensitive personal information never logged.

## Objectives

- One call (`get_logger(name)`) gives any module a correctly configured logger — no subsystem builds its own handlers.
- Output goes to both console and a rotating file under `logs/`.
- Log level and destination are driven by `LoggingConfig` from Sprint 1.2, not hardcoded.
- Provide a redaction mechanism so conversation content / credentials can't accidentally end up in a log line.

## Engineering Rationale

Every subsystem from Sprint 1.4 onward needs to log. Building this now, second, means Health Monitor and Core Manager (1.4–1.5) can use real logging from day one instead of `print()` placeholders that would need retrofitting. It depends on Configuration (1.2) for its own settings, which is exactly the dependency direction Part 3's DI rule expects.

## Prerequisites

Sprint 1.2 (Configuration Manager) complete — `LoggingConfig` exists.

## Dependencies

1.2

## Files to Create

- `core/logging_setup.py` — `configure_logging()`, `get_logger()`, `JarminieLogFormatter`, `SensitiveDataFilter`.
- `tests/unit/core/test_logging_setup.py`

## Files to Modify

None outside `core/logging_setup.py` — this sprint is additive.

## Expected Classes

- `JarminieLogFormatter(logging.Formatter)` — enforces `timestamp | subsystem | LEVEL | message` output format.
- `SensitiveDataFilter(logging.Filter)` — strips/redacts fields flagged as sensitive (e.g. anything logged under a `sensitive=True` extra) before a record is emitted.

## Expected Interfaces

None new. Python's standard `logging` module is the abstraction layer already; introducing a custom logging interface on top would be unjustified complexity for a single implementation (explicitly a YAGNI call, not an oversight).

## Expected Functions

- `configure_logging(config: LoggingConfig) -> None` — called once at startup by `main.py` (Sprint 1.6); sets up root handlers (console + rotating file).
- `get_logger(name: str) -> logging.Logger` — thin wrapper every module calls as `get_logger(__name__)`.

## Implementation Tasks

1. Implement `JarminieLogFormatter` producing the required format.
2. Implement `SensitiveDataFilter`.
3. Implement `configure_logging()`: root logger at `config.level`, a `RotatingFileHandler` (`config.log_dir/jarminei.log`, `config.max_bytes`, `config.backup_count`) with `delay=True` (avoids locking the file before first write, a known Windows `RotatingFileHandler` gotcha), and a `StreamHandler` for console.
4. Implement `get_logger()`.
5. Unit tests: format correctness, level filtering, rotation triggers at configured size (use a tiny `max_bytes` in the test), sensitive-field redaction.

## Architecture Notes

`configure_logging()` is called exactly once, at process start, before any other subsystem is constructed — mirrors how `logging.basicConfig` is conventionally used, but centralized here so the _format_ and _redaction_ policy is enforced project-wide rather than left to each caller's discretion. Every other subsystem only ever calls `get_logger(__name__)`, never touches handlers directly (Single Responsibility: this module owns "how logs look and where they go"; nothing else does).

## Potential Risks

- **Windows file locking** on the rotating log file if multiple processes run JARMINEI at once — out of scope for v1 (single-user, single-instance assumption), but worth a one-line comment in code so it's not mistaken for an oversight later.
- **Redaction is allow-list by convention, not enforced by the type system** — a developer must remember to mark sensitive data with the `sensitive=True` extra; nothing currently stops a raw `logger.info(user_message)` from leaking content. Documented here as a known limitation, not silently accepted — worth a lint rule or code-review checklist item in a later sprint if this proves error-prone in practice.

## Acceptance Criteria

- `get_logger("test")` returns a logger that writes correctly formatted lines to both console and `logs/jarminei.log`.
- Log level respects `LoggingConfig.level` (e.g. DEBUG suppressed when level is INFO).
- A record logged with `sensitive=True` does not appear verbatim in the file output.
- File rotates once it exceeds the configured size.

## Testing Checklist

- [ ] Unit: format matches `timestamp | subsystem | LEVEL | message`.
- [ ] Unit: level filtering (DEBUG suppressed at INFO level).
- [ ] Unit: rotation occurs at configured `max_bytes`.
- [ ] Unit: `SensitiveDataFilter` redacts flagged fields.
- [ ] Integration: `configure_logging()` + `get_logger()` used together end-to-end write a real file under a temp `logs/` dir.

## Documentation Checklist

- [ ] `core/logging_setup.py` module docstring: usage example (`logger = get_logger(__name__)`).
- [ ] Note the sensitive-data convention (`extra={"sensitive": True}`) in `docs/CODING_STANDARDS.md`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Low.

## Estimated Development Time

0.5 day.

## Next Sprint

1.4 — Health Monitor.

## Future Considerations

- Structured (JSON) log output for future log-aggregation tooling — not needed for a single local-first desktop app in v1; revisit only if a real need appears.

---

## Sprint Completion Report

### Summary

Implemented the Logging System: `configure_logging(LoggingConfig)` sets up a console handler and a rotating file handler on the root logger with a shared `timestamp | subsystem | LEVEL | message` format, plus a `SensitiveDataFilter` that redacts any record logged with `extra={"sensitive": True}`. `get_logger(name)` is the one entrypoint every future subsystem calls. Also updated `core/__init__.py` to export both, per the approved recommendation from Pass 1 review.

### Files Created

- `core/logging_setup.py` — `JarminieLogFormatter`, `SensitiveDataFilter`, `configure_logging()`, `get_logger()`.
- `tests/unit/core/test_logging_setup.py` (7 tests).

### Files Modified

- `core/__init__.py` — exports `configure_logging`, `get_logger` (approved improvement beyond the sprint doc's original scope, mirroring the `config/__init__.py` pattern from Sprint 1.2).

### Engineering Decisions

- **Filter attachment point**: `SensitiveDataFilter` is attached to each **handler**, not to the root logger's own filter list. Python's `Logger.filter()` only runs for records logged directly on that logger instance — a filter attached to the root _logger_ would not run for records originating from child loggers (e.g. `get_logger("core.manager")`) as they propagate upward; only handler-level filters see every propagated record. Verified via the manual smoke test using a non-root logger name (`get_logger("smoke_test")`), which redacted correctly.
- **Handler cleanup on reconfigure**: `configure_logging()` now explicitly calls `handler.close()` on every existing root handler before clearing them, not just `root.handlers.clear()`. Without this, repeated calls (which the test suite relies on for isolation) would leak open file handles.
- **`delay=True` on `RotatingFileHandler`**: avoids opening/locking the log file until the first actual write, sidestepping a known Windows file-locking gotcha, as flagged in the original sprint spec.
- **Defensive level fallback**: `getattr(logging, config.level, logging.INFO)` — `AppConfig.validate()` (Sprint 1.2) already guarantees a valid level by the time a real `AppConfig` reaches this function, but `configure_logging()` accepts a bare `LoggingConfig` slice per the DI design, so it doesn't assume the caller validated it.

### Tests Added

7 unit tests, all passing: format correctness, level filtering, sensitive-data redaction, rotation-triggers-backup-file, idempotency (no duplicate/leaked handlers across repeated calls), `get_logger` naming, invalid-level fallback. An `autouse` fixture resets and closes root logger handlers after every test to keep Windows file handles from leaking between tests.

### Documentation Updated

This file (Sprint Completion Report). `docs/STATUS.md` Phase 1.2 row updated.

### Acceptance Criteria Checklist

- ✔ `get_logger("test")` writes correctly formatted lines to both console and `logs/jarminei.log` (verified by unit test and a manual end-to-end smoke test wiring `load_config()` → `configure_logging()` → `get_logger()`).
- ✔ Log level respects `LoggingConfig.level`.
- ✔ A record logged with `sensitive=True` does not appear verbatim in file output.
- ✔ File rotates once it exceeds the configured size.

### Remaining Risks

None blocking. `ruff check .` clean; full suite (26/26, including Sprint 1.2's tests) passes.

### Technical Debt

None introduced. The redaction convention remains opt-in rather than type-enforced (already documented as an accepted limitation in the sprint spec, not new debt from this sprint).

### Recommendations for Sprint 1.4

- Health Monitor (Sprint 1.4) should log via `get_logger(__name__)` from the start rather than `print()`, now that a real logging system exists.
- No changes anticipated to `LoggingConfig` or `configure_logging()`'s signature.
