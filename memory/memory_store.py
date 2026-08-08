"""MemoryStore — the foundational store/retrieve/delete layer every
memory-type wrapper (PersonaScopedMemory, EventMemory, ShortTermMemory;
Sprints 3.2-3.4) composes over.

Dual-backend: SQLite (database/sqlite_client.py's SqliteClient, reused
unchanged from Sprint 2.7 — resolves the layering question INDEX.md's
Recommendations flagged for this sprint) holds every MemoryRecord field as
the structured source of truth; ChromaDB (memory/chroma_client.py) holds
the same content's embedding for semantic search. A record is only ever
written to SQLite first, then Chroma — a Chroma failure is logged and does
NOT fail store(); the record still exists and is retrievable by id/recency,
just not yet semantically searchable. See sprint_3_1.md's Potential Risks
for why this dual-write has no distributed transaction.

This module knows nothing about which MemoryType means what (Shared vs.
Jarvis vs. Event, permanence, confidence scoring) — that is Sprints
3.2-3.6's job. It only stores and retrieves whatever MemoryRecord it is
given.

Sprint 3.14 (Integration Testing & Level Freeze) adversarial re-read
finding: every SQLite operation below now has explicit failure handling,
matching the Chroma-failure handling this class already had since Sprint
3.1/3.13 and its Level 2 sibling ConversationSessionStore's own SQLite
handling (Sprint 2.13). A write whose caller needs to know it didn't
happen (store()) raises a typed MemoryStoreError; a read that can
reasonably degrade to "nothing found" (get_by_id(), recent()) does so;
a best-effort update whose failure only means "stays stale until the
next pass" (update_confidence(), delete()) is logged and swallowed. See
sprint_3_14.md's own completion report for the full reasoning.
"""

from datetime import UTC, datetime
from typing import Protocol

from core.logging_setup import get_logger
from core.module_registry import ServiceState
from core.runtime_manager import RuntimeManager
from database.sqlite_client import SqliteClient
from memory.chroma_client import ChromaMemoryClient
from memory.errors import MemoryStoreError
from memory.models import MemoryRecord, MemoryType

logger = get_logger(__name__)


class MemoryStoreProtocol(Protocol):
    """Interface-first per 03_Engineering_Standards.md — every consumer
    that only ever reads/writes records (PersonaScopedMemory, EventMemory,
    ShortTermMemory, EmotionalMemory, PreferenceLearner) depends on this,
    never the concrete MemoryStore type, so Runtime Phase 6's
    LazyMemoryStore (below) is a drop-in substitute wherever MemoryStore
    used to be threaded through directly. MemoryLifecycleManager is the
    one deliberate exception — see LazyMemoryStore's own docstring for
    why it keeps a direct MemoryStore dependency instead."""

    def store(self, record: MemoryRecord) -> str: ...

    def get_by_id(self, record_id: str) -> MemoryRecord | None: ...

    def recent(self, memory_type: MemoryType, limit: int) -> list[MemoryRecord]: ...

    def semantic_search(
        self, memory_type: MemoryType, query_text: str, n_results: int
    ) -> list[tuple[MemoryRecord, float]]: ...

    def update_confidence(
        self,
        record_id: str,
        new_score: float,
        user_override: bool | None = None,
        band_entered_at: datetime | None = None,
    ) -> None: ...

    def delete(self, record_id: str) -> None: ...

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_records (
    id TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT,
    confidence_score REAL NOT NULL,
    is_permanent INTEGER NOT NULL,
    user_override INTEGER NOT NULL,
    source_session_id TEXT,
    occurred_at TEXT,
    created_at TEXT NOT NULL,
    last_accessed_at TEXT NOT NULL,
    band_entered_at TEXT NOT NULL,
    access_count INTEGER NOT NULL,
    emotional_significance REAL NOT NULL DEFAULT 0.0
)
"""

# Sprint 5.3 (Emotional Memory) migration: CREATE TABLE IF NOT EXISTS above
# only creates emotional_significance for a brand-new database — it does
# NOT retroactively add the column to an already-existing on-disk
# memory_records table (this project's real, standing database/jarminei.db
# among them). ALTER TABLE ADD COLUMN has no IF NOT EXISTS in SQLite, so
# start() below runs it unconditionally and swallows only the specific
# "duplicate column" failure that means it already ran — see start()'s own
# docstring.
_MIGRATE_ADD_EMOTIONAL_SIGNIFICANCE_SQL = (
    "ALTER TABLE memory_records ADD COLUMN emotional_significance REAL NOT NULL DEFAULT 0.0"
)

_SELECT_COLUMNS = (
    "id, memory_type, content, category, confidence_score, is_permanent, "
    "user_override, source_session_id, occurred_at, created_at, last_accessed_at, "
    "band_entered_at, access_count, emotional_significance"
)


class MemoryStore:
    """Constructor DI per 03_Engineering_Standards.md: receives the
    SqliteClient and ChromaMemoryClient it depends on rather than
    constructing either itself."""

    def __init__(self, sqlite_client: SqliteClient, chroma_client: ChromaMemoryClient) -> None:
        self._sqlite_client = sqlite_client
        self._chroma_client = chroma_client
        self._started = False
        # Runtime Phase 6 (Runtime Refactor Sprint) — LazyModule Protocol
        # additions (core/module_registry.py). Unlike WhisperSpeechToText/
        # CoquiTextToSpeech (Runtime Phase 5), state() deliberately does
        # NOT distinguish ACTIVE from READY here: every public method
        # below (store/get_by_id/recent/semantic_search/update_confidence/
        # delete) is a fast SQLite/Chroma call, not a multi-second
        # blocking inference — the mid-request eviction race Runtime
        # Phase 9 must guard against for STT/TTS is a much smaller,
        # narrower window here. Revisit only if a real eviction-during-a-
        # memory-call bug is ever actually observed.
        self._last_used_at: datetime | None = None
        self._idle_timeout_seconds: float | None = None

    def start(self) -> None:
        """Open both backends and ensure the memory_records table and all
        five Chroma collections exist (idempotent).

        Sprint 5.3 (Emotional Memory): also runs a one-off, idempotent
        column migration for emotional_significance — real, necessary for
        any on-disk database created before this sprint (CREATE TABLE IF
        NOT EXISTS is a no-op against an already-existing table, so a
        pre-existing memory_records table would otherwise never gain the
        new column and every subsequent store() would fail). A "duplicate
        column" failure means the migration already ran (or the table was
        just freshly created with the column already present) and is
        swallowed; any other failure is a genuine problem and re-raised."""
        try:
            self._sqlite_client.connect()
            self._sqlite_client.execute(_CREATE_TABLE_SQL)
            self._migrate_add_emotional_significance_column()
            self._chroma_client.connect()
            self._chroma_client.ensure_collections()
        except Exception as exc:
            raise MemoryStoreError(f"Failed to start memory store: {exc}") from exc
        self._started = True
        logger.info("Memory store started.")

    def _migrate_add_emotional_significance_column(self) -> None:
        try:
            self._sqlite_client.execute(_MIGRATE_ADD_EMOTIONAL_SIGNIFICANCE_SQL)
        except Exception as exc:
            if "duplicate column" not in str(exc).lower():
                raise

    def stop(self) -> None:
        self._sqlite_client.close()
        self._chroma_client.close()
        self._started = False
        logger.info("Memory store stopped.")

    def health_check(self) -> bool:
        """Started AND both backends still respond — a real liveness
        check, not just a "was start() called" flag."""
        if not self._started:
            return False
        try:
            self._sqlite_client.query("SELECT 1")
        except Exception:
            logger.exception("Memory store health check: SQLite query failed.")
            return False
        return self._chroma_client.health_check()

    def state(self) -> ServiceState:
        """LazyModule Protocol (Runtime Phase 6). NOT_LOADED before
        start()/after stop() — never reported as "unhealthy" just for
        being unloaded, a distinct, expected state, not a failure. READY
        once started (see this class's own __init__ docstring for why no
        separate ACTIVE state is tracked)."""
        return ServiceState.READY if self._started else ServiceState.NOT_LOADED

    def last_used_at(self) -> datetime | None:
        """LazyModule Protocol (Runtime Phase 6) — Runtime Phase 9's own
        idle-timeout sweep is the real reader; None until the first real
        store()/get_by_id()/recent()/semantic_search()/update_confidence()/
        delete() call."""
        return self._last_used_at

    def mark_idle_timeout(self, seconds: float) -> None:
        """LazyModule Protocol (Runtime Phase 6) — stored for Runtime
        Phase 9's idle-timeout sweep to read; nothing in this class acts
        on it yet."""
        self._idle_timeout_seconds = seconds

    def store(self, record: MemoryRecord) -> str:
        """Persist record to SQLite (source of truth), then attempt its
        Chroma embedding. A Chroma failure is logged and does not raise —
        see this module's own docstring.

        Sprint 3.14 (Integration Testing & Level Freeze) adversarial
        re-read finding: the SQLite INSERT itself previously had no
        failure handling at all, unlike ConversationSessionStore.
        record_turn() (its Level 2 sibling, Sprint 2.13) — a caller
        receiving back a record.id for a row that was never actually
        persisted would be silently working with a fake reference, worse
        than raising. A write failure here now raises MemoryStoreError
        (never a raw sqlite3 exception, per Interface First Design) rather
        than either silently swallowing it or leaking an implementation-
        specific error type."""
        self._last_used_at = datetime.now(UTC)
        try:
            self._sqlite_client.execute(
                f"INSERT INTO memory_records ({_SELECT_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.memory_type.value,
                    record.content,
                    record.category,
                    record.confidence_score,
                    int(record.is_permanent),
                    int(record.user_override),
                    record.source_session_id,
                    record.occurred_at.isoformat() if record.occurred_at else None,
                    record.created_at.isoformat(),
                    record.last_accessed_at.isoformat(),
                    record.band_entered_at.isoformat(),
                    record.access_count,
                    record.emotional_significance,
                ),
            )
        except Exception as exc:
            raise MemoryStoreError(f"Failed to store memory record {record.id}: {exc}") from exc
        try:
            self._chroma_client.add_embedding(record.memory_type, record.id, record.content)
        except Exception:
            logger.exception(
                "Failed to embed memory record %s; row persisted but not semantically searchable.",
                record.id,
            )
        return record.id

    def get_by_id(self, record_id: str) -> MemoryRecord | None:
        """Return the record, or None if it doesn't exist. Also bumps
        access_count and last_accessed_at — every read is itself a signal
        Sprint 3.5's Dynamic Memory Formula consumes.

        Sprint 3.14 hardening: a SQLite failure (either the SELECT or the
        access_count/last_accessed_at UPDATE) is logged and degrades to
        None — the same "nothing found" outcome as a genuinely-missing
        record, per this module's own established Fail Gracefully
        convention (semantic_search()'s Chroma-failure handling, Sprint
        3.13). Callers throughout memory/ already treat None as a normal,
        expected outcome (e.g. MemoryLifecycleManager.apply_user_
        override()), so no caller needed to change for this."""
        self._last_used_at = datetime.now(UTC)
        try:
            rows = self._sqlite_client.query(
                f"SELECT {_SELECT_COLUMNS} FROM memory_records WHERE id = ?",
                (record_id,),
            )
            if not rows:
                return None
            record = _row_to_record(rows[0])
            record.access_count += 1
            record.last_accessed_at = datetime.now(UTC)
            self._sqlite_client.execute(
                "UPDATE memory_records SET access_count = ?, last_accessed_at = ? WHERE id = ?",
                (record.access_count, record.last_accessed_at.isoformat(), record.id),
            )
        except Exception:
            logger.exception("Failed to read memory record %s; treating as not found.", record_id)
            return None
        return record

    def recent(self, memory_type: MemoryType, limit: int) -> list[MemoryRecord]:
        """Plain recency query, no embedding involved. Newest first.

        Sprint 3.14 hardening: a SQLite failure degrades to an empty
        list rather than raising — every caller of this method (Event
        Memory's list_milestones(), Short-Term Memory's active_context_
        memories(), MemoryLifecycleManager's own cleanup/review passes)
        already treats "no records" as a normal, valid outcome."""
        self._last_used_at = datetime.now(UTC)
        try:
            rows = self._sqlite_client.query(
                f"SELECT {_SELECT_COLUMNS} FROM memory_records "
                "WHERE memory_type = ? ORDER BY created_at DESC LIMIT ?",
                (memory_type.value, limit),
            )
        except Exception:
            logger.exception("Failed to read recent memory records for type=%s.", memory_type.value)
            return []
        return [_row_to_record(row) for row in rows]

    def semantic_search(
        self, memory_type: MemoryType, query_text: str, n_results: int
    ) -> list[tuple[MemoryRecord, float]]:
        """The single-type retrieval primitive: ChromaMemoryClient.query()
        for nearest-neighbor (id, distance) pairs, then SQLite hydration,
        returned as (record, distance) pairs in Chroma's similarity order
        (lowest distance = most similar, first). Callers that don't need
        the raw distance can discard it with `for record, _ in results`.

        Distance is exposed (not hidden as originally shipped — see
        docs/sprint_book/sprint_3_1.md's Post-Sprint Fix) specifically so
        a caller combining results from more than one MemoryType/collection
        (PersonaScopedMemory.recall_for_persona(), Sprint 3.2; the future
        MemoryRetrievalEngine, Sprint 3.9) can genuinely rank the merged
        set by similarity rather than only being able to interleave
        already-separately-ordered lists.

        A degraded/unavailable Chroma backend returns an empty list
        rather than raising — an empty result is a normal "nothing
        relevant found" outcome to every caller of this method. Sprint
        3.13 (Error Handling & Recovery Hardening) reviewed and confirmed
        this behavior under a real induced failure (a local double whose
        query() genuinely raises, not just a pre-built exception
        asserted against) — see
        tests/unit/memory/test_memory_store.py's own
        test_semantic_search_returns_empty_list_on_a_chroma_query_failure
        and tests/integration/test_decision_engine_hardening.py's
        full-turn-level confirmation. store()'s own Chroma-failure
        handling below (Sprint 3.1) was reviewed the same way and found
        already correct — no code change was needed for either method."""
        self._last_used_at = datetime.now(UTC)
        try:
            hits = self._chroma_client.query(memory_type, query_text, n_results)
        except Exception:
            logger.exception(
                "Semantic search failed for memory_type=%s; returning no results.",
                memory_type.value,
            )
            return []
        results = []
        for record_id, distance in hits:
            record = self.get_by_id(record_id)
            if record is not None:
                results.append((record, distance))
        return results

    def update_confidence(
        self,
        record_id: str,
        new_score: float,
        user_override: bool | None = None,
        band_entered_at: datetime | None = None,
    ) -> None:
        """Persist a recomputed confidence_score (Sprint 3.5) and,
        optionally, a new user_override flag and/or band_entered_at
        (Sprint 3.6, on an actual band transition — see MemoryRecord's
        own docstring). Leaves whichever of the two isn't supplied
        unchanged.

        Sprint 3.14 hardening: a SQLite failure is logged and swallowed
        rather than raised — a best-effort write, the same convention
        ConversationSessionStore.record_turn() established (Sprint 2.7):
        a record simply keeps its previous score/band until the next
        successful rescoring pass, rather than aborting the caller
        (MemoryLifecycleManager's own per-record try/except already adds
        a second layer of isolation on top of this one)."""
        self._last_used_at = datetime.now(UTC)
        set_clauses = ["confidence_score = ?"]
        params: list[object] = [new_score]
        if user_override is not None:
            set_clauses.append("user_override = ?")
            params.append(int(user_override))
        if band_entered_at is not None:
            set_clauses.append("band_entered_at = ?")
            params.append(band_entered_at.isoformat())
        params.append(record_id)
        try:
            self._sqlite_client.execute(
                f"UPDATE memory_records SET {', '.join(set_clauses)} WHERE id = ?",
                tuple(params),
            )
        except Exception:
            logger.exception("Failed to update confidence for memory record %s.", record_id)

    def delete(self, record_id: str) -> None:
        """Remove from both SQLite and Chroma. Looks up the record's
        MemoryType via a plain read (not get_by_id(), which would bump
        access_count/last_accessed_at on a record about to be deleted).

        Sprint 3.14 hardening: a SQLite failure (the lookup or the
        DELETE itself) is logged and swallowed rather than raised — a
        record that fails to delete now simply remains and is
        reconsidered on the next cleanup pass (MemoryLifecycleManager's
        run_cleanup_pass(), Sprint 3.6), the same "stays around, tried
        again later" degrade already accepted for the grace-period
        design generally."""
        self._last_used_at = datetime.now(UTC)
        try:
            rows = self._sqlite_client.query(
                "SELECT memory_type FROM memory_records WHERE id = ?", (record_id,)
            )
            self._sqlite_client.execute("DELETE FROM memory_records WHERE id = ?", (record_id,))
        except Exception:
            logger.exception("Failed to delete memory record %s from SQLite.", record_id)
            return
        if rows:
            memory_type = MemoryType(rows[0][0])
            try:
                self._chroma_client.delete_embedding(memory_type, record_id)
            except Exception:
                logger.exception(
                    "Failed to delete Chroma embedding for memory record %s "
                    "(SQLite row already removed).",
                    record_id,
                )


class LazyMemoryStore:
    """MemoryStoreProtocol implementation that defers to a real, already-
    registered LazyModule (MemoryStore in production), calling
    RuntimeManager.ensure_started() before every method so the real
    chromadb import + PersistentClient construction + SQLite connect
    happens on first genuine memory access — or whenever a background
    warm-up thread gets to it first (Runtime Phase 4) — rather than at
    CoreManager startup time.

    Every wrapper class that depends on MemoryStore today (PersonaScopedMemory,
    EventMemory, ShortTermMemory, EmotionalMemory, PreferenceLearner)
    receives this proxy instead of the real MemoryStore in main.py — none
    of them need to change, since this class exposes the identical six
    public methods MemoryStore does (MemoryStoreProtocol, above).

    MemoryLifecycleManager is the one deliberate exception: it keeps a
    direct MemoryStore dependency, not this proxy, because its own
    start() is guaranteed by CoreManager's own tier-plus-registration-
    order sequencing to run only after the real MemoryStore.start()
    already has (same WARM tier, registered immediately after it, per
    main.py's own _register_level3_modules()) — threading a second,
    redundant lazy gate through it would be pure duplication, not a
    correctness need.
    """

    def __init__(
        self, real_store: MemoryStore, service_name: str, runtime_manager: RuntimeManager
    ) -> None:
        self._real_store = real_store
        self._service_name = service_name
        self._runtime_manager = runtime_manager

    def store(self, record: MemoryRecord) -> str:
        self._runtime_manager.ensure_started(self._service_name)
        return self._real_store.store(record)

    def get_by_id(self, record_id: str) -> MemoryRecord | None:
        self._runtime_manager.ensure_started(self._service_name)
        return self._real_store.get_by_id(record_id)

    def recent(self, memory_type: MemoryType, limit: int) -> list[MemoryRecord]:
        self._runtime_manager.ensure_started(self._service_name)
        return self._real_store.recent(memory_type, limit)

    def semantic_search(
        self, memory_type: MemoryType, query_text: str, n_results: int
    ) -> list[tuple[MemoryRecord, float]]:
        self._runtime_manager.ensure_started(self._service_name)
        return self._real_store.semantic_search(memory_type, query_text, n_results)

    def update_confidence(
        self,
        record_id: str,
        new_score: float,
        user_override: bool | None = None,
        band_entered_at: datetime | None = None,
    ) -> None:
        self._runtime_manager.ensure_started(self._service_name)
        self._real_store.update_confidence(record_id, new_score, user_override, band_entered_at)

    def delete(self, record_id: str) -> None:
        self._runtime_manager.ensure_started(self._service_name)
        self._real_store.delete(record_id)


def _row_to_record(row: tuple) -> MemoryRecord:
    return MemoryRecord(
        id=row[0],
        memory_type=MemoryType(row[1]),
        content=row[2],
        category=row[3],
        confidence_score=row[4],
        is_permanent=bool(row[5]),
        user_override=bool(row[6]),
        source_session_id=row[7],
        occurred_at=datetime.fromisoformat(row[8]) if row[8] else None,
        created_at=datetime.fromisoformat(row[9]),
        last_accessed_at=datetime.fromisoformat(row[10]),
        band_entered_at=datetime.fromisoformat(row[11]),
        access_count=row[12],
        emotional_significance=row[13],
    )
