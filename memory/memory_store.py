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
"""

from datetime import UTC, datetime

from core.logging_setup import get_logger
from database.sqlite_client import SqliteClient
from memory.chroma_client import ChromaMemoryClient
from memory.errors import MemoryStoreError
from memory.models import MemoryRecord, MemoryType

logger = get_logger(__name__)

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
    access_count INTEGER NOT NULL
)
"""

_SELECT_COLUMNS = (
    "id, memory_type, content, category, confidence_score, is_permanent, "
    "user_override, source_session_id, occurred_at, created_at, last_accessed_at, "
    "band_entered_at, access_count"
)


class MemoryStore:
    """Constructor DI per 03_Engineering_Standards.md: receives the
    SqliteClient and ChromaMemoryClient it depends on rather than
    constructing either itself."""

    def __init__(self, sqlite_client: SqliteClient, chroma_client: ChromaMemoryClient) -> None:
        self._sqlite_client = sqlite_client
        self._chroma_client = chroma_client
        self._started = False

    def start(self) -> None:
        """Open both backends and ensure the memory_records table and all
        five Chroma collections exist (idempotent)."""
        try:
            self._sqlite_client.connect()
            self._sqlite_client.execute(_CREATE_TABLE_SQL)
            self._chroma_client.connect()
            self._chroma_client.ensure_collections()
        except Exception as exc:
            raise MemoryStoreError(f"Failed to start memory store: {exc}") from exc
        self._started = True
        logger.info("Memory store started.")

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

    def store(self, record: MemoryRecord) -> str:
        """Persist record to SQLite (source of truth), then attempt its
        Chroma embedding. A Chroma failure is logged and does not raise —
        see this module's own docstring."""
        self._sqlite_client.execute(
            f"INSERT INTO memory_records ({_SELECT_COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            ),
        )
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
        Sprint 3.5's Dynamic Memory Formula consumes."""
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
        return record

    def recent(self, memory_type: MemoryType, limit: int) -> list[MemoryRecord]:
        """Plain recency query, no embedding involved. Newest first."""
        rows = self._sqlite_client.query(
            f"SELECT {_SELECT_COLUMNS} FROM memory_records "
            "WHERE memory_type = ? ORDER BY created_at DESC LIMIT ?",
            (memory_type.value, limit),
        )
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
        (Sprint 3.13 hardens this explicitly) rather than raising — an
        empty result is a normal "nothing relevant found" outcome to every
        caller of this method."""
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
        unchanged."""
        set_clauses = ["confidence_score = ?"]
        params: list[object] = [new_score]
        if user_override is not None:
            set_clauses.append("user_override = ?")
            params.append(int(user_override))
        if band_entered_at is not None:
            set_clauses.append("band_entered_at = ?")
            params.append(band_entered_at.isoformat())
        params.append(record_id)
        self._sqlite_client.execute(
            f"UPDATE memory_records SET {', '.join(set_clauses)} WHERE id = ?",
            tuple(params),
        )

    def delete(self, record_id: str) -> None:
        """Remove from both SQLite and Chroma. Looks up the record's
        MemoryType via a plain read (not get_by_id(), which would bump
        access_count/last_accessed_at on a record about to be deleted)."""
        rows = self._sqlite_client.query(
            "SELECT memory_type FROM memory_records WHERE id = ?", (record_id,)
        )
        self._sqlite_client.execute("DELETE FROM memory_records WHERE id = ?", (record_id,))
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
    )
