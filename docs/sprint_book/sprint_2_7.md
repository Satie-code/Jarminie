# Sprint 2.7 — Conversation Session Store

## Sprint ID

2.7

## Sprint Name

Conversation Session Store

## Purpose

Begin Phase 2.2 (Conversation Engine) by persisting individual conversation turns, per [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md)'s Phase 2.2 tasks: *"Conversation sessions. Conversation history."* This is explicitly a **session log**, not the Memory Engine — Level 2's scope excludes memory, confidence scoring, and long-term retrieval entirely; those belong to Level 3 (Phase 3.1 Memory Engine, Phase 3.2 Dynamic Memory, per [02_System_Architecture.md](../02_System_Architecture.md)'s Memory Architecture and Dynamic Memory Formula).

## Engineering Rationale

[INDEX.md](INDEX.md) already flagged this sprint's real dependency accurately before this Sprint Book existed: *"database (3.1) stub"* — Conversation Session Store needs SQLite before Sprint 3.1 (Memory Store Foundation) formally builds out the database layer. Rather than have this sprint reach into `database/` and build something ad hoc, it creates the minimal generic piece `database/` was always going to need first: a thin `SqliteClient` connection wrapper (open, execute, close — no schema/table knowledge). Sprint 3.1 will be the one to decide whether `config/` (already SQLite-adjacent via `DatabaseConfig`), this store, and Scheduler (4.8) share one generic access layer, per the Recommendation already recorded in INDEX.md — this sprint answers "does a genuinely generic SQLite client already exist by the time that decision needs making," not the full generic-layer question itself.

To stay inside Level 2's boundary: rows here are timestamped turns tagged by session, with **bounded, time-based retention** and **no scoring, promotion, or cross-session semantic retrieval** of any kind. If a future sprint is tempted to add a "relevance" or "importance" column here, that is Sprint 3.1/3.2's Dynamic Memory Formula territory, not this one's.

## Objectives

- A generic `SqliteClient` in `database/` usable by any future subsystem needing simple structured persistence.
- A `ConversationSessionStore` that records each completed turn (`VoiceSessionManager.on_turn_complete`, from Sprint 2.5) and the persona that handled it, and can retrieve the most recent turns for a session.
- A bounded retention policy (configurable, time-based) — this is a rolling session log, not permanent storage.

## Dependencies

2.5 (Voice Session Manager & Timeout — supplies `on_turn_complete`), `database` (Sprint 3.1 stub — created here, not there)

## Files to Create

- `database/sqlite_client.py` — `SqliteClient` (connect/execute/close, WAL mode enabled, path from `DatabaseConfig.sqlite_path`).
- `voice/conversation_store.py` — `ConversationTurn` (dataclass), `ConversationSessionStore`.
- `tests/unit/database/test_sqlite_client.py`
- `tests/unit/voice/test_conversation_store.py`

## Files to Modify

- `voice/errors.py` — add `ConversationStoreError(VoiceError)`.
- `config/schema.py` — add `conversation_retention_days: int = 30` to `DatabaseConfig` (already owns `sqlite_path`/`chroma_path` — persistence *policy* belongs alongside persistence *paths*); add validation (`> 0`) to `AppConfig._validate_paths()`.

## Expected Classes

- `SqliteClient` — `connect() -> None`, `execute(sql: str, params: tuple) -> None`, `query(sql: str, params: tuple) -> list[tuple]`, `close() -> None`. No knowledge of what tables exist — pure connection/execution mechanism, per Interface First / Single Responsibility (schema ownership belongs to each caller, e.g. `ConversationSessionStore` owns its own table's DDL).
- `ConversationTurn` (dataclass) — `session_id: str`, `persona_name: str`, `timestamp: datetime`, `user_text: str`, `response_text: str`.
- `ConversationSessionStore(ManagedModule)` — constructor DI: `(sqlite_client: SqliteClient, database_config: DatabaseConfig)`.

## Expected Interfaces

- `ManagedModule` (reused) — `start()` opens the SQLite connection and ensures the conversation-turns table exists (idempotent `CREATE TABLE IF NOT EXISTS`); `stop()` closes the connection; `health_check()` reports connection liveness.

## Expected Functions

- `ConversationSessionStore.record_turn(turn: ConversationTurn) -> None` — a failed write is caught and logged, never raised out to the caller (Voice Session Manager must not crash a live conversation because a disk write failed — matches the precedent from Sprint 1.8's `ConfigLoader.save()` failure-handling lesson).
- `ConversationSessionStore.get_recent_turns(session_id: str, limit: int) -> list[ConversationTurn]`
- `ConversationSessionStore.purge_older_than(days: int) -> int` — deletes turns older than the retention window, returns the count removed; called periodically (the *caller* that decides cadence arrives with Sprint 2.12's integration, not this sprint — mirrors the "Core owns *how*, a caller owns *when*" pattern from `CoreManager.check_resources()` in Sprint 1.5).

## Data Flow

```
VoiceSessionManager.on_turn_complete(transcript, session_id)  (2.5)
      ↓
Persona reply composed (2.9+)
      ↓
ConversationSessionStore.record_turn(ConversationTurn(...))
      ↓
SqliteClient.execute(INSERT ...)
      ↓
   (later) get_recent_turns() → Context Manager (2.8)
```

## Acceptance Criteria

- `record_turn()` persists a turn retrievable via `get_recent_turns()` after a simulated restart (new `SqliteClient` instance, same file) — the same "real save, real reload" discipline established for `ConfigLoader` in Sprint 1.8, applied here since this module's whole point is persistence across a session boundary.
- A failed write (e.g. a locked/read-only database file) is logged and does not raise out of `record_turn()`.
- `purge_older_than()` removes only turns strictly older than the window and leaves recent ones intact.
- No table other than conversation turns is created by this sprint — no memory/confidence columns.

## Testing Checklist

- [ ] Unit: `SqliteClient` connect/execute/query/close against a temp file.
- [ ] Unit: `record_turn()` + `get_recent_turns()` round-trip, including a real restart simulation (new instances, same underlying file).
- [ ] Unit: `record_turn()` swallows and logs a write failure rather than raising.
- [ ] Unit: `purge_older_than()` boundary behavior (exactly-at-window, just-under, just-over).
- [ ] Unit: `AppConfig._validate_paths()` rejects a non-positive `conversation_retention_days`.

## Documentation Checklist

- [ ] `database/sqlite_client.py` docstring: deliberately schema-agnostic, intended as the shared low-level piece for Sprint 3.1 to build on.
- [ ] `voice/conversation_store.py` docstring: explicit "this is a session log, not the Memory Engine" statement, cross-referencing Phase 3.1/3.2.
- [ ] `docs/STATUS.md` — Phase 2.2 (Conversation Engine) row updated to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium — the SQLite mechanics are simple; the discipline of *not* growing this into a memory system is the real engineering constraint.

## Estimated Development Time

1–1.5 days.

## Risks

- **Scope creep temptation**: it will be easy for a future sprint (or a well-meaning mid-implementation "improvement") to add a relevance/importance field here once Level 3 exists — explicitly flagged so any such addition is recognized as belonging to Sprint 3.1/3.2, not a natural extension of this table.
- **Sprint 3.1 layering decision** (whether `SqliteClient` is generic enough for config/scheduler too) is deferred, not resolved, by this sprint — re-confirm at Sprint 3.1 rather than assuming this sprint settled it.

## Next Sprint

2.8 — Context Manager.

## Sprint Completion Report (2026-07-17)

Delivered exactly the files this sprint's spec named:

- `database/sqlite_client.py` — `SqliteClient` (`connect`/`execute`/`query`/`close`), WAL mode enabled on connect, schema-agnostic per the spec.
- `voice/conversation_store.py` — `ConversationTurn` (dataclass), `ConversationSessionStore(ManagedModule)`.
- `voice/errors.py` — `ConversationStoreError(VoiceError)` added.
- `config/schema.py` — `DatabaseConfig.conversation_retention_days: int = 30`, validated (`> 0`) in `AppConfig._validate_paths()`; `config/defaults.yaml` updated to match. No `config/loader.py` change needed — `database` was already registered in `_SECTION_SCHEMAS` (Sprint 1.2), so the new field is picked up by file/env loading automatically (the exact step that was easy to forget, per this project's own Sprint 1.8 lesson — checked and confirmed not applicable here since only a *field*, not a new *section*, was added).
- `tests/unit/database/test_sqlite_client.py` (7 tests), `tests/unit/voice/test_conversation_store.py` (12 tests), plus one new test in `tests/unit/config/test_schema.py`. 197/197 tests passing project-wide (177 prior + 20 new), `ruff check .` clean.

**All Acceptance Criteria met**, each verified against a real SQLite file under `tmp_path` (no mocking of the persistence path itself, matching the spec's own "real save, real reload" framing):

- `record_turn()` → `get_recent_turns()` round-trip verified, including a genuine restart simulation (`test_turns_survive_a_simulated_restart`: a second, independent `SqliteClient` + `ConversationSessionStore` pair pointed at the same file, after the first pair's `stop()`).
- A failed write is caught and logged without raising (`test_record_turn_swallows_and_logs_a_write_failure`, via a small local `_RaisingSqliteClient` double — see Engineering Decisions below).
- `purge_older_than()` boundary behavior tested with three rows (well-within / just-under / just-over a 1-day retention window) — only the strictly-older row is removed, return value matches the removed count.
- No table other than `conversation_turns` is created; no relevance/importance/scoring column exists anywhere in this sprint's code.

**Two engineering decisions made during implementation, not fully specified by the sprint file, recorded here:**

1. **`get_recent_turns()` return order**: the spec didn't state whether results come back newest-first or oldest-first. Implemented as oldest-first (chronological) within the returned window — `SELECT ... ORDER BY timestamp DESC LIMIT ?` then reversed in Python — since the stated consumer (Context Manager, Sprint 2.8, per this file's own Data Flow) wants a directly-usable recent-transcript window, not a list it has to reverse itself. Documented in `get_recent_turns()`'s own docstring.
2. **`purge_older_than()`'s `days` parameter was given a default** (`int | None = None`, falling back to `database_config.conversation_retention_days`) rather than staying a bare required `int` as the spec's Expected Functions line literally shows. This is what actually gives the sprint's own `database_config: DatabaseConfig` constructor parameter a real, immediate use — without it, `database_config` would have been accepted but never read anywhere in this sprint's code, an "unused for now, forward-compatible" pattern this project has used before (`CoreManager.__init__`, Sprint 1.5) but only as a last resort. A caller can still pass `days` explicitly to override the configured default. `test_purge_older_than_defaults_to_configured_retention` covers the no-argument path.

**Boundary-test timing note**: the "just-under"/"just-over" purge tests use 1-minute margins around the 1-day retention boundary rather than millisecond-exact timestamps, to stay robust against normal test-execution jitter while still exercising the strict-less-than cutoff semantics ("exactly at the window" is kept, not purged). Documented inline in the test file.

**No real-hardware/model verification needed or run** — unlike the voice-pipeline sprints (2.1–2.6), this sprint's only external dependency is Python's stdlib `sqlite3` against a real file, which every test already exercises directly (no fake/mock stands in for SQLite itself; only the one write-failure-injection test uses a double, and only for the `execute()` call it needs to fail).

`docs/STATUS.md` updated: Phase 2.2 (Conversation Engine) is now **Designing** (this sprint done; 2.8 Context Manager onward still Planned). **Sprint 2.8 (Context Manager) is next.**

### Post-Sprint Fix (Technical Debt Resolution, 2026-07-28)

`purge_older_than()` had no caller anywhere in the codebase since this sprint shipped it — logged as `backlog/technical_debt.md` item 11, which named its own resolution as ready to apply without waiting for a Scheduler ("`ConversationSessionStore.start()` could adopt the identical one-line change today"). `start()` now calls `purge_older_than()` once, right after the table is created, mirroring `MemoryLifecycleManager.start()` (Sprint 3.12) and `ActionAuditLog.start()` (Sprint 4.8) exactly. 1 new regression test (`test_start_calls_purge_older_than_for_real`, `tests/unit/voice/test_conversation_store.py`), matching `test_action_log.py`'s own equivalent test. A true periodic cadence remains Level 4 Part B's Scheduler's job — this closes only the "zero callers" half of the gap, same honest scoping as its two precedents.
