"""Pattern Store — persistent storage for LearnedPatterns, including
upsert-by-identity. See docs/sprint_book/sprint_5/sprint_5_21.md.

Owns its own single-table DDL (learned_patterns) against the shared
SqliteClient, following UsageStore's/CalendarStore's/WorkflowStore's own
"caller owns its own DDL" precedent — no second database-access layer
invented.

A dedicated store, not a sixth memory/models.py MemoryType, a real
modeling decision made explicitly at this sprint's own Engineering
Rationale: MemoryType (SHARED/JARVIS/MINIE/EVENT/SHORT_TERM) has been a
locked, small set since Sprint 3.1, and ConfidenceScorer's/
PersonaScopedMemory's own scoring/scoping rules are written specifically
around those five — a LearnedPattern is a conceptually different kind of
record (a learned statistical fact, not a conversational memory), so a
small, independent store (the same shape UsageStore/CalendarStore already
use) serves this sprint's own real need without a cross-cutting change to
Level 3's own frozen architecture.

upsert()'s identity is (pattern_type, subject), enforced by this table's
own UNIQUE constraint and a real SQL upsert (INSERT ... ON CONFLICT(...)
DO UPDATE SET ...) rather than a SELECT-then-INSERT-or-UPDATE round trip:
on a genuinely new (pattern_type, subject) pair, every column from the
incoming LearnedPattern is inserted as-is; on a conflict against an
already-stored pair, only description/confidence/evidence_count/
last_updated_at are overwritten — pattern_id and first_observed_at are
deliberately left out of the DO UPDATE SET clause, so the existing row's
own original values survive untouched. This is what lets
PatternRecognizer always construct a brand-new LearnedPattern (with a
fresh pattern_id/first_observed_at="now") on every single detection pass
without ever duplicating a row or losing a pattern's own true
first-detected timestamp.

Sprint 5.25 hardening (scenario b): list_by_type()/list_all() degrade to
[] on a real SQLite failure, matching CalendarStore.list_due_within()'s/
UsageStore.list_samples_since()'s own precedent — their real callers
(Sprint 5.21's PatternRecognizer counter-model reads, Sprint 5.23's
RecommendationEngine, Sprint 5.24's live wellness-turn/TaskScheduler call
sites) already treat "no patterns found" as an ordinary, valid input.
upsert() (the write path) is deliberately left unwrapped, the same
"wrapping the write path here would risk a false success the caller
never actually got" reasoning CalendarStore.save() already established.
"""

from __future__ import annotations

from datetime import datetime

from core.logging_setup import get_logger
from database.sqlite_client import SqliteClient
from learning.pattern_model import LearnedPattern, PatternType

logger = get_logger(__name__)

_CREATE_LEARNED_PATTERNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS learned_patterns (
    pattern_id TEXT PRIMARY KEY,
    pattern_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_count INTEGER NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    UNIQUE(pattern_type, subject)
)
"""

_UPSERT_SQL = """
INSERT INTO learned_patterns
    (pattern_id, pattern_type, subject, description, confidence,
     evidence_count, first_observed_at, last_updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(pattern_type, subject) DO UPDATE SET
    description = excluded.description,
    confidence = excluded.confidence,
    evidence_count = excluded.evidence_count,
    last_updated_at = excluded.last_updated_at
"""

_SELECT_COLUMNS = (
    "pattern_id, pattern_type, subject, description, confidence, "
    "evidence_count, first_observed_at, last_updated_at"
)


class PatternStore:
    """Constructor DI: (sqlite_client,)."""

    def __init__(self, sqlite_client: SqliteClient) -> None:
        self._sqlite_client = sqlite_client
        self._started = False

    def start(self) -> None:
        self._sqlite_client.connect()
        self._sqlite_client.execute(_CREATE_LEARNED_PATTERNS_TABLE_SQL)
        self._started = True
        logger.info("Pattern store started.")

    def stop(self) -> None:
        self._sqlite_client.close()
        self._started = False
        logger.info("Pattern store stopped.")

    def health_check(self) -> bool:
        if not self._started:
            return False
        try:
            self._sqlite_client.query("SELECT 1")
            return True
        except Exception:
            logger.exception("Pattern store health check query failed.")
            return False

    def upsert(self, pattern: LearnedPattern) -> None:
        self._sqlite_client.execute(
            _UPSERT_SQL,
            (
                pattern.pattern_id,
                pattern.pattern_type.value,
                pattern.subject,
                pattern.description,
                pattern.confidence,
                pattern.evidence_count,
                pattern.first_observed_at.isoformat(),
                pattern.last_updated_at.isoformat(),
            ),
        )

    def list_by_type(self, pattern_type: PatternType) -> list[LearnedPattern]:
        """Sprint 5.25 hardening (scenario b): a SQLite failure degrades
        to an empty list rather than raising — see this module's own
        docstring."""
        try:
            rows = self._sqlite_client.query(
                f"SELECT {_SELECT_COLUMNS} FROM learned_patterns WHERE pattern_type = ?",
                (pattern_type.value,),
            )
        except Exception:
            logger.exception("Failed to query patterns by type; treating as none found.")
            return []
        return [self._build_pattern(row) for row in rows]

    def list_all(self) -> list[LearnedPattern]:
        """Sprint 5.25 hardening (scenario b): same SQLite-failure
        degrade as list_by_type() above."""
        try:
            rows = self._sqlite_client.query(f"SELECT {_SELECT_COLUMNS} FROM learned_patterns")
        except Exception:
            logger.exception("Failed to query all patterns; treating as none found.")
            return []
        return [self._build_pattern(row) for row in rows]

    def _build_pattern(self, row: tuple) -> LearnedPattern:
        (
            pattern_id,
            pattern_type,
            subject,
            description,
            confidence,
            evidence_count,
            first_observed_at,
            last_updated_at,
        ) = row
        return LearnedPattern(
            pattern_id=pattern_id,
            pattern_type=PatternType(pattern_type),
            subject=subject,
            description=description,
            confidence=confidence,
            evidence_count=evidence_count,
            first_observed_at=datetime.fromisoformat(first_observed_at),
            last_updated_at=datetime.fromisoformat(last_updated_at),
        )
