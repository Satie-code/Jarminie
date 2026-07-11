# Sprint 1.4 — Health Monitor (Resource Probe)

## Sprint ID
1.4

## Sprint Name
Health Monitor (Resource Probe)

## Purpose
Build the raw resource-monitoring capability behind the Resource Protection rule in [02_System_Architecture.md](../02_System_Architecture.md): continuously sample CPU/RAM/Storage/Battery and flag threshold breaches, so JARMINEI can throttle itself before the user's system becomes unresponsive.

## Objectives
- Sample system resource usage on a configurable interval without busy-polling.
- Compare samples against `ResourceThresholds` (from Sprint 1.2) and expose a clear over-threshold signal.
- Keep this module a pure probe — it reports; it does not itself decide what to throttle (that belongs to Core Manager / whichever subsystem is consuming resources, in later sprints).

## Engineering Rationale
Part 2 states resource protection must ensure "the user should never experience degraded usability because of JARMINEI" — that starts with being able to *measure* usage accurately. Building this as an isolated, single-responsibility probe (rather than folding it into Core Manager) keeps it independently testable with mocked `psutil` values and reusable later by the Status Panel (Sprint 1.7) and the full System Monitoring sprint (4.4), which extends this into throttling decisions.

## Prerequisites
Sprint 1.2 (Configuration Manager) complete — `ResourceThresholds` exists.

## Dependencies
1.2

## Files to Create
- `core/resource_monitor.py` — `ResourceMonitor`, `ResourceSnapshot`.
- `tests/unit/core/test_resource_monitor.py`

## Files to Modify
None.

## Expected Classes
- `ResourceSnapshot` (dataclass) — `cpu_percent`, `ram_percent`, `disk_percent`, `battery_percent: float | None`, `timestamp: datetime`.
- `ResourceMonitor` — `__init__(thresholds: ResourceThresholds, logger)`; wraps `psutil` calls.

## Expected Interfaces
None new. `psutil` is the only implementation needed; no swap-need identified (single target platform: Windows, per spec scope) — introducing an abstraction here would be premature per the anti-overengineering guidance, not a Part 3 requirement.

## Expected Functions
- `ResourceMonitor.sample() -> ResourceSnapshot`
- `ResourceMonitor.is_over_threshold(snapshot: ResourceSnapshot) -> bool`
- `ResourceMonitor.breached_resources(snapshot: ResourceSnapshot) -> list[str]` — which specific resource(s) breached, for explainability (Part 2's Explainability Rule — "why is JARMINEI throttling?" needs a concrete answer).

## Implementation Tasks
1. Implement `ResourceSnapshot`.
2. Implement `ResourceMonitor.sample()` using `psutil.cpu_percent()`, `psutil.virtual_memory()`, `psutil.disk_usage()`, `psutil.sensors_battery()` (may be `None` on desktops without a battery — handle gracefully).
3. Implement threshold comparison functions.
4. Unit tests using `unittest.mock.patch` on `psutil` calls to simulate normal and over-threshold readings, and a missing-battery case.

## Architecture Notes
No GPU monitoring in this sprint — `psutil` has no built-in GPU support (see Potential Risks). `ResourceMonitor` samples on-demand (`sample()` called by whoever needs a reading — Core Manager on a timer in 1.5, Status Panel on a UI timer in 1.7) rather than running its own background thread; this avoids the "unnecessary polling" pitfall Part 3 warns about and lets each caller choose its own cadence.

## Potential Risks
- **No GPU metric**: Part 2 explicitly lists GPU under Resource Protection, but `psutil` doesn't expose it. Flagged as a known limitation, not silently dropped — a future sprint could add optional `pynvml`/`wmi`-based GPU sampling if it proves necessary; not blocking for v1's CPU-bound workloads.
- **Battery-less desktops**: `psutil.sensors_battery()` returns `None` on desktop PCs — `ResourceSnapshot.battery_percent` must tolerate `None` throughout, including in the threshold check (skip, don't crash).

## Acceptance Criteria
- `sample()` returns a fully populated snapshot on this machine.
- `is_over_threshold()` correctly flags a breach against mocked over-threshold values in tests.
- `battery_percent = None` does not raise in any code path.

## Testing Checklist
- [ ] Unit: `sample()` returns expected fields with real `psutil` (smoke test).
- [ ] Unit: `is_over_threshold()` true when a mocked CPU/RAM/disk value exceeds the configured threshold.
- [ ] Unit: `is_over_threshold()` false when all values are under threshold.
- [ ] Unit: battery `None` handled without exception.
- [ ] Unit: `breached_resources()` names exactly the breaching resource(s).

## Documentation Checklist
- [ ] `core/resource_monitor.py` docstring documents the no-GPU limitation explicitly.

## Definition of Done
Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity
Low–Medium.

## Estimated Development Time
0.5 day.

## Next Sprint
1.5 — Core Manager.

## Future Considerations
- GPU monitoring (optional dependency) — candidate for Level 6 Performance hardening if GPU-bound work (e.g. local model inference) makes it relevant.

---

## Sprint Completion Report

### Summary

Implemented the Health Monitor resource probe: `ResourceMonitor.sample()` reads CPU/RAM/disk/battery via `psutil`, and `breached_resources()`/`is_over_threshold()` compare a snapshot against `ResourceThresholds` (Sprint 1.2). Verified end-to-end against real hardware, not just mocks — it correctly flagged genuine RAM/disk threshold breaches on the dev machine.

### Files Created

- `core/resource_monitor.py` — `ResourceSnapshot`, `ResourceMonitor`.
- `tests/unit/core/test_resource_monitor.py` (9 tests).

### Files Modified

- `requirements.txt` — moved `psutil` from the Phase 4.1 group to its own Sprint 1.4 entry; it's needed now, not just when Device Control's full System Monitoring work arrives.

### Engineering Decisions

- **Logger via module-level `get_logger(__name__)`**, not a constructor-injected `logger` parameter as this sprint file originally sketched (`__init__(thresholds, logger)`) — that wording predated Sprint 1.3's actual implementation, which established `get_logger(__name__)` at module scope as the real project-wide convention (every subsystem calls `get_logger(__name__)`; nothing touches handlers directly). Followed the convention that was actually built rather than the earlier speculative draft, for consistency with `config`/`core.logging_setup`.
- **Disk path**: samples `Path.cwd().anchor` (e.g. `C:\`) rather than psutil's `/` shorthand — verified both resolve identically on this Windows machine, but the explicit drive anchor is self-documenting about which drive is measured (wherever JARMINEI is actually running from) rather than relying on psutil's implicit path normalization.
- **First-sample CPU quirk documented, not hidden**: `psutil.cpu_percent()` always returns 0.0 on the first call in a process (it compares against the prior call); noted in `sample()`'s docstring rather than working around it with a blocking `interval=` call, which would hurt responsiveness for no real benefit given `sample()` is meant to be called repeatedly on a timer by future callers (Status Panel in 1.7, Core Manager in 1.5).

### Tests Added

9 unit tests, all passing: populated snapshot (mocked psutil), missing-battery handling, no-breach case, individual cpu/ram/disk breach detection, inverted battery-breach direction, `None` battery not falsely breaching, multiple simultaneous breaches. Plus a manual smoke test against real hardware (see Summary).

### Documentation Updated

This file (Sprint Completion Report). `docs/STATUS.md` Phase 1.2 row updated.

### Acceptance Criteria Checklist

- ✔ `sample()` returns a fully populated snapshot on this machine (verified with both mocked tests and a real smoke test).
- ✔ `is_over_threshold()` correctly flags a breach against mocked over-threshold values.
- ✔ `battery_percent = None` does not raise in any code path (dedicated test).

### Remaining Risks

None blocking. No-GPU limitation remains documented, not resolved (matches the sprint's own Future Considerations — deferred to Level 6 if it ever matters).

### Technical Debt

None introduced.

### Recommendations for Sprint 1.5

- Core Manager should own the sampling cadence (call `ResourceMonitor.sample()` on a timer) rather than any other subsystem — keeps "who decides how often to check" in one place.
- No changes anticipated to `ResourceMonitor`'s public API.
