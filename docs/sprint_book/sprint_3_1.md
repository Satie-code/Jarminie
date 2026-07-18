# Sprint 3.1 — Memory Store Foundation

## Sprint ID

3.1

## Sprint Name

Memory Store Foundation

## Purpose

Begin Phase 3.1 (Memory Engine) by building the foundational persistence layer every memory-type sprint (3.2–3.4) builds on: a SQLite schema for structured memory metadata and a ChromaDB client for semantic embeddings, per [03_Engineering_Standards.md](../03_Engineering_Standards.md)'s Technology Stack ("Semantic Memory: ChromaDB — Semantic retrieval, conversation memory, context search, long-term knowledge") and [02_System_Architecture.md](../02_System_Architecture.md)'s Memory Architecture (five layers: Shared, Jarvis, Minie, Event, Short-Term).

## Engineering Rationale

[sprint_book/INDEX.md](INDEX.md) already flagged the open question this sprint must resolve: *"`database/` (SQLite layer) is first exercised in Sprint 3.1 but `config/` (Sprint 1.2) and `scheduler` (Sprint 4.8) also need persistent storage — worth deciding at Sprint 3.1 whether the SQLite access layer is generic enough to serve all three."* It already is — Sprint 2.7 built `database/sqlite_client.py`'s `SqliteClient` deliberately schema-agnostic ("no knowledge of what tables exist... schema ownership belongs to each caller"), and `ConversationSessionStore` already proved the pattern by owning its own table DDL. This sprint reuses `SqliteClient` unchanged and the same `sqlite_path` database file, adding a new `memory_records` table via the same idempotent `CREATE TABLE IF NOT EXISTS` convention — resolving that flagged recommendation rather than building a second, competing database-access layer.

`DatabaseConfig.chroma_path` has existed since Sprint 1.2 as a forward-looking stub specifically for this sprint. ChromaDB requires an embedding function; rather than routing every memory write through Ollama (`ModelConfig.ollama_model`, reserved for Decision Engine reasoning in Sprint 3.7+), this sprint uses ChromaDB's own default local embedding function (`all-MiniLM-L6-v2` via `sentence-transformers`, bundled with `chromadb`). This is a real, load-bearing decision recorded here rather than assumed silently: it keeps the Memory Engine's only new hard dependency scoped to `chromadb` itself (already tracked in `backlog/technical_debt.md` item 1 as "Remaining: `chromadb` (Phase 3.1)"), keeps memory embedding available even before Ollama is confirmed running, and keeps Single Responsibility intact — semantic *storage* does not depend on the *reasoning* runtime. If embedding quality proves inadequate once real usage exists, swapping the embedding function is an internal `ChromaMemoryClient` change, not a ripple through every memory-type sprint (Interface First Design).

This sprint stores and retrieves generic `MemoryRecord`s; it does not implement any of the five memory layers' specific rules (ownership scoping, permanence, expiry) — those are Sprints 3.2–3.4. It also does not implement confidence *scoring* (Sprint 3.5) — it only persists the `confidence_score` field so later sprints have somewhere to write it.

## Objectives

- A `MemoryRecord` dataclass and `MemoryType` enum covering all five Part 2 memory layers, used unchanged by every subsequent Level 3 sprint.
- A `ChromaMemoryClient` wrapping a persistent ChromaDB client with one collection per `MemoryType`.
- A `MemoryStore(ManagedModule)` providing the base store/retrieve/delete primitives every memory-type wrapper (3.2–3.4) composes over — never subclassed or duplicated.
- Per-type semantic search accurate enough to satisfy Phase 3.1's "Retrieval accurate" acceptance criterion at the storage level (cross-type, decision-ready retrieval is Sprint 3.9's job).

## Prerequisites

Sprints 1.2, 1.5, 2.7 complete.

## Dependencies

1.2 (Configuration Manager — `DatabaseConfig`), 1.5 (Core Manager — `ManagedModule`), 2.7 (`database/sqlite_client.py`'s `SqliteClient`)

## Files to Create

- `memory/__init__.py`
- `memory/models.py` — `MemoryType` (Enum), `MemoryRecord` (dataclass).
- `memory/chroma_client.py` — `ChromaMemoryClient`.
- `memory/errors.py` — `MemoryError(Exception)`, `MemoryStoreError(MemoryError)`.
- `memory/memory_store.py` — `MemoryStore(ManagedModule)`.
- `tests/unit/memory/test_chroma_client.py`
- `tests/unit/memory/test_memory_store.py`

## Files to Modify

- `config/schema.py` — add `MemoryConfig` dataclass: `chroma_collection_prefix: str = "jarminei_memory"`. Register `memory` in `AppConfig` and `_SECTION_SCHEMAS` (Sprint 1.2's loader picks up new sections automatically once registered, per the precedent already confirmed in Sprint 2.7).
- `config/defaults.yaml` — add the `memory` section matching `MemoryConfig`'s defaults.

## Expected Classes

- `MemoryType` (Enum) — `SHARED`, `JARVIS`, `MINIE`, `EVENT`, `SHORT_TERM`. Declaration order has no priority meaning here (unlike `SwitchReason`/`PriorityLevel` elsewhere in this book) — it is a plain classification.
- `MemoryRecord` (dataclass) — `id: str` (UUID4, generated on creation), `memory_type: MemoryType`, `content: str`, `category: str | None`, `confidence_score: float = 0.0` (written by Sprint 3.5; this sprint only persists the field), `is_permanent: bool = False` (set `True` only by Event Memory, Sprint 3.3 — added to the dataclass now so Sprint 3.6's Lifecycle Manager has a single, unambiguous field to check rather than inferring permanence from confidence, which would conflate two different guarantees), `user_override: bool = False` (User Override Rule — set by Sprint 3.5/3.6), `created_at: datetime`, `last_accessed_at: datetime`, `access_count: int = 0`, `source_session_id: str | None = None`.
- `ChromaMemoryClient` — constructor DI: `(memory_config: MemoryConfig, database_config: DatabaseConfig)`. Owns one `chromadb.PersistentClient(path=database_config.chroma_path)` and lazily-created collections named `f"{memory_config.chroma_collection_prefix}_{memory_type.value}"`.
- `MemoryStore(ManagedModule)` — constructor DI: `(sqlite_client: SqliteClient, chroma_client: ChromaMemoryClient)`.

## Expected Interfaces

- `ManagedModule` (reused, Sprint 1.5) — `start()` ensures the `memory_records` SQLite table exists and all five Chroma collections exist (idempotent); `stop()` closes the SQLite connection (the Chroma `PersistentClient` has no explicit close — documented as a deliberate no-op in `stop()`, not an oversight); `health_check()` confirms both the SQLite connection and the Chroma client are reachable, degrading (not raising) per Sprint 3.13's later hardening — this sprint implements the happy path, 3.13 hardens the failure path.

## Expected Functions

- `ChromaMemoryClient.add_embedding(memory_type: MemoryType, record_id: str, content: str) -> None`
- `ChromaMemoryClient.query(memory_type: MemoryType, query_text: str, n_results: int) -> list[tuple[str, float]]` — returns `(record_id, distance)` pairs; the caller (`MemoryStore`) resolves ids back to full records via SQLite.
- `ChromaMemoryClient.delete_embedding(memory_type: MemoryType, record_id: str) -> None`
- `MemoryStore.store(record: MemoryRecord) -> str` — writes the SQLite row first (the structured source of truth), then attempts the Chroma embedding; a Chroma failure is logged and does **not** fail the call — the record still exists and is retrievable by id/recency, just not yet semantically searchable (Fail Gracefully; full reconciliation is a Future Consideration, not built here).
- `MemoryStore.get_by_id(record_id: str) -> MemoryRecord | None` — also increments `access_count` and updates `last_accessed_at` (every read is itself a signal Sprint 3.5's Dynamic Memory Formula consumes).
- `MemoryStore.recent(memory_type: MemoryType, limit: int) -> list[MemoryRecord]` — plain recency query, no embedding involved.
- `MemoryStore.semantic_search(memory_type: MemoryType, query_text: str, n_results: int) -> list[MemoryRecord]` — the single-type retrieval primitive: `ChromaMemoryClient.query()` then SQLite hydration, in Chroma's similarity order.
- `MemoryStore.update_confidence(record_id: str, new_score: float, user_override: bool | None = None) -> None` — used by Sprint 3.5; not called by anything in this sprint.
- `MemoryStore.delete(record_id: str) -> None` — removes from both SQLite and Chroma.

## Data Flow

```
content (from a memory-type wrapper, 3.2–3.4)
      ↓
MemoryStore.store(MemoryRecord(...))
      ↓                              ↓
SqliteClient.execute(INSERT ...)   ChromaMemoryClient.add_embedding(...)
      ↓                              ↓
   memory_records row           Chroma collection vector
      ↓
   (later) MemoryStore.semantic_search(memory_type, query_text)
      ↓
ChromaMemoryClient.query() → (id, distance)[]
      ↓
SQLite hydration → MemoryRecord[] → Sprint 3.9's Memory Retrieval Engine
```

## Implementation Tasks

1. `memory/models.py` — `MemoryType`, `MemoryRecord`.
2. `memory/chroma_client.py` — `ChromaMemoryClient`, collection-per-type management.
3. `memory/memory_store.py` — `MemoryStore(ManagedModule)`, SQLite DDL, dual-write `store()`, hydration-based `semantic_search()`.
4. `config/schema.py` — `MemoryConfig`; register in `AppConfig`/`_SECTION_SCHEMAS`; `config/defaults.yaml` updated to match.
5. Unit tests against a real temp-file SQLite database and a real temp-directory ChromaDB `PersistentClient` (no mocking of the persistence path itself — the established convention since Sprint 2.7).

## Architecture Notes

`MemoryStore` is intentionally the *only* class in this sprint that knows both SQLite and ChromaDB exist — every later sprint (3.2–3.11) depends on `MemoryStore`'s interface, never on `SqliteClient` or `ChromaMemoryClient` directly (Interface First Design, same discipline as `ConversationSessionStore` hiding `SqliteClient` from `ContextManager`). `memory/` is a new top-level package, matching [03_Engineering_Standards.md](../03_Engineering_Standards.md)'s Repository Structure, which already names it.

## Integration Considerations

- Nothing in Level 2 changes — `voice/conversation_store.py` remains the session-log mechanism it was built as; `memory/memory_store.py` is a separate table in the same SQLite file, not a replacement.
- `ModelConfig.ollama_model` is untouched by this sprint — embeddings and LLM reasoning are deliberately separate concerns until Sprint 3.7 needs the latter.
- This sprint's `MemoryStore` is the dependency every one of Sprints 3.2, 3.3, 3.4, 3.5, 3.6, and 3.9 lists first.

## Potential Risks

- **SQLite/Chroma dual-write has no distributed transaction** — a crash between the two writes can leave a SQLite row with no matching embedding (never the reverse, since SQLite is written first). Accepted as a known limitation for a local-first single-user system; a startup reconciliation pass is flagged as a Future Consideration, not built now (avoids premature generality against a failure mode with no evidence of being common).
- **ChromaDB's default embedding model is a real, if modest, dependency and startup-time cost** (`sentence-transformers` model load) — tracked in `backlog/technical_debt.md` item 1; first real installation/verification happens during this sprint's implementation, same as `coqui-tts`/`openwakeword` were for Level 2.
- **`is_permanent` and `user_override` fields are unused by any real logic in this sprint** — deliberately added to the dataclass now (not bolted on later) so Sprints 3.3, 3.5, and 3.6 never need to modify this sprint's schema, matching the "config/DI parameter accepted now, used later" pattern already established (`CoreManager.config`, Sprint 1.5; `ConversationSessionStore.database_config`, Sprint 2.7).

## Acceptance Criteria

- `store()` persists a record retrievable via `get_by_id()` after a simulated restart (new `SqliteClient`/`ChromaMemoryClient` instances, same files).
- `semantic_search()` ranks an obviously-related fixture string above an obviously-unrelated one for a fixed small test corpus, per `MemoryType`.
- All five Chroma collections and the `memory_records` table exist after `start()`, idempotently (calling `start()` twice does not error or duplicate).
- A Chroma write failure during `store()` is logged and does not raise — the SQLite row still exists and `get_by_id()` still returns it.

## Testing Checklist

- [ ] Unit: `MemoryRecord`/`MemoryType` construction and defaults.
- [ ] Unit: `ChromaMemoryClient` add/query/delete round-trip against a real temp-directory `PersistentClient`.
- [ ] Unit: `MemoryStore.store()` → `get_by_id()` round-trip, including a restart simulation.
- [ ] Unit: `MemoryStore.semantic_search()` ranking against a fixed small corpus.
- [ ] Unit: `MemoryStore.recent()` ordering and limit boundary.
- [ ] Unit: a Chroma write failure during `store()` is caught, logged, and the SQLite row still exists.
- [ ] Unit: `AppConfig` loads the new `memory` section with correct defaults.

## Documentation Checklist

- [ ] `memory/memory_store.py` docstring: explicit statement that this is the generic foundation only — memory-type rules (scoping, permanence, expiry) belong to Sprints 3.2–3.4, not here.
- [ ] `memory/chroma_client.py` docstring: records the embedding-function decision (ChromaDB default local embedding, not Ollama) and why.
- [ ] `docs/STATUS.md` — Phase 3.1 (Memory Engine) row updated to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High — the mechanics are well-precedented by `ConversationSessionStore`, but this is the project's first dual-backend (SQL + vector) persistence module, and the first real `chromadb` integration.

## Estimated Development Time

1.5–2 days.

## Next Sprint

3.2 — Shared Memory & Persona Memory.

## Future Considerations

- A startup reconciliation pass for SQLite rows with no matching Chroma embedding (see Potential Risks) — build only if real usage shows orphaned rows are a genuine, recurring problem.
- Revisit the embedding-function choice if real retrieval quality (once Sprint 3.9/3.14 exercise it against real conversation content) proves the default local model insufficient.
