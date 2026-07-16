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
