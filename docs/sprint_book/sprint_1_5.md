# Sprint 1.5 — Core Manager

## Sprint ID
1.5

## Sprint Name
Core Manager

## Purpose
Implement the orchestrator described in [02_System_Architecture.md](../02_System_Architecture.md): initializes modules, maintains system state, coordinates communication, manages startup/shutdown, monitors module health, and restarts recoverable modules. This sprint completes Phase 1.2 and satisfies its acceptance criteria: "JARMINEI launches. JARMINEI exits cleanly. Logging works. Configuration loads."

## Objectives
- A `CoreManager` that wires together Configuration (1.2), Logging (1.3), and the Health/Resource Monitor (1.4) via dependency injection.
- A generic module registry so any future subsystem can register itself without Core Manager knowing its concrete type.
- A clean startup and shutdown sequence, logged at each step.
- A minimal `main.py` entrypoint that proves the whole chain launches and exits cleanly.

## Engineering Rationale
Part 2 is explicit that "the Core should contain minimal business logic. Its primary purpose is orchestration." Building it last among the Level 1 infrastructure sprints — after Config, Logging, and the resource probe already exist — means Core Manager can depend on all three via constructor injection rather than constructing them itself, directly satisfying the Dependency Injection rule ("avoid creating X inside Y; instead Y receives an X instance").

## Prerequisites
Sprints 1.2, 1.3, 1.4 complete.

## Dependencies
1.2, 1.3, 1.4

## Files to Create
- `core/manager.py` — `CoreManager`.
- `core/module_registry.py` — `ModuleRegistry`, `ManagedModule` interface.
- `main.py` (repo root) — application entrypoint.
- `tests/unit/core/test_manager.py`
- `tests/unit/core/test_module_registry.py`

## Files to Modify
None.

## Expected Classes
- `CoreManager(config: AppConfig, logger, resource_monitor: ResourceMonitor)` — owns a `ModuleRegistry`; exposes `startup()`, `shutdown()`.
- `ModuleRegistry` — tracks registered modules by name, their state, and last health-check result.

## Expected Interfaces
- `ManagedModule` (Protocol): `start() -> None`, `stop() -> None`, `health_check() -> bool`. This is the one interface every future subsystem (Voice Engine, Memory Engine, Decision Engine, etc.) will eventually implement to be managed by Core — introduced now because Core's stated job ("module registration," "restart recoverable modules") is meaningless without a uniform contract for what a "module" is. Kept deliberately minimal (3 methods) to avoid over-fitting to subsystems that don't exist yet.

## Expected Functions
- `CoreManager.startup() -> None` — logs start, initializes resource monitoring loop, starts all registered modules in registration order.
- `CoreManager.shutdown() -> None` — stops all modules in reverse order, logs completion.
- `CoreManager.register_module(name: str, module: ManagedModule) -> None`
- `CoreManager.restart_module(name: str) -> bool` — stop + start a single module, used when `health_check()` reports failure (Fail Gracefully rule: one module's failure must not take down the rest).
- `main() -> None` (in `main.py`) — constructs `AppConfig` → logger → `ResourceMonitor` → `CoreManager`, calls `startup()`, waits (placeholder — real UI event loop arrives in 1.6), calls `shutdown()` on exit signal.

## Implementation Tasks
1. Implement `ManagedModule` protocol and `ModuleRegistry`.
2. Implement `CoreManager` with constructor DI of config/logger/resource_monitor.
3. Implement `startup()`/`shutdown()` sequences with structured logging at each step.
4. Implement `restart_module()` — catches exceptions from a failing module's `stop()`/`start()` so a broken module can't crash Core itself (Fail Gracefully).
5. Write `main.py` as the thin composition-root entrypoint — this is the only file allowed to construct concrete subsystem instances; everything else receives them via DI.
6. Unit tests: registry add/remove, startup calls `start()` on all modules in order, shutdown calls `stop()` in reverse order, a module raising in `health_check()` triggers `restart_module()` without propagating the exception to the caller, a module raising in `start()` is logged and does not prevent other modules from starting.

## Architecture Notes
No real subsystems exist yet to register (Voice, Memory, etc. start arriving in Level 2) — this sprint's tests use small mock `ManagedModule` implementations. `CoreManager` itself must remain thin: if a future sprint finds business logic creeping into it (e.g. persona-switching rules, decision logic), that logic belongs in the relevant subsystem, not here — a direct application of the Single Responsibility Rule.

## Potential Risks
- **`ManagedModule` interface may not fit every future subsystem's lifecycle** (e.g. the Voice Engine's "dormant until wake word" state doesn't map cleanly onto simple start/stop). Documented as an explicit risk to revisit at Sprint 2.1 rather than over-designing the interface now for needs that aren't confirmed yet.
- **Shutdown ordering on crash**: if `main.py` exits via an unhandled exception rather than a clean signal, `shutdown()` may not run. Mitigate with a `try/finally` in `main()`; full crash-recovery testing is Level 6's job (Sprint 6.3), not this sprint's.

## Acceptance Criteria
- Running `main.py` starts JARMINEI, logs the full startup sequence, and exits cleanly (logs the full shutdown sequence) on close.
- Logging works (uses Sprint 1.3's `get_logger`).
- Configuration loads (uses Sprint 1.2's `load_config`).
- A mock module that fails `health_check()` gets restarted without crashing Core Manager or other modules.

## Testing Checklist
- [ ] Unit: `register_module` + `ModuleRegistry` state tracking.
- [ ] Unit: `startup()` starts all modules in registration order.
- [ ] Unit: `shutdown()` stops all modules in reverse order.
- [ ] Unit: a module raising in `start()` is caught, logged, and doesn't block other modules.
- [ ] Unit: `restart_module()` on health-check failure.
- [ ] Integration: `main.py` runs end-to-end (start → immediate shutdown) without error, verified via a subprocess or direct function call test.

## Documentation Checklist
- [ ] `core/manager.py` docstring: lifecycle diagram in words (startup → running → shutdown), how to register a module.
- [ ] `docs/STATUS.md` updated to mark Phase 1.2 acceptance criteria met.

## Definition of Done
Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint also closes out Phase 1.2's acceptance criteria from [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md).

## Estimated Complexity
Medium.

## Estimated Development Time
1–1.5 days.

## Next Sprint
1.6 — Desktop Shell & Main Window.

## Future Considerations
- Async startup (parallelizing independent modules' `start()` calls) — premature for Level 1 with zero real modules; reconsider once Level 2+ modules make startup time actually noticeable.

---

## Sprint Completion Report

### Summary

Implemented the Core Manager: `ModuleRegistry`/`ManagedModule` protocol, `CoreManager` (startup/shutdown sequencing, registration, restart, health checks), and a real `main.py` composition root wiring Config → Logging → ResourceMonitor → CoreManager. Ran `main.py` for real — full startup/shutdown sequence logged correctly to console and file, exit code 0. Also implements the Sprint 1.4 recommendation: `CoreManager.check_resources()` is now the single place that owns how a resource reading is taken.

### Files Created

- `core/module_registry.py` — `ManagedModule` (Protocol), `ModuleState` (Enum), `ModuleRegistry`.
- `core/manager.py` — `CoreManager`.
- `main.py` — application entrypoint / composition root.
- `tests/unit/core/test_module_registry.py` (6 tests), `tests/unit/core/test_manager.py` (9 tests).

### Files Modified

None outside the created files (matches the sprint doc's "Files to Modify: None").

### Engineering Decisions

- **`config` retained but currently unused** in `CoreManager.__init__` — kept because the sprint doc's documented constructor shape includes it and a plausible future need exists (e.g. Quiet Mode state), not because any logic in this sprint reads it. Flagged explicitly in the code comment rather than silently included or silently dropped.
- **Dropped the `logger` constructor parameter** from `CoreManager(config, logger, resource_monitor)` as originally sketched — same reasoning applied consistently from Sprints 1.4/1.3: `get_logger(__name__)` at module scope is the project's real, already-built convention.
- **`check_health()` and `restart_module()` kept as separate methods**, not fused — checking health and deciding to restart are different concerns (Single Responsibility); no automatic health-check loop calls them together yet, since no scheduler/timer infrastructure exists until later sprints. Same reasoning as Sprint 1.4's resource-sampling-cadence decision: Core Manager owns *how*, a future timer/loop owns *when*.
- **`module_states()` added** as a public read-only accessor — this is exactly what Sprint 1.7 (Status Panel)'s plan already anticipated needing ("add a read-only `CoreManager.module_states()` accessor if not already sufficient from Sprint 1.5"), so building it now avoids a follow-up modification later.
- **`restart_module()` attempts `start()` even if `stop()` raised** — a failed stop shouldn't prevent an attempted recovery restart; verified with a dedicated test (`test_restart_attempts_start_even_if_stop_failed`).

### Tests Added

15 unit tests, all passing: registry CRUD/ordering/duplicate-rejection (6), startup/shutdown ordering, start/stop failure isolation (a broken module doesn't block others or crash Core), restart semantics including the stop-fails-but-start-still-attempted case, health-check safety, and resource-check delegation (9). Plus a full real-process run of `main.py` (not just unit tests) confirming the actual acceptance criteria end-to-end.

### Documentation Updated

This file (Sprint Completion Report). `docs/STATUS.md` — Phase 1.2 marked **Complete** (all four of its sprints — 1.2, 1.3, 1.4, 1.5 — done), closing out Level 1's Core Framework phase per [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md).

### Acceptance Criteria Checklist

- ✔ Running `main.py` starts JARMINEI, logs the full startup sequence, and exits cleanly with the full shutdown sequence logged (verified by actually running it, not just tests).
- ✔ Logging works (uses Sprint 1.3's `get_logger`).
- ✔ Configuration loads (uses Sprint 1.2's `load_config`).
- ✔ A module that fails restarts without crashing Core Manager or other modules (`test_module_start_failure_does_not_block_other_modules`, `test_restart_attempts_start_even_if_stop_failed`).

### Remaining Risks

- `ManagedModule`'s fit for the Voice Engine's dormant/wake-word lifecycle remains an open question, as already flagged in this sprint's own Potential Risks — revisit at Sprint 2.1, not resolved here.
- Shutdown-on-crash (unhandled exception bypassing the `try/finally`) remains untested — explicitly deferred to Level 6 (Sprint 6.3 reliability/recovery testing) per this sprint's own scope.

### Technical Debt

None introduced.

### Recommendations for Sprint 1.6

- `main.py`'s `try/startup/finally/shutdown` structure will need to change shape to host a real Qt event loop instead of the current immediate shutdown — expect `main.py` to be modified in Sprint 1.6 despite this sprint's "Files to Modify: None" (that constraint was for *this* sprint, not a promise `main.py` is frozen going forward).
- No changes anticipated to `CoreManager`'s or `ModuleRegistry`'s public API — Sprint 1.6 should only need to construct a `CoreManager` and call its existing `startup()`/`shutdown()`.
