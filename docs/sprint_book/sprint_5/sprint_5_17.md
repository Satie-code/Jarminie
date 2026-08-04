# Sprint 5.17 — Usage & Habit Tracking

## Sprint ID

5.17

## Sprint Name

Usage & Habit Tracking

## Purpose

Give the Analytics Engine its foundational data-collection layer — per `02_System_Architecture.md`'s Analytics Engine section ("Tracks: Productivity, Habit consistency, Project progress, Focus sessions, Screen time, Application usage") and `04_Master_Implementation_Plan.md`'s Phase 5.3 ("Habit tracking. Project tracking. Focus tracking. Application usage."). This is the first sprint of Level 5 Part B by real build order (see `docs/sprint_book/INDEX.md`'s "Level 5 Part B breakdown changes" note for why it is renumbered ahead of the roadmap-granularity Wellness sprints) — storage and raw sampling only, no aggregation (Sprint 5.20) and no learning (Sprint 5.21).

## Engineering Rationale

Corresponds to the roadmap-granularity `Usage & Habit Tracking` entry (originally numbered `5.20`, Phase 5.3) — expanded to full detail now that Part A (Sprints 5.1–5.16) is frozen, matching this project's own "expand when current" practice. Reordered to `5.17`, the first sprint actually built in this Part, because `5.21` (Pattern Recognition, Learning phase) and `5.20`→`5.20`(Analytics Dashboard Data) both structurally require this sprint's own stored data before either can produce anything real — the same "keep dependency references pointing only at earlier-numbered sprints" discipline `docs/sprint_book/INDEX.md`'s Level 3/Level 4 breakdown notes already established, applied here for the first time within Level 5 Part B.

**No new external dependency, and no stop-and-ask gate is needed** — unlike Sprint 4.16's Search & Research provider choice or Sprint 5.8's VTube Studio WebSocket client choice, both libraries this sprint needs are already locked by `03_Engineering_Standards.md`: `pywin32` ("Native Windows functionality. System-level operations.") already backs `device_control/window_manager.py`'s/`device_control/application_manager.py`'s own `win32gui.GetForegroundWindow()`/`win32process.GetWindowThreadProcessId()` calls; `psutil` ("System Monitoring... CPU, RAM, Battery, Disk, Resource monitoring") already backs `core/resource_monitor.py`. `analytics/` is also already named in Part 3's own repository-structure list — unlike `emotion/`/`presentation/` at Level 5 Part A, no `backlog/technical_debt.md` "new top-level folder" entry is warranted here.

**A real modeling decision made explicitly here**: rather than a `UsageTracker` that maintains a mutable "current session" across polls (closing it out and reopening a new one whenever the foreground app changes — genuinely stateful, and a real source of bugs if a poll is ever missed or the process restarts mid-session), this sprint stores immutable per-poll samples only (`AppFocusSample` — one row per tick) and derives sessions at *read* time by grouping contiguous same-process samples (`UsageStore.list_sessions_since()`). This is simpler and strictly more honest about what was actually observed (a gap in samples — e.g. the process was asleep, or a poll was missed — cannot silently merge two real, distinct sessions into one), the same "prefer a simpler, more honest shape over a stateful one" reasoning `sprint_4_14.md`'s own `ScheduledItem` decision already used for a different problem.

**Reused, not reinvented**: the periodic tick itself is `scheduler/task_scheduler.py`'s `TaskScheduler.add_job()`/`remove_job()` (Sprint 4.15), the exact generic primitive that sprint was built to serve future callers beyond `ReminderEngine` — the first of what `docs/sprint_book/INDEX.md`'s own Level 4 Part B breakdown note anticipated.

## Objectives

- `AppFocusSample` (one observed foreground-application reading) and `UsageSession` (a derived, contiguous run of same-application samples).
- `UsageStore`: persistent (SQLite, via `SqliteClient`) recording of samples plus session-derivation queries.
- `UsageTracker`: a `ManagedModule` that samples the real foreground window/process on a `TaskScheduler`-driven interval and records it via `UsageStore`.
- `AnalyticsConfig` (new `config/schema.py` section), this Sprint Book's first.

## Dependencies

4.6 (`device_control/resource_gate.py`'s established `psutil`-via-`ResourceMonitor` precedent — the pattern this sprint's own process-name lookup follows), 4.2 (`device_control/application_manager.py`'s established `win32gui`/`win32process` foreground-window precedent this sprint's own sampling follows). No dependency on Level 4 Part A's own `ManagedModule` graph — this sprint only reuses the same *libraries*, not any Part A class.

## Files to Create

- `analytics/usage_model.py` — `AppFocusSample` (dataclass), `UsageSession` (dataclass).
- `analytics/usage_store.py` — `UsageStore`.
- `analytics/usage_tracker.py` — `UsageTracker`.
- `tests/unit/analytics/test_usage_model.py`
- `tests/unit/analytics/test_usage_store.py`
- `tests/unit/analytics/test_usage_tracker.py`

## Files to Modify

- `config/schema.py` — new `AnalyticsConfig` dataclass: `sample_interval_seconds: float = 60.0` (how often `UsageTracker` samples the foreground window), `session_gap_seconds: float = 180.0` (a gap between two same-process samples wider than this splits them into two sessions rather than one continuous one — accounts for a missed poll without falsely joining two real, separate sessions), `category_map: dict[str, str] = field(default_factory=dict)` (a config-driven `process_name -> category` map, e.g. `{"devenv.exe": "coding", "chrome.exe": "browsing"}`, the same "small, literal, config-driven classification" discipline `PresentationConfig.workspace_profile_keywords`/`decision/authority.py`'s keyword tuples already established — empty by default, since no category has any basis without the user's own machine-specific application list).
- `config/defaults.yaml` — matching `analytics:` section.

## Expected Classes

- `AppFocusSample` (dataclass) — `sample_id: str`, `process_name: str`, `window_title: str`, `sampled_at: datetime`.
- `UsageSession` (dataclass) — `process_name: str`, `category: str | None` (resolved via `AnalyticsConfig.category_map`, `None` if unmapped), `started_at: datetime`, `ended_at: datetime`, `sample_count: int` (how many raw samples contributed — a cheap, honest confidence signal: a session backed by one sample is far less certain than one backed by twenty).
- `UsageStore(ManagedModule)` — constructor DI: `(sqlite_client: SqliteClient, analytics_config: AnalyticsConfig)`. Owns its own table DDL (`app_focus_samples`), the same "caller owns its own DDL" precedent `CalendarStore`/`WorkflowStore`/`ActionAuditLog` already established.
- `UsageTracker(ManagedModule)` — constructor DI: `(task_scheduler: TaskScheduler, usage_store: UsageStore, analytics_config: AnalyticsConfig)`.

## Expected Interfaces

None new.

## Expected Functions

- `UsageStore.record_sample(sample: AppFocusSample) -> None`
- `UsageStore.list_samples_since(since: datetime) -> list[AppFocusSample]` — ordered oldest-first (session derivation below needs chronological order; nothing in this sprint needs newest-first).
- `UsageStore.list_sessions_since(since: datetime) -> list[UsageSession]` — groups `list_samples_since()`'s own result into `UsageSession`s: consecutive samples sharing `process_name` with a gap of at most `analytics_config.session_gap_seconds` between them collapse into one session; a wider gap, or a different `process_name`, starts a new one. A single sample with no neighbor becomes a one-sample session (`sample_count=1`), never dropped.
- `UsageTracker._sample_foreground_window() -> AppFocusSample | None` — `win32gui.GetForegroundWindow()` → `win32process.GetWindowThreadProcessId()` → `psutil.Process(pid).name()` (process name) + `win32gui.GetWindowText()` (window title); returns `None` (no sample recorded) when there is no real foreground window (`hwnd == 0`, the desktop itself is focused) or the resolved process has already exited by the time `psutil.Process()` is called (`psutil.NoSuchProcess`) — a real, ordinary race between reading the handle and resolving it, not an error condition.
- `UsageTracker._on_tick() -> None` — calls `_sample_foreground_window()`; when non-`None`, `usage_store.record_sample()`.

## Data Flow

```
TaskScheduler job (analytics_config.sample_interval_seconds)
      ↓
UsageTracker._on_tick()
      ↓
_sample_foreground_window()  →  win32gui/win32process/psutil (real OS state)
      ↓
AppFocusSample
      ↓
UsageStore.record_sample()  →  persisted (SQLite, app_focus_samples table)
      ↓
(later, on demand) UsageStore.list_sessions_since(since)
      ↓
Sprint 5.20 (Analytics Dashboard Data), Sprint 5.21 (Pattern Recognition)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `AnalyticsConfig`.
2. `analytics/usage_model.py` — `AppFocusSample`, `UsageSession`.
3. `analytics/usage_store.py` — `UsageStore`, own DDL, `record_sample()`/`list_samples_since()`/`list_sessions_since()`.
4. `analytics/usage_tracker.py` — `UsageTracker`, `start()` registers a `TaskScheduler` job, `stop()` removes it, `_on_tick()`/`_sample_foreground_window()`.
5. Unit tests: sample round trip; session-derivation grouping (same-process contiguous samples merge; a gap wider than `session_gap_seconds` splits; a different process splits); a simulated `psutil.NoSuchProcess` race degrades to no sample recorded, not a raised exception; persistence across a `UsageStore` close/reopen cycle.

## Architecture Notes

`UsageTracker` never interprets what it observes — no "this is work" / "this is a distraction" judgment anywhere in this sprint, matching the Learning Engine's own "never makes major autonomous decisions" mandate one level up in the architecture (Part 2) applied here at the data-collection layer first. `AnalyticsConfig.category_map` is the *only* classification surface, entirely user-configured, defaulting to empty (no category assigned to anything) rather than a guessed built-in list — the same "no basis in Part 2's own text, don't build it speculatively" discipline this Sprint Book applies repeatedly.

`UsageStore` has zero knowledge of Wellness, Learning, or any dashboard — this sprint answers only "what was the foreground application, and when," the same storage/interpretation separation `sprint_4_14.md`'s `CalendarStore` already established for reminders.

## Integration Considerations

- Registered as a `ManagedModule` with `CoreManager` by Sprint 5.24 (Companion Intelligence Integration), following the same `main.py` composition-root pattern every prior storage/tracker class has already established.
- Sprint 5.20 (Analytics Dashboard Data) and Sprint 5.21 (Pattern Recognition) are this sprint's own real consumers within this Sprint Book's scope; nothing calls `list_sessions_since()` yet within 5.17 itself.
- No opt-out/privacy control exists yet for a user who does not want their application usage recorded — flagged here rather than silently assumed acceptable; see Potential Risks.

## Potential Risks

- **No user-facing opt-out or visibility control is built in this sprint** — `UsageTracker` records continuously once started, with no pause/disable surface. Given `01_Project_Vision.md`'s own privacy-respecting framing, this is a real, disclosed gap; a Future Consideration, not solved here since no sprint in this Book names a settings-UI surface for it.
- **`psutil.Process(pid).name()` can raise `psutil.AccessDenied` for a small number of protected/elevated processes** (not just `NoSuchProcess`) — `_sample_foreground_window()` must treat both identically (no sample, not a crash); a real, if narrow, gap if only one is handled.
- **`session_gap_seconds`/`sample_interval_seconds` are unvalidated guesses**, the same tuned-constant caveat every comparable config default in this codebase already carries.
- **No Fail Gracefully hardening for `UsageStore`'s own SQLite calls this sprint** — deliberate, matching `CalendarStore`'s identical Sprint 4.14 precedent (no real caller exists yet to meaningfully degrade for); Sprint 5.25's job once Sprint 5.20/5.21/5.24 give it real callers.

## Acceptance Criteria

- `_sample_foreground_window()` returns a real `AppFocusSample` when a real foreground window exists, and `None` (never raises) when there is none or the owning process has already exited.
- Samples round-trip through `record_sample()`/`list_samples_since()` with every field preserved exactly.
- `list_sessions_since()` correctly merges contiguous same-process samples within `session_gap_seconds`, correctly splits on a wider gap or a process change, and never drops a lone sample.
- `UsageTracker.start()` registers exactly one `TaskScheduler` job; `stop()` removes it; ticking the job (test-driven, not a real wait) produces a real, persisted sample when a fake foreground-window resolver returns one.
- Data survives a `UsageStore` close/reopen cycle against the same SQLite file.

## Testing Checklist

- [ ] Unit: `AppFocusSample`/`UsageSession` construction and field defaults.
- [ ] Unit: `record_sample()`/`list_samples_since()` round trip, ordering.
- [ ] Unit: `list_sessions_since()` — contiguous merge, gap split, process-change split, lone-sample survival.
- [ ] Unit: `_sample_foreground_window()` against faked `win32gui`/`win32process`/`psutil` — a real reading, a no-foreground-window case, a `psutil.NoSuchProcess` race, a `psutil.AccessDenied` case.
- [ ] Unit: `UsageTracker.start()`/`stop()` job registration/removal against a fake `TaskScheduler`.
- [ ] Unit: persistence survives close/reopen against a real (temp-file) SQLite database.

## Documentation Checklist

- [ ] `analytics/usage_model.py`/`analytics/usage_store.py`/`analytics/usage_tracker.py` docstrings: the immutable-sample-not-mutable-session modeling decision, stated explicitly (per Engineering Rationale above).
- [ ] `docs/STATUS.md` — Phase 5.3 (Analytics) row moves to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

5.18 — Wellness Triggers.

## Future Considerations

- A user-facing pause/disable/visibility control for usage tracking — the real privacy gap named above, out of this Sprint Book's own scope.
- Multi-window/multi-monitor attention tracking (which of several visible windows the user is actually looking at, not just which has OS focus) — no basis in Part 2's own text, not built speculatively.
- True "project" tracking (as opposed to the category-map proxy Sprint 5.20 builds) — would need an explicit user-declared project concept nothing in this codebase has yet.
