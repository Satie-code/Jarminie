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

- [x] `max_instances=1` isolation test per job (13 — 1 already covered at Sprint 6.14 in this exact shape, ProactiveAssistant; 12 new tests added this sprint).
- [x] Shutdown-discipline confirmation per thread (8 — 6 already correct/disclosed, 1 fixed, 1 new narrower finding logged to `backlog/technical_debt.md`).
- [x] Full project suite re-run (per-tier, given the thread-accumulation history — see Sprint Completion Report).

## Documentation Checklist

- [x] `docs/STATUS.md` — narrative describing the full inventory and audit outcome.
- [x] `docs/sprint_book/INDEX.md` — 6.17 row → `Complete`.
- [x] `docs/backlog/technical_debt.md` — item 50 marked resolved (root cause + fix); new item 51 (the one interval-review-adjacent finding sized beyond this sprint's own scope, `ui/app.py`'s warm-up/shutdown race).

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

## Sprint Completion Report (2026-08-14)

Implemented as specified, authorized directly ("continue with sprint 6.17") immediately after Sprint 6.16. Built a real, concrete inventory directly from the current codebase (grep-confirmed, not assumed) matching this sprint file's own Engineering Rationale exactly: 13 `TaskScheduler` jobs (`scheduler/reminder_engine.py`'s `_poll_due_items`; `voice/pipeline.py`'s 4 maintenance jobs, `_check_and_announce_priority_item`, 3 guarded Level 5 Part B jobs, `_run_runtime_housekeeping`; `analytics/usage_tracker.py`/`wellness/wellness_tracker.py`/`proactive/proactive_assistant.py`'s own `_on_tick`s) and 8 raw daemon threads (`voice/session_manager.py` ×2, `voice/wake_word.py`, `ui/app.py`, `presentation/minie_renderer.py`, `presentation/vtube_studio_renderer.py`, `presentation/lip_sync.py`, `device_control/window_manager.py`).

**Objective 1 (job isolation) — implemented.** `scheduler/task_scheduler.py`'s `TaskScheduler.add_job()` now passes `max_instances=1` explicitly to APScheduler's own `add_job()` call (APScheduler's own default was already 1 — this closes the "implicit dependency on an unstated library default" gap the sprint's own Engineering Rationale named, changing no observed behavior). 12 new regression tests added, one per not-yet-individually-verified job (Sprint 6.14 already verified `ProactiveAssistant._on_tick` in this exact shape), mirroring that sprint's own established real-double-raises pattern: `tests/unit/scheduler/test_reminder_engine.py` (1), `tests/unit/memory/test_lifecycle_manager.py` (2, `run_cleanup_pass`/`run_monthly_review`), `tests/unit/voice/test_conversation_store.py` (1), `tests/unit/device_control/test_action_log.py` (1), `tests/unit/wellness/test_wellness_tracker.py` (1), `tests/unit/analytics/test_usage_tracker.py` (1), `tests/unit/voice/test_pipeline.py` (5 — 4 parametrized `CommunicationPipeline`-owned jobs sharing this file's own already-established faulty-collaborator technique from its `_check_and_announce_priority_item` sweep test, plus `pattern_recognizer.run_detection_pass` separately). **A real, disclosed split found while building these**: five of the twelve jobs (`_poll_due_items` via `CalendarStore.list_due_within()`, both purge jobs) already swallow their own underlying failures internally (Sprint 2.14/3.13-era hardening) and never actually propagate an exception to `TaskScheduler` at all — for these, the meaningful test proves the real, registered callable keeps recurring on schedule despite a persistently failing real collaborator, not merely that one direct call degrades gracefully (which existing tests already proved); the other seven (including `MemoryLifecycleManager`'s two jobs, whose outer `store.recent()` iteration has no such guard) genuinely propagate, matching Sprint 6.14's own precedent shape directly. 299/299 passing in a targeted run of every touched file plus its neighbors.

**Objective 2 (shutdown discipline) — one genuine, previously-undisclosed gap found and fixed; the other 7 threads confirmed already correct or already-disclosed.** `voice/session_manager.py`'s `VoiceSessionManager.stop()` joined its own `_watchdog_thread` (bounded timeout) but never joined `_listen_thread` at all — asymmetric with its own sibling since this class's Sprint 2.5 origin. Root-caused as the direct cause of `backlog/technical_debt.md` item 50's own real, measured 1750+-thread full-suite finding (`voice_session_manager` is a real registered `CoreManager` module; `CoreManager.shutdown()` calls this `stop()` on every one of the many `app_harness`-style fixture teardowns a combined-tier run performs). Fixed with a bounded `_listen_thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)` in `stop()`, called after `end_session()` — never inside `end_session()` itself, which can run ON the listener thread (a same-thread self-join risk). The remaining 7: `voice/session_manager.py`'s own watchdog thread and `voice/wake_word.py`'s listener thread already join correctly with a bounded timeout (the latter also logging an error if the timeout is exceeded); `presentation/lip_sync.py`'s driver thread, `presentation/minie_renderer.py`'s mount thread, and `presentation/vtube_studio_renderer.py`'s reconnect thread are all genuinely bounded, fire-and-forget-by-design, single-flight-guarded where relevant, with already-documented reasoning in their own docstrings; `device_control/window_manager.py`'s bounded native-call thread was already an explicitly-disclosed, accepted "abandoned if it hangs" limitation per this sprint's own Objectives text, not re-litigated. **One further genuine, narrower finding, logged rather than fixed**: `ui/app.py`'s `run_app()` starts its Tier WARM/COLD warm-up on a fire-and-forget daemon thread with no reference kept and never joined — if the app is closed quickly enough that `CoreManager.shutdown()` runs while that thread is still mid-`startup_tier()`, `_start_module()`/`_stop_module()` can race on shared `ModuleRegistry` state. Real, but a data race, not a hang a bounded `join()` fixes — either fix (waiting for warm-up to finish first, or a real cancellation token) is genuinely new mechanism, not a same-file hardening fix, and no real occurrence has ever been observed — logged as `backlog/technical_debt.md` item 51 per this sprint's own Potential Risks guidance ("if the minimal fix isn't safely containable... log to backlog rather than force it").

**The fix was verified with real, timed numbers, not assumed correct from code inspection alone.** `tests/integration/` + `tests/system/` (107 tests) together in ONE process, post-fix: completed in **471.02s (7m51s)** — 102 passed, 4 skipped, 1 failed (`test_context_analyzer_extracts_a_nonempty_topic_for_real_input`, the already-long-documented pre-existing real-Ollama-nondeterminism flake in `decision/context_analyzer.py`, a file this sprint never touches), with steady, healthy progress throughout — never once collapsing toward the near-standstill (3% in ~50 minutes, then stalled) item 50's own original finding described. **An honest residual, not swept under the rug**: live thread count (sampled repeatedly via `Get-Process` through the run) still climbed substantially — into the low thousands by the run's own end — a real, if narrower and non-catastrophic, observation investigated and root-caused to a second contributor: `VoiceSessionManager._listen_thread` is overwritten (not accumulated) on every new `begin_session()`, so a test exercising several conversation turns before its own final teardown only ever has its LAST session's own listener thread joined — every earlier turn's own now-superseded listener thread was signalled to stop but never explicitly confirmed to have exited (it does, empirically, near-instantly against this suite's own non-blocking fake `AudioBackend`s — but that's an observation, not a build-time guarantee). Logged as `backlog/technical_debt.md` item 52, deliberately not fixed — no real, observed harm (the re-verification run above completed cleanly and quickly), matching this project's own repeated "don't harden speculatively absent a demonstrated need" discipline. The property that actually matters — a real, complete, healthy full run rather than a multi-hour stall — is genuinely restored.

**Objective 3 (unnecessary polling) — reviewed, no change made.** Every one of the 13 jobs' real configured interval default (`config/schema.py`) already carries its own written rationale, confirmed by reading each docstring directly rather than assumed: `poll_interval_seconds` (30s, `ReminderEngine`/priority-item announcement), `maintenance_interval_seconds` (3600s, the 4 purge/cleanup jobs — "deliberately a much longer default than `poll_interval_seconds`"), `sample_interval_seconds` (60s, `UsageTracker`), `idle_check_interval_seconds` (60s, `WellnessTracker`/wellness-prompt enqueue), `pattern_detection_interval_seconds`/`recommendation_generation_interval_seconds` (86400s each, explicitly reasoned as "neither needs to run often, the same reasoning `maintenance_interval_seconds`'s own [cadence]" already established), `evaluation_interval_seconds` (300s, `ProactiveAssistant` — "deliberately coarser than Wellness's own `idle_check_interval_seconds`"), `housekeeping_interval_seconds` (60s). No genuinely wasteful interval found — a real, disclosed "no change needed" outcome, not a skipped step, matching Sprint 6.16's own identical-shaped precedent for its own two audit objectives.

**Diagnostics-panel extension (Objectives, last bullet) — deliberately deferred, per this sprint's own explicit permission.** `ui/runtime_diagnostics_panel.py`'s `RuntimeDiagnosticsPanel` is constructed with only a `CoreManager` (`ui/main_window.py`'s one real call site) and `CoreManager` exposes no accessor for a registered module's own live instance (only `module_states()`/`runtime_manager()`) — reading `TaskScheduler`'s own job list from this panel would need a new `CoreManager` accessor (a second production file beyond this sprint's own narrow Files to Modify) plus `MainWindow`/test-harness wiring, not "a small addition to `ui/runtime_diagnostics_panel.py` only" as hoped. Per this sprint's own Objectives text ("pursued only if it fits cleanly... if it doesn't fit cleanly once the audit itself is done, it is deferred, not forced in to satisfy a stretch objective") and Potential Risks, deliberately not built.

**Full-suite verification, per-tier (given item 50's own history)**: `tests/unit/` — **2248 passed, 1 skipped, zero failures, in 126.52s (2m6s)**. `tests/integration/` + `tests/system/` together — see the Objective 2 paragraph above (102 passed, 4 skipped, 1 pre-existing unrelated flake, in 471.02s/7m51s). `ruff check .` — clean, repository-wide.

`docs/STATUS.md` (this sprint's own narrative; Part B's own phase-status table row updated to `Developing (6.16–6.17 Complete)`), `docs/sprint_book/INDEX.md` (6.17 row → `Complete`), `docs/backlog/technical_debt.md` (item 50 marked resolved; new items 51/52) all updated.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Level 6 Part A's and Sprint 6.16's own still-uncommitted work. **Sprint 6.18 (Stress & Recovery Testing) is next.**
