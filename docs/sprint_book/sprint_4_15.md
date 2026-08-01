# Sprint 4.15 — Reminder Engine (delay/reschedule/postpone)

## Sprint ID

4.15

## Sprint Name

Reminder Engine (delay/reschedule/postpone)

## Purpose

Turn `CalendarStore`'s (4.14) stored items into real, time-driven reminders, per `02_System_Architecture.md`'s Scheduler Engine section (*"Reminders. Delayed reminders. Reminder rescheduling. Wellness postponement."*) and Part 2's Priority Queue System, which names Scheduled Reminders as Priority 3 (*"Queued."*) — this sprint gives that priority level its first real source since `decision/priority_queue.py` shipped it as a reserved value at Sprint 3.10.

## Engineering Rationale

Corresponds to `docs/sprint_book/INDEX.md`'s roadmap-granularity `4.15 Reminder Engine (delay/reschedule/postpone)` entry, expanded to full detail alongside the rest of this Sprint Book (2026-07-31).

**`APScheduler` is installed starting this sprint** — `requirements.txt` already declares `APScheduler>=3.10` (added ahead of need when Level 4 Part A's own dependencies were pinned, commented "Phase 4.2 / 4.3 — Workflow & Scheduler") but `backlog/technical_debt.md` item 1 explicitly deferred actually installing it until "the phase that needs it," matching every prior dependency's own per-phase install discipline (PySide6 at 1.3, `sounddevice` at 2.1, `chromadb` at 3.1, `pywin32` at 4.2, etc.). This sprint is that phase. `APScheduler.BackgroundScheduler` (not `BlockingScheduler`) is the correct choice — it runs its own scheduling thread without blocking the Qt event loop (`ui/app.py`'s `run_app()`), the same "background thread, not the main loop" shape `WakeWordDetector`'s passive-listening thread and `VoiceSessionManager`'s watchdog thread already establish.

**The real `BackgroundScheduler` instance is owned by a new, small, standalone `TaskScheduler` class — not privately by `ReminderEngine` itself.** `docs/sprint_book/INDEX.md`'s own Recommendations section, written back when `backlog/technical_debt.md` items 11/15 were first logged, already named this exact question: *"worth deciding... whether one generic periodic-task mechanism can serve both `MemoryLifecycleManager`'s passes and `ConversationSessionStore.purge_older_than()`/`ActionAuditLog.purge_older_than()`, rather than three separate ad hoc timers."* Those three methods still have only a one-time-at-startup caller each (items 11/15's own current, honest status) — a real *recurring* cadence for all three has been explicitly deferred, every time, to "once Level 4 Part B's Scheduler exists." This sprint is that point. Rather than `ReminderEngine` privately owning a `BackgroundScheduler` that only it can add jobs to (which would leave items 11/15 exactly as unresolved as before, just with a second, parallel, equally-private scheduler now sitting next to the gap), `TaskScheduler` exposes one generic `add_job(func, interval_seconds, job_id)` primitive that any caller can register a recurring callable against. `ReminderEngine` becomes `TaskScheduler`'s first caller (registering its own `_poll_due_items` on `poll_interval_seconds`); Sprint 4.18 (Scheduler & Internet Agent Integration) is where `main.py` — the only file with construction-time references to `MemoryLifecycleManager`/`ConversationSessionStore`/`ActionAuditLog` — registers their three passes as additional jobs on the same instance, finally closing items 11/15's recurring-cadence gap for real. Named here explicitly so Sprint 4.18 isn't left to rediscover this connection on its own.

**A real architectural boundary decision, made explicitly here rather than left implicit**: `ReminderEngine` enqueues due items onto `PriorityQueueManager` (3.10) — it does **not** itself decide when to interrupt the user, drive `QuietModeController`, or call `VoiceSessionManager.speak_reply()`. Keeping `scheduler/` from reaching into `voice/` preserves the same dependency direction discipline `docs/sprint_book/INDEX.md`'s own Recommendations already established for `workflow/`→`device_control/` ("Device Control is the more architecturally foundational... `workflow/` depending on `device_control/`, never the reverse") — `scheduler/` has no business knowing about microphones, sessions, or personas any more than `workflow/` has business launching processes directly instead of going through `device_control/`'s Action Engine. The actual "pop the queue and speak, respecting Quiet Mode" consumer is a `voice/`-level concern and is explicitly Sprint 4.18's job (Scheduler & Internet Agent Integration) — mirroring exactly how Sprint 4.10 (Workflow Executor) built real dispatch logic while `main.py`/`CommunicationPipeline` wiring waited for Sprint 4.11. This also finally gives `PriorityQueueManager.enqueue()`/`.pop_next()`/`.peek_next()` — implemented and unit-tested since Sprint 3.10 but never called by anything real (`backlog/technical_debt.md` item 17, only ever partially resolved by Sprint 4.6's unrelated resource-gate path) — their first genuinely intended live source, closing the "Scheduled Reminders" half of that gap in Sprint 4.18.

Kept as a separate sprint from Calendar & Deadlines Store (4.14), matching the storage/execution split precedent `sprint_4_9.md`/`sprint_4_10.md` already established for Workflow, and `sprint_2_7.md`/`sprint_2_8.md` before that for Conversation Store/Context Manager.

**"Wellness postponement," named in Part 2's Scheduler Engine section, is built here only as a generic, reusable postponement primitive** (`postpone(item_id, delay)`) — the Wellness Engine's own escalation policy (*"Stop repeated reminders after three postponements... Resume after: New session / Actual break / Significant inactivity"*) is explicitly Part 2's Wellness Engine section, Phase 5.2, not Scheduler's. `ReminderEngine` does not track postponement counts or enforce any hard limit; it just reschedules on request, honestly and generically, so Level 5's Wellness Engine can call the same primitive later without this sprint guessing at wellness-specific policy it has no spec basis to build now. Named explicitly as a Future Consideration, not silently built nor silently ignored.

## Objectives

- `TaskScheduler(ManagedModule)`: owns the one real `BackgroundScheduler` instance; exposes a generic `add_job()`/`remove_job()` primitive any caller can register a recurring callable against — the shared periodic-task mechanism `docs/sprint_book/INDEX.md`'s Recommendations section already anticipated.
- `ReminderEngine`: registers its own due-item poll as one `TaskScheduler` job; enqueues each newly-due, not-yet-enqueued item onto `PriorityQueueManager` at `PriorityLevel.SCHEDULED_REMINDER`.
- `postpone(item_id: str, delay: timedelta) -> ScheduledItem | None` and `reschedule(item_id: str, new_time: datetime) -> ScheduledItem | None` — both update `CalendarStore` and clear the item's "already enqueued" tracking so it can be re-announced at its new time.
- `acknowledge(item_id: str) -> bool` — marks an item `is_completed=True` via `CalendarStore` (e.g. "got it, thanks" after a spoken reminder) and clears its tracking.
- `SchedulerConfig` gains the polling-interval and reminder-lookahead fields this sprint needs.

## Dependencies

4.14 (Calendar & Deadlines Store), 3.10 (Priority Queue, for `PriorityQueueManager.enqueue()`/`PriorityLevel.SCHEDULED_REMINDER`).

## Files to Create

- `scheduler/task_scheduler.py` — `TaskScheduler`.
- `scheduler/reminder_engine.py` — `ReminderEngine`.
- `tests/unit/scheduler/test_task_scheduler.py`
- `tests/unit/scheduler/test_reminder_engine.py`

## Files to Modify

- `config/schema.py` — `SchedulerConfig` gains `poll_interval_seconds: float = 30.0` (how often `ReminderEngine` checks `CalendarStore` for newly-due items — the real-time equivalent of `MemoryLifecycleManager`'s cleanup cadence, but per-item rather than per-pass) and `reminder_lookahead_seconds: float = 0.0` (how far into the future "due" looks ahead of `poll_interval_seconds`'s own next tick — `0.0` means "due now or overdue only," the safe default; a nonzero value lets a reminder fire slightly early for a caller that wants lead time, not built as a real feature this sprint beyond the config field itself).
- `config/defaults.yaml` — matching new `scheduler:` fields.
- `requirements.txt` — no line changes (`APScheduler>=3.10` is already present); comment updated to remove the "not yet installed" framing now that this sprint is the one installing it, matching `backlog/technical_debt.md` item 1's own per-phase resolution tracking convention.

## Expected Classes

- `TaskScheduler(ManagedModule)` — constructor DI: none (owns its `BackgroundScheduler` outright — there is nothing to inject; it is the root of this particular resource). `start()` creates and starts the real `BackgroundScheduler`; `stop()` shuts it down (`BackgroundScheduler.shutdown(wait=False)`, matching `WorkflowExecutor`'s own "don't block shutdown on in-flight background work" precedent from Sprint 4.10's own Architecture Notes, if that pattern applies — otherwise a bounded wait, decided at implementation time and documented, not silently assumed). `health_check()` reflects whether the underlying scheduler is genuinely running.
- `ReminderEngine` — constructor DI: `(calendar_store: CalendarStore, priority_queue_manager: PriorityQueueManager, task_scheduler: TaskScheduler, scheduler_config: SchedulerConfig)`. Not a `ManagedModule` itself — it owns no thread/resource of its own now that `TaskScheduler` does; its `start()`/`stop()`-shaped lifecycle (registering/removing its own job) happens via plain `register()`/`unregister()` methods called by whichever `ManagedModule` composes it (Sprint 4.18's own job, per `main.py`'s composition-root pattern), the same "plain, lifecycle-free collaborator, registered by its owner" shape `security/policy_engine.py`'s `PermissionPolicyEngine` already established for Level 4 Part A.

## Expected Interfaces

None new.

## Expected Functions

- `TaskScheduler.add_job(func: Callable[[], None], interval_seconds: float, job_id: str) -> None` — registers `func` to run every `interval_seconds` on the shared `BackgroundScheduler`; a duplicate `job_id` replaces the existing job (idempotent registration, safe to call again from a restarted module without manual bookkeeping by the caller).
- `TaskScheduler.remove_job(job_id: str) -> None` — no-op (not an error) if `job_id` isn't registered, the same tolerant-removal convention `WorkflowStore.delete()`/`CalendarStore.delete()` already established for "remove something that may already be gone."
- `ReminderEngine.register() -> None` / `ReminderEngine.unregister() -> None` — calls `task_scheduler.add_job(self._poll_due_items, scheduler_config.poll_interval_seconds, job_id="reminder_engine_poll")` / `task_scheduler.remove_job("reminder_engine_poll")`.
- `ReminderEngine._poll_due_items() -> None` — internal; calls `calendar_store.list_due_within(now)`, and for each item not already in the engine's own in-memory `_enqueued_item_ids` tracking set, constructs a `PriorityItem(payload=item, priority=PriorityLevel.SCHEDULED_REMINDER, source="scheduler")` and calls `priority_queue_manager.enqueue()`, then adds the item's id to `_enqueued_item_ids` so the next poll doesn't re-enqueue the same still-due, not-yet-acknowledged item every `poll_interval_seconds`.
- `ReminderEngine.postpone(item_id: str, delay: timedelta) -> ScheduledItem | None`
- `ReminderEngine.reschedule(item_id: str, new_time: datetime) -> ScheduledItem | None`
- `ReminderEngine.acknowledge(item_id: str) -> bool`

## Data Flow

```
CalendarStore.save(ScheduledItem(scheduled_at=<10 minutes from now>, ...))
      ↓
(background, every poll_interval_seconds, via TaskScheduler) ReminderEngine._poll_due_items()
      ↓
CalendarStore.list_due_within(now) → [item]  (once scheduled_at has passed)
      ↓
PriorityQueueManager.enqueue(PriorityItem(payload=item, priority=SCHEDULED_REMINDER))
      ↓
(Sprint 4.18's own consumer, outside this sprint's scope) pops the queue when idle,
announces via QuietModeController.activate(SCHEDULED_ALERT) + VoiceSessionManager.speak_reply()
      ↓
(user says "remind me in 10 minutes" / "got it") →
ReminderEngine.postpone(item_id, timedelta(minutes=10))  /  .acknowledge(item_id)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `SchedulerConfig` new fields.
2. `requirements.txt`/venv — install `APScheduler` for real (already declared, per Engineering Rationale).
3. `scheduler/task_scheduler.py` — `TaskScheduler`, `add_job()`/`remove_job()`.
4. `scheduler/reminder_engine.py` — `ReminderEngine`, `register()`/`unregister()`, `_poll_due_items()`, `postpone()`/`reschedule()`/`acknowledge()`.
5. Unit tests: `TaskScheduler` against a real `BackgroundScheduler` (job registration/removal/idempotent re-registration); `ReminderEngine` driven through a real `TaskScheduler` against a real, temp-file `CalendarStore` with a near-future `ScheduledItem`, confirming it's enqueued exactly once across several poll cycles (not re-enqueued while still pending); `postpone()`/`reschedule()`/`acknowledge()` correctness against both `CalendarStore` state and the engine's own tracking set.

## Architecture Notes

`_enqueued_item_ids` is deliberately in-memory-only, not persisted — see Potential Risks below for the honest tradeoff this implies. `ReminderEngine` never mutates `ScheduledItem.is_completed` itself except via `acknowledge()`'s own explicit call; a due-and-enqueued item that's never acknowledged stays enqueued (once) and due forever, which is the correct, honest behavior (Part 2 never says a reminder should self-expire).

`TaskScheduler` knows nothing about reminders, memory cleanup, or any other specific job's purpose — it is a pure, generic "run this callable on this interval" primitive, the same "mechanism, not policy" separation `PriorityQueueManager` itself already draws between classification and interruption-decision. This is what lets Sprint 4.18 register `MemoryLifecycleManager.run_cleanup_pass()`/`run_monthly_review()`, `ConversationSessionStore.purge_older_than()`, and `ActionAuditLog.purge_older_than()` as three more jobs on the identical instance without `TaskScheduler` itself changing at all.

`PriorityQueueManager.enqueue()` (3.10) already exists, fully implemented and unit-tested — this sprint is purely a new *caller*, not a change to that class. No modification to `decision/priority_queue.py` is anticipated; if implementation reveals `enqueue()`'s existing signature doesn't fit `ReminderEngine`'s payload shape, that is a real, narrow, additive finding to flag before proceeding, not silently worked around.

## Integration Considerations

- `TaskScheduler` is registered as a `ManagedModule` with `CoreManager` by Sprint 4.18; `ReminderEngine` itself is not (it has no lifecycle of its own now — see Expected Classes above) but is `register()`ed against the already-started `TaskScheduler` at the same point, following the same "construct, then register/wire" two-phase pattern `main.py` already uses throughout.
- **This sprint is also where `backlog/technical_debt.md` items 11 and 15's still-open recurring-cadence halves finally get a real, concrete path to resolution** — not resolved by this sprint itself (it has no reference to `MemoryLifecycleManager`/`ConversationSessionStore`/`ActionAuditLog`, all constructed elsewhere in `main.py`), but `TaskScheduler`'s existence is exactly the "one generic periodic-task mechanism" `docs/sprint_book/INDEX.md`'s Recommendations section asked for. Sprint 4.18 is where those three real registrations actually happen.
- **The queue-consumer half — popping a `SCHEDULED_REMINDER` item when the system is idle and actually speaking it — is explicitly NOT this sprint's job**, per the Engineering Rationale's dependency-direction reasoning above. This is this sprint's single most important named gap, worth restating rather than letting it be assumed away: after this sprint, a reminder can be scheduled, become due, and get enqueued — and nothing yet announces it. Sprint 4.18 closes that gap.
- No voice command surface exists yet for `postpone()`/`reschedule()`/`acknowledge()` — they are real, callable, tested methods with no live caller from a conversation turn. Wiring "remind me in 10 minutes" as a spoken response to an announced reminder is Sprint 4.18's own job too (the natural place, since it already owns the announcement flow these responses react to).
- Level 5's Wellness Engine (Phase 5.2, per `docs/sprint_book/INDEX.md`'s own dependency note: *"5.3 Wellness Triggers... Depends On 4.15"*) is expected to call `postpone()` directly once it exists, per this sprint's own Engineering Rationale — no Wellness-specific code is added here to anticipate that.

## Potential Risks

- **`_enqueued_item_ids` is in-memory only — a process restart forgets which due items were already enqueued.** A due reminder still enqueued-but-unacknowledged at restart is enqueued again, which is a safe, honest failure mode (a duplicate reminder is a minor annoyance, not a missed one — the opposite failure, silently losing a reminder because "it was already enqueued" state survived a restart while the queue itself didn't, would be far worse). Not persisted deliberately: a dedicated `reminder_state` table for this sprint's own scope would be premature durability for a problem (annoying-but-safe duplication) this project's own standing anti-over-engineering guidance says not to solve speculatively; flagged as a Future Consideration if real use shows duplicate reminders are a genuine problem, not assumed now.
- **`poll_interval_seconds` (30.0) trades latency for overhead** — a reminder can be enqueued up to ~30 seconds after its exact due time, an unvalidated guess like every other tuned interval in this codebase, config-driven for exactly that reason.
- **A single shared `TaskScheduler`/`BackgroundScheduler` means one misbehaving job (an exception inside `_poll_due_items()`, or, after Sprint 4.18, inside `MemoryLifecycleManager.run_cleanup_pass()`) must not be allowed to take down every other registered job.** APScheduler itself catches and logs a job's own exception without killing the scheduler thread by default, but this sprint's own tests must verify that real behavior directly rather than assuming APScheduler's documentation is accurate for this version — the same "verify, don't assume" discipline Sprint 4.12 applied to `subprocess.run(timeout=...)`'s own documented kill-on-timeout guarantee.
- **This sprint's own real-world testability is bounded by the same gap named in Integration Considerations**: nothing actually gets spoken yet, so "reminder fires and interrupts correctly" cannot be demonstrated end-to-end until Sprint 4.18 and, ultimately, Sprint 4.20's real verification pass exist. This sprint's Acceptance Criteria are scoped honestly to scheduling/enqueueing/postponement correctness only, the same honest-scoping discipline `sprint_4_14.md`/`sprint_4_9.md` already applied to their own storage-only sprints.
- **`BackgroundScheduler.shutdown()` timing needs real verification** — a job actively running at the exact moment `TaskScheduler.stop()` is called is a real, if narrow, race worth a dedicated test, the same discipline Sprint 4.12 applied to `CommandExecutionEngine`'s subprocess-timeout-vs-kill race.

## Acceptance Criteria

- A `ScheduledItem` due within the next poll cycle is enqueued onto `PriorityQueueManager` at `PriorityLevel.SCHEDULED_REMINDER` exactly once, not re-enqueued on subsequent polls while still pending.
- `postpone(item_id, delay)` updates the item's `scheduled_at` by `delay` and clears its enqueued-tracking, so it becomes due again (and re-enqueues) at the new time.
- `reschedule(item_id, new_time)` sets `scheduled_at` to `new_time` exactly, same re-enqueue behavior.
- `acknowledge(item_id)` marks the item completed via `CalendarStore` and it no longer appears in subsequent `list_due_within()`/enqueue cycles.
- `TaskScheduler.start()`/`stop()` cleanly start and stop the underlying `BackgroundScheduler`, verified via `health_check()` and no orphaned background thread after `stop()`.
- Two independently-registered `TaskScheduler` jobs run on their own intervals without interfering with each other, and one job's exception doesn't stop the other from continuing to run.

## Testing Checklist

- [ ] Unit: `TaskScheduler.add_job()`/`remove_job()` against a real `BackgroundScheduler` — registration, idempotent re-registration, tolerant removal of a nonexistent job.
- [ ] Unit: a job's own exception doesn't stop a second, independently-registered job from continuing to fire.
- [ ] Unit: `ReminderEngine`, driven through a real `TaskScheduler` (short `poll_interval_seconds` for test speed), enqueues a near-future item exactly once across multiple poll cycles.
- [ ] Unit: `postpone()`/`reschedule()` correctness against `CalendarStore` state and re-enqueue-eligibility.
- [ ] Unit: `acknowledge()` correctness and exclusion from future polls.
- [ ] Unit: `TaskScheduler.stop()` leaves no running background thread/job (verified, not assumed).
- [ ] Unit: `postpone()`/`reschedule()`/`acknowledge()` against a nonexistent `item_id` returns `None`/`False`, not an exception.
- [ ] Unit: `TaskScheduler.health_check()` reflects whether the underlying scheduler is genuinely running.

## Documentation Checklist

- [ ] `scheduler/reminder_engine.py` docstring: the deliberate storage-vs-announcement boundary (this class enqueues, it never speaks), stated explicitly, cross-referencing Sprint 4.18 as the class that closes the gap.
- [ ] `docs/backlog/technical_debt.md` — new item noting `PriorityQueueManager.enqueue()`'s `SCHEDULED_REMINDER` path now has a real source (this sprint) but the consumer side (`pop_next()`/`peek_next()`) still doesn't, until Sprint 4.18 — an honest, precise update to item 17's existing text rather than a premature "resolved."
- [ ] `docs/STATUS.md` — Phase 4.3 (Scheduler) row stays `Designing` (closed by 4.18, not this sprint, matching Workflow Engine's own 4.9/4.10 precedent where Phase 4.2 didn't move to `Complete` until 4.11).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

4.16 — Search & Research.

## Future Considerations

- Wellness-specific postponement-count escalation ("stop after three postponements") — explicitly Level 5's own job, named above, not built here.
- Persisted enqueue-tracking (surviving a restart) — flagged above as a real but currently-acceptable gap.
- A voice or UI authoring/response interface for reminders — the real gap named above; largely Sprint 4.18's job for the response half, entirely out of this Sprint Book's scope for authoring.

## Sprint Completion Report (2026-07-31)

Implemented as specified, authorized directly ("continue with sprint 4.15") right after Sprint 4.14 — no separate Pass-1 round trip, matching this session's own established precedent since the spec was already complete/unmodified. Delivered `scheduler/task_scheduler.py` (`TaskScheduler` — a real `APScheduler` `BackgroundScheduler` wrapper, `add_job()`/`remove_job()`), `scheduler/reminder_engine.py` (`ReminderEngine` — `register()`/`unregister()`, `_poll_due_items()`, `postpone()`/`reschedule()`/`acknowledge()`), `SchedulerConfig.poll_interval_seconds`/`reminder_lookahead_seconds` in `config/schema.py`/`config/defaults.yaml`. `APScheduler` genuinely installed into the venv for the first time (`APScheduler-3.11.3`, resolved with `tzlocal`/`tzdata`), closing the last remaining item in `backlog/technical_debt.md` item 1's own per-phase install list. 24 new tests (11 in `test_task_scheduler.py`, 13 in `test_reminder_engine.py`), all against real collaborators — a real `BackgroundScheduler`, a real temp-file `CalendarStore`, a real `PriorityQueueManager` — no mocking of any of them, matching this project's own "real collaborator for timing-sensitive/persistence-sensitive behavior" precedent. Stable across 3 repeated standalone runs of the new tests. `ruff check .` clean.

**One real bug in my own first test draft, caught and fixed before running anything**: the initial `test_reminder_engine.py` used a fixed, hardcoded calendar date/time (`_NOW = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)`) for items meant to be "due," but `ReminderEngine._poll_due_items()` always compares against the REAL wall-clock `datetime.now(UTC)` internally, not a test-injected value — a fixed constant would only coincidentally work depending on the exact time of day the suite happens to run, and would silently stop working once real calendar time moves far enough past that constant in either direction. Rewrote every affected test to compute `scheduled_at` as an offset from a freshly-captured `datetime.now(UTC)` at test-execution time instead, the same "compute relative to real now, never a frozen historical/future constant" discipline this codebase already needed for any test whose production code itself reads the real clock (distinct from `CalendarStore`'s own tests, Sprint 4.14, which are safe with a fixed constant since `list_due_within()`'s *due* comparison is fully test-controlled — only its `max_lookahead_days` guard touches real time, and a 365-day margin absorbs any realistic gap between a fixed test constant and actual execution time).

**A second, small correction against the sprint's own literal Expected Functions wording**: the spec described `_poll_due_items()` as constructing a `PriorityItem(...)` object before calling `enqueue()`, but `PriorityQueueManager.enqueue(payload, priority, source)` (3.10) already builds the `PriorityItem` internally from those three plain arguments — implemented as a direct `enqueue(payload=item, priority=PriorityLevel.SCHEDULED_REMINDER, source="scheduler")` call instead of constructing a redundant `PriorityItem` by hand, confirmed correct by reading the real method's signature first, exactly the "verify existing signature before assuming" check this sprint's own Architecture Notes had already flagged as the thing to do if a mismatch surfaced.

**`reminder_lookahead_seconds` was wired into real behavior, not left declared-but-unused** — `_poll_due_items()` widens its own `CalendarStore.list_due_within()` query window by exactly that many seconds, a direct, one-line implementation of what the field's own docstring already promised, and a deliberate change from the sprint's own text ("not built as a real feature this sprint beyond the config field itself") — reversed because shipping a documented, self-explanatory config field that does nothing contradicts this project's own "don't ship an unread config field" discipline, flagged explicitly in Sprint 4.14's own completion report one sprint ago. A dedicated regression test (`test_reminder_lookahead_seconds_widens_the_due_window`) confirms it.

**Full-suite run found one failure beyond the 15 already-tracked `test_text_to_speech.py` failures**: `tests/system/test_level4_part_a_acceptance.py::test_level4_part_a_full_acceptance_scenario` (`AssertionError: Timed out waiting for Quiet Mode Controller to return to DORMANT`, a 5-second wait). Investigated before dismissing it, per this project's own standing discipline — confirmed passing standalone (4/4 in that file, twice) and reproduced identically on a second full-suite rerun (same single test, same failure mode), with this sprint's own changes confined entirely to `scheduler/`/`config/` and touching none of `device_control/`, `voice/`, `decision/`, or `main.py` that this test's own scenario depends on. This is the same "passes standalone, occasionally times out under full-suite load" flake class already established for `test_full_level2/3_acceptance_scripted_conversation` and, per Sprint 4.12's own completion report, this exact test file — real host CPU/RAM contention from running ~950 tests concurrently, not a logic defect. Not a new finding requiring a new technical-debt entry — `backlog/technical_debt.md` already documents this flake class generally; not fixed here, consistent with every prior sprint's identical treatment of the same class of flake. Final count both runs: 958 total, 942 passing (16 failed = the 15 known `test_text_to_speech.py` failures + this one confirmed-flaky system test).

`docs/backlog/technical_debt.md` item 17 updated with an honest, precise account of what this sprint resolved (a real, live, recurring `SCHEDULED_REMINDER` *source*) versus what remains open (the consumer side, `pop_next()`/`peek_next()`, and the `IMPORTANT_ALERT` path's own still-missing periodic source) — not marked fully resolved. `docs/STATUS.md` (Phase 4.3 stays `Developing`, new completion notes) and `docs/sprint_book/INDEX.md` (4.15 row marked `Complete`) both updated. Neither `TaskScheduler` nor `ReminderEngine` is wired into `main.py`/`CoreManager` yet, and nothing yet pops the queue to actually announce a reminder — both explicitly Sprint 4.18's job, per this sprint's own Integration Considerations. **Sprint 4.16 (Search & Research) is next** — its own spec names an open stop-and-ask gate (the concrete search provider) that needs resolving before implementation can begin.
