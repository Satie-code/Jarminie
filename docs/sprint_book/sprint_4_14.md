# Sprint 4.14 — Calendar & Deadlines Store

## Sprint ID

4.14

## Sprint Name

Calendar & Deadlines Store

## Purpose

Give the Scheduler Engine its definition/storage half — a persistent record of calendar events, deadlines, and projects — per `02_System_Architecture.md`'s Scheduler Engine section (*"Calendar. Deadlines. Events."*) and `04_Master_Implementation_Plan.md`'s Phase 4.3 (*"Calendar. Deadlines. Events."*). This is the first sprint of Level 4 Part B and, structurally, plays the same role for the Scheduler that Sprint 4.9 (Workflow Builder) played for the Workflow Engine: storage only, no execution/notification logic.

## Engineering Rationale

Corresponds to `docs/sprint_book/INDEX.md`'s roadmap-granularity `4.14 Calendar & Deadlines Store` entry, now expanded to full detail per the explicit user request that opened this Sprint Book (2026-07-31), matching the same "expand when current" practice already used for Levels 2, 3, and Part A.

**One modeling decision made explicitly here, since Part 2's text names three nouns ("Calendar," "Deadlines," "Events") without specifying whether they are three separate stored shapes or one shape with a type distinction**: this sprint ships a single `ScheduledItem` dataclass with an `ItemType` enum (`EVENT`, `DEADLINE`) rather than three parallel classes/tables. The two share every field that matters for storage and querying (a title, an optional description, a `scheduled_at`/`due_at` timestamp, completion state) — the only real behavioral difference (a deadline has a hard due time that reminders count down toward; an event has a start time that a reminder announces in advance) is a Sprint 4.15 (Reminder Engine) concern, not a storage-shape concern. This mirrors Sprint 4.9's own precedent of keeping `WorkflowStep`/`ActionRequest` deliberately aligned rather than building parallel shapes for structurally identical data, and Sprint 3.1's `MemoryType`-as-a-single-table-discriminator design (`memory/memory_store.py`) — the established pattern in this codebase for "several conceptually distinct things that share one real storage shape."

Kept as a separate sprint from Reminder Engine (4.15), preserving the roadmap's own split and matching the exact risk-boundary reasoning `sprint_4_9.md`'s Engineering Rationale already established for Workflow Builder/Workflow Executor: a stored `ScheduledItem` that nothing ever reminds anyone about is inert and safe; Reminder Engine is where real-world interruption (speaking to the user, possibly while a session is already active — Part 2's own Priority Queue "Priority 3: Scheduled reminders — Queued" language) actually matters.

`database/sqlite_client.py`'s `SqliteClient` is reused unchanged, following the exact "caller owns its own DDL" precedent every prior storage sprint (`ConversationSessionStore`, `MemoryStore`, `ActionAuditLog`, `WorkflowStore`) has already established — `docs/sprint_book/INDEX.md`'s own Recommendations section named this specific sprint ("Scheduler (now Part B, Sprint 4.14)") as the next one expected to follow that precedent when it arrived.

## Objectives

- `ScheduledItem` (a stored calendar entry, deadline, or event) and `ItemType`.
- `CalendarStore`: persistent (SQLite, via `SqliteClient`) create/read/update/delete/list for `ScheduledItem`s, including a query for "items due within a window" (the primitive Sprint 4.15's reminder scheduling needs).
- `SchedulerConfig` (new `config/schema.py` section), this Sprint Book's first.

## Dependencies

3.1 (Memory Store Foundation, for the established `SqliteClient`-reuse-via-DI pattern this sprint follows — the same dependency `docs/sprint_book/INDEX.md`'s roadmap table already names). No dependency on Level 4 Part A — Scheduler is architecturally independent of Device Control/Workflow (Part 2 names them as sibling top-level engines, not a dependency chain).

## Files to Create

- `scheduler/scheduler_model.py` — `ScheduledItem` (dataclass), `ItemType` (Enum).
- `scheduler/calendar_store.py` — `CalendarStore`.
- `tests/unit/scheduler/test_scheduler_model.py`
- `tests/unit/scheduler/test_calendar_store.py`

## Files to Modify

- `config/schema.py` — new `SchedulerConfig` dataclass: `max_lookahead_days: int = 365` (a defensive bound against an unbounded future-dated query, the same category of guard `WorkflowConfig.max_steps_per_workflow` already established), `sqlite_path` reuse (no new field — `SchedulerConfig` takes `DatabaseConfig.sqlite_path` via the store constructor, the same "one database file, many tables" convention every prior storage class already follows, not a new config field).
- `config/defaults.yaml` — matching `scheduler:` section.

## Expected Classes

- `ItemType` (Enum) — `EVENT`, `DEADLINE`.
- `ScheduledItem` (dataclass) — `item_id: str`, `item_type: ItemType`, `title: str`, `description: str | None`, `scheduled_at: datetime` (an event's start time, or a deadline's due time — one field, meaning depends on `item_type`, avoiding two mutually-exclusive-in-practice timestamp fields), `is_completed: bool = False`, `created_at: datetime`.
- `CalendarStore(ManagedModule)` — constructor DI: `(sqlite_client: SqliteClient, scheduler_config: SchedulerConfig)`. Owns its own table DDL (`scheduled_items`), the same "caller owns its own DDL" precedent as `WorkflowStore`/`ActionAuditLog`/`ConversationSessionStore`.

## Expected Interfaces

None new.

## Expected Functions

- `CalendarStore.save(item: ScheduledItem) -> None`
- `CalendarStore.get(item_id: str) -> ScheduledItem | None`
- `CalendarStore.list_all() -> list[ScheduledItem]`
- `CalendarStore.list_due_within(window_end: datetime, *, include_completed: bool = False) -> list[ScheduledItem]` — the query primitive Sprint 4.15's `ReminderEngine` polls; returns every non-completed item whose `scheduled_at` falls at or before `window_end`, ordered soonest-first. Deliberately open-ended on the lower bound (no `window_start`) — a reminder that should have fired yesterday (e.g. the process was offline) still needs to surface, not silently vanish because it's "in the past" relative to the query window; Sprint 4.15 decides what to do with an overdue item (immediate announcement vs. a distinct "missed" handling), this store just reports it honestly.
- `CalendarStore.mark_completed(item_id: str) -> bool`
- `CalendarStore.delete(item_id: str) -> bool`

## Data Flow

```
caller (voice command, or a future authoring UI outside this sprint's scope)
      ↓
ScheduledItem(item_type=DEADLINE, title="Submit report", scheduled_at=...)
      ↓
CalendarStore.save(item)  →  persisted (SQLite, scheduled_items table)
      ↓
(periodically) CalendarStore.list_due_within(now + lookahead_window)
      ↓
Sprint 4.15 (Reminder Engine)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `SchedulerConfig`.
2. `scheduler/scheduler_model.py` — `ItemType`, `ScheduledItem`.
3. `scheduler/calendar_store.py` — `CalendarStore`, own DDL, full CRUD plus `list_due_within()`.
4. Unit tests: save/get/list/delete/mark_completed round trips, `list_due_within()`'s window/ordering/overdue-item behavior, persistence across a `close()`/reopen cycle (matching every prior storage sprint's own precedent for verifying real persistence, not just an in-memory happy path).

## Architecture Notes

`ScheduledItem.scheduled_at` uses one timestamp field for both event-start and deadline-due semantics deliberately — see Engineering Rationale above. A future need to distinguish "starts at" from "must finish by" (e.g. a multi-day event) has no basis in Part 2's own text and is not built speculatively; `item_type` alone is enough to disambiguate what the one timestamp means for every capability this Sprint Book actually specifies.

`CalendarStore` has zero knowledge of reminders, notification timing, or postponement — those are entirely Sprint 4.15's concern, the same storage/execution separation `WorkflowStore`/`WorkflowExecutor` already established. This store answers "what's due soon," never "should the user be told right now" (that answer depends on Quiet Mode state, an active session, and the Priority Queue — none of which this sprint touches).

## Integration Considerations

- Registered as a `ManagedModule` with `CoreManager` by Sprint 4.18 (Scheduler & Internet Agent Integration), following the same `main.py` composition-root pattern every prior storage class has already established.
- No authoring interface (voice or UI) is built in this sprint — `CalendarStore.save()` is real, tested, and callable, but nothing yet constructs a `ScheduledItem` from a live conversation turn; that live-caller gap is explicitly out of this sprint's own scope and named here rather than silently discovered later, the same discipline `sprint_4_9.md` already applied to `WorkflowStore`.
- Sprint 4.15 (Reminder Engine) is the sole consumer of `CalendarStore.list_due_within()` within this Sprint Book's own scope.

## Potential Risks

- **No recurrence support** — `ScheduledItem` models a single point in time; a repeating event ("every Monday") has no representation and would need a caller to create one row per occurrence. Acceptable for this sprint's own scope (Part 2 names no recurrence requirement), flagged as a Future Consideration, not built speculatively.
- **`max_lookahead_days` (365) is an unvalidated guess**, same caveat class as every other tuned bound in this codebase — config-driven for exactly that reason.
- **No authoring interface means this sprint's own real-world testability is limited to directly constructed `ScheduledItem` objects** in tests, the same honest scoping limitation `sprint_4_9.md` already named for `WorkflowStore` — the Master Plan's "Scheduling reliable" acceptance criterion cannot be fully demonstrated end-to-end until Sprint 4.15 and, ultimately, Sprint 4.20's real verification pass exist.

## Acceptance Criteria

- A `ScheduledItem` round-trips through `save()`/`get()` with every field preserved exactly, including `item_type`.
- `list_due_within()` returns exactly the non-completed items at or before the given window end, soonest-first, including an item whose `scheduled_at` is already in the past.
- `list_all()` accurately reflects the current set of stored items across save/delete operations.
- `mark_completed(item_id)` persists and is reflected in a subsequent `get()` and excluded from `list_due_within()` (unless `include_completed=True`).
- Data survives a `CalendarStore` close/reopen cycle against the same SQLite file.

## Testing Checklist

- [ ] Unit: save/get round trip preserves every field.
- [ ] Unit: `list_due_within()` window boundary (exactly-at-window-end is included; just-past is excluded), ordering, and overdue-item inclusion.
- [ ] Unit: `list_all()` reflects save/delete correctly.
- [ ] Unit: `mark_completed()` persists and is excluded from `list_due_within()` by default.
- [ ] Unit: persistence survives close/reopen against a real (temp-file) SQLite database.
- [ ] Unit: `delete()`/`mark_completed()` of a nonexistent `item_id` returns `False`, not an exception.

## Documentation Checklist

- [ ] `scheduler/scheduler_model.py`/`scheduler/calendar_store.py` docstrings: the single-`ScheduledItem`-shape decision, stated explicitly (per Engineering Rationale above).
- [ ] `docs/STATUS.md` — Phase 4.3 (Scheduler) row moves to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

4.15 — Reminder Engine (delay/reschedule/postpone).

## Future Considerations

- Recurring events/deadlines — flagged above, not built now.
- A voice or UI authoring interface — the real gap named above; out of this Sprint Book's scope entirely.
- Item categories/tagging (e.g. "work" vs. "personal") — no basis in Part 2's own text; would be a real, if small, schema addition if a future need names it.

## Sprint Completion Report (2026-07-31)

Implemented as specified, authorized directly ("continue with the implementation of sprint 4.14") — the spec was already complete and unmodified from this session's own Pass-1 planning work, so implementation proceeded without a separate stop-and-ask round trip, matching this project's established precedent for a direct "proceed with implementation" instruction against an already-complete sprint file. Delivered `scheduler/scheduler_model.py` (`ItemType`, `ScheduledItem`), `scheduler/calendar_store.py` (`CalendarStore` — a `ManagedModule`, real single-table `scheduled_items` SQLite schema via `SqliteClient`, full create/read/update(mark-completed)/delete plus `list_due_within()`), `SchedulerConfig` in `config/schema.py`/`config/defaults.yaml`/`config/loader.py`'s `_SECTION_SCHEMAS`. 20 new tests (2 in `tests/unit/scheduler/test_scheduler_model.py`, 18 in `tests/unit/scheduler/test_calendar_store.py`, including a real close/reopen persistence round trip against a temp-file SQLite database, matching every prior storage sprint's own established precedent). Full-suite run: 934 total, 919 passing — the only failures are the 15 pre-existing, already-tracked `tests/unit/voice/test_text_to_speech.py` failures (`backlog/technical_debt.md` item 29, a PySide6/shiboken6-vs-`six` environment bug, confirmed unrelated to this sprint's own code), `ruff check .` clean.

**One deliberate deviation from this session's own Pass-1 plan, corrected before writing any code**: the sprint file's own "Files to Modify" section for `config/schema.py` had listed `SchedulerConfig` alongside a parenthetical about "no new field" for `sqlite_path` reuse, but while implementing `SchedulerConfig` I initially also drafted `poll_interval_seconds`/`reminder_lookahead_seconds` fields belonging to Sprint 4.15 (Reminder Engine) per this Sprint Book's own later sprint — caught immediately by re-reading Sprint 4.14's own Files to Modify section, which names only `max_lookahead_days` for this sprint, and removed before any test was written. Consistent with this project's own "don't build ahead of the current sprint's own scope" discipline (`05_Claude_Development_Guide.md`'s Step 3).

**`SchedulerConfig.max_lookahead_days` was given a real enforcement point not explicitly spelled out in the sprint file's own Expected Functions signature**: `list_due_within()` now raises `ValueError` (no query run) when `window_end` exceeds `max_lookahead_days` from now, the same "enforced here, not left to a caller's own discipline" pattern `WorkflowStore.save()`'s `max_steps_per_workflow` check already established (Sprint 4.9) — without this, the newly-added config field would have been present but genuinely unused by this sprint's own code, the exact "constructor arg completely unused" gap Sprint 4.9's own Engineering Rationale specifically called out as a mistake to avoid repeating (`voice/conversation_store.py`'s `purge_older_than()` default-fallback fix, referenced in that sprint's own completion report). Not spelled out in the original Expected Functions section, but a direct, narrow implementation of what the field's own docstring already promised ("a defensive bound... enforced").

Deliberately NOT given Fail Gracefully hardening this sprint, per the sprint's own Engineering Rationale — `CalendarStore`'s SQLite calls have no try/except wrapping yet, matching `WorkflowStore`'s identical Sprint 4.9 precedent; Sprint 4.19 (Error Handling & Recovery Hardening, Part B) is where this lands, once `ReminderEngine` (4.15) and `CommunicationPipeline._handle_scheduler_turn()` (4.18) give it real callers. No authoring interface (voice or UI) exists yet — `CalendarStore.save()` is real and callable, but nothing yet constructs a `ScheduledItem` from a live conversation turn; explicitly out of this Sprint Book's own scope, named here rather than silently discovered later. Not yet wired into `main.py`/`CoreManager` — Sprint 4.18's job, alongside every other Level 4 Part B module. `docs/STATUS.md` (Phase 4.3 now `Developing`) and `docs/sprint_book/INDEX.md` (4.14 row marked `Complete`) both updated. **Sprint 4.15 (Reminder Engine) is next.**

### Post-Sprint Fix (2026-08-01, Sprint 4.19 — Error Handling & Recovery Hardening, Part B, scenario e)

`CalendarStore` now has real Fail Gracefully hardening, exactly as this sprint's own Engineering Rationale predicted once real callers existed: `list_due_within()` (its only real read-path caller, `ReminderEngine._poll_due_items()`) degrades to `[]` on a SQLite failure rather than raising, matching `MemoryStore.recent()`'s established convention — a transient outage simply means that one poll cycle finds nothing, never a lost item (still persisted, picked up on the next successful poll). `get()`/`list_all()`/`mark_completed()`/`delete()` remain deliberately unhardened, same as `WorkflowStore`'s own precedent — none has a real production caller yet (`postpone()`/`reschedule()`/`acknowledge()` are real and tested but not called from anywhere live). `save()` itself is deliberately left unwrapped by this class — its one real caller, `CommunicationPipeline._handle_scheduler_turn()`, needs to compose an honest degraded spoken reply on failure, which only the caller (not this store) can do; wrapping `save()` to silently swallow here would risk the opposite problem, a false "Done" reply the user never actually got. See `sprint_4_18.md`'s own Post-Sprint Fix for the matching `voice/pipeline.py` change. Regression tests: `test_list_due_within_degrades_to_empty_list_on_a_sqlite_read_failure` and `test_list_due_within_max_lookahead_days_check_still_raises_even_while_query_fails` (`tests/unit/scheduler/test_calendar_store.py`), plus `test_poll_due_items_survives_a_real_calendar_store_failure` (`tests/unit/scheduler/test_reminder_engine.py`), proving the degrade through the real `ReminderEngine` caller too, not just `CalendarStore` in isolation.
