# Sprint 6.17 — Async Background Task Audit

## Sprint ID

6.17

## Sprint Name

Async Background Task Audit

## Purpose

Close Phase 6.1's own remaining half ("Background tasks should be asynchronous whenever possible... Avoid unnecessary polling," per [03_Engineering_Standards.md](../../03_Engineering_Standards.md)'s Performance Guidelines) with a real, complete inventory and audit of every recurring/background mechanism in the codebase — something that has never existed in one place before this sprint.

## Engineering Rationale

Six Levels of components have each independently registered their own recurring work against `scheduler/task_scheduler.py`'s `TaskScheduler` (a thin wrapper around one shared `apscheduler.schedulers.background.BackgroundScheduler` instance, first built at Sprint 4.15) or spawned their own raw `threading.Thread`, with no single sprint ever auditing the resulting whole. A real, concrete inventory, built directly from the current codebase rather than assumed: **13 distinct recurring `TaskScheduler` jobs** (`ReminderEngine._poll_due_items`, four `CommunicationPipeline`-owned maintenance/purge jobs, `_check_and_announce_priority_item`, three guarded Level 5 Part B jobs, `_run_runtime_housekeeping`, plus `UsageTracker`/`WellnessTracker`/`ProactiveAssistant`'s own self-registered ticks) and **8 raw daemon threads** (`voice/session_manager.py`'s watchdog and per-session listener, `voice/wake_word.py`'s listen loop, `ui/app.py`'s Tier B/C warm-up, `presentation/minie_renderer.py`'s avatar mount, `presentation/vtube_studio_renderer.py`'s reconnect, `presentation/lip_sync.py`'s driver, and `device_control/window_manager.py`'s bounded native-call thread). This sprint audits every one of them against three concrete questions, not a generic checklist: does one job/thread's own failure ever affect another's; does `CoreManager.shutdown()` actually stop each of them within a bounded time; is each one's own recurrence cadence genuinely necessary (not unnecessary polling).

## Objectives

- **Job isolation**: `TaskScheduler.add_job()` (`scheduler/task_scheduler.py`) currently relies entirely on APScheduler's own *implicit default* `max_instances=1` for per-job isolation — never passed explicitly. Sprint 6.14 verified this default holds for one job (`ProactiveAssistant._on_tick`) with a real always-raising double; this sprint passes `max_instances=1` explicitly in `add_job()` itself, closing the "implicit dependency on an unstated library default" gap directly, and re-verifies isolation for the remaining 12 jobs the same way 6.14 verified the one.
- **Shutdown discipline**: confirm `CoreManager.shutdown()` actually stops or bounds every one of the 8 raw threads within a documented timeout — most are already daemon threads with a documented shutdown story (`window_manager.py`'s own "abandoned, never cancelled, if it hangs" is an already-disclosed, accepted limitation, not a gap this sprint re-litigates); audit the remaining 7 for the same honesty, fixing only a genuine, previously-undisclosed hang risk.
- **Unnecessary polling**: review each of the 13 jobs' own configured interval against what it actually needs (per Phase 6.1's own literal "avoid unnecessary polling" text) — a documentation/config-default review, not a behavior change, unless a genuinely wasteful interval is found.
- Extend `ui/runtime_diagnostics_panel.py` (the Runtime Refactor's own Phase 10 diagnostics window, the one existing purpose-built surface for exactly this kind of visibility) with a read-only TaskScheduler job list (job id, interval, last-run time) — a natural, low-risk extension of an already-existing diagnostics surface, not new capability built from scratch; investigative, pursued only if it fits cleanly within this sprint's own scope once the audit itself is done.

## Dependencies

1.1–6.15; soft: 6.16 (shares audit methodology and touches some of the same startup-registration code — sequenced immediately after to avoid two sprints editing `main.py`'s registration functions on divergent assumptions).

## Files to Create

None expected, unless the diagnostics-panel extension (Objectives, last bullet) is pursued, in which case a small addition to `ui/runtime_diagnostics_panel.py` only (no new file).

## Files to Modify

- `scheduler/task_scheduler.py` (explicit `max_instances=1`)
- `core/manager.py` / relevant owning modules (`voice/session_manager.py`, `voice/wake_word.py`, `ui/app.py`, `presentation/minie_renderer.py`, `presentation/vtube_studio_renderer.py`, `presentation/lip_sync.py`) — only where the shutdown-discipline audit finds a genuine, fixable gap
- `ui/runtime_diagnostics_panel.py` (optional, per Objectives)

## Expected Classes

None new, unless the diagnostics extension is pursued (a small `SchedulerJobStatus` dataclass, `scheduler/task_scheduler.py`, exposing job id/interval/last-run for read-only display — never a control surface).

## Expected Functions

`TaskScheduler.list_jobs()` (optional, only if the diagnostics extension is pursued) — read-only, wraps APScheduler's own `get_jobs()`.

## Data Flow

Unchanged — this sprint audits and (where a genuine gap is found) hardens existing recurring mechanisms; it introduces no new flow of its own beyond the optional read-only diagnostics surface.

## Implementation Tasks

1. Add `max_instances=1` explicitly to `TaskScheduler.add_job()`'s own APScheduler call; confirm every one of the existing job-isolation tests (Sprint 4.19's five-job precedent, Sprint 6.14's `ProactiveAssistant` case) still passes unchanged.
2. For each of the 12 not-yet-individually-verified jobs, a lightweight real-double-raises test confirming isolation, mirroring 6.14's own established shape — not a full re-investigation, a mechanical extension of an already-proven pattern.
3. Shutdown-discipline audit of all 8 raw threads against `CoreManager.shutdown()`; fix only a genuine, previously-undisclosed unbounded-hang risk (a bounded `join(timeout=...)` matching `window_manager.py`'s own already-established precedent), document every thread's own actual shutdown behavior either way.
4. Interval review against each job's real purpose; flag (don't silently change) any interval that looks wasteful, since a default-value change ripples into every test/fixture assuming it — treat as a `backlog/technical_debt.md` candidate unless trivially safe to adjust.
5. Optional: `ui/runtime_diagnostics_panel.py` extension per Objectives, if it fits cleanly.

## Architecture Notes

`TaskScheduler` remains the one shared scheduling mechanism every recurring job goes through — this sprint doesn't introduce a second one, doesn't consolidate the 8 raw threads into it either (each of those exists specifically because it isn't interval-shaped work — a blocking audio stream, a bounded native call, a one-time warm-up), and doesn't build a general thread/job supervisor beyond the narrow, read-only diagnostics extension named in Objectives.

## Integration Considerations

- Sprint 6.18 (Stress & Recovery Testing) exercises this sprint's own audited job/thread inventory under real concurrent load — this sprint's own inventory and isolation-verification work is the map 6.18's stress scenarios are built against.
- Sprint 6.19 (Resource Protection & Fail-Gracefully Verification) is where this sprint's own inventory gets resource-pressure-awareness wired in (jobs pausing under CRITICAL resource readings) — this sprint only inventories and verifies isolation/shutdown, it does not add resource-awareness itself.

## Potential Risks

- **A genuine, previously-undisclosed thread-shutdown hang, if found, may need more than a bounded `join()` to fix safely** (e.g. a real cross-thread signal the target thread must itself check) — if the minimal fix isn't safely containable within this sprint's own scope, log to `backlog/technical_debt.md` rather than force it.
- **The diagnostics-panel extension is explicitly optional** — if it doesn't fit cleanly once the audit itself is done, it is deferred, not forced in to satisfy a stretch objective.

## Acceptance Criteria

- Every one of the 13 recurring jobs has an explicit `max_instances=1` and a real regression test proving isolation (a raising tick never kills the job's own future recurrence or any other job).
- Every one of the 8 raw threads has a documented, either-already-correct-or-now-fixed shutdown story — no previously-undisclosed unbounded hang risk remains unaddressed or unlogged.
- Full test suite (unit + integration + system, opt-in real-model marker excluded) passes with zero regressions.
- `ruff check .` clean.

## Testing Checklist

- [ ] `max_instances=1` isolation test per job (13, or a shared parametrized test where the shape allows).
- [ ] Shutdown-discipline confirmation per thread (8).
- [ ] Full project suite re-run.

## Documentation Checklist

- [ ] `docs/STATUS.md` — narrative describing the full inventory and audit outcome.
- [ ] `docs/sprint_book/INDEX.md` — 6.17 row → `Complete` (once implemented).
- [ ] `docs/backlog/technical_debt.md` — any interval-review or shutdown-risk finding sized beyond this sprint's own scope.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

6.18 — Stress & Recovery Testing.

## Future Considerations

- A genuine central thread/job supervisor (beyond the narrow, read-only diagnostics extension this sprint may add) is real future-shaped work, not built speculatively here — revisit only if the diagnostics extension proves insufficient for a real, later diagnostic need.
