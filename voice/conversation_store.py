"""Conversation Session Store — a rolling, bounded-retention log of
completed voice turns.

This is a **session log, not the Memory Engine**: it timestamps and stores
each turn (who said what, and which persona answered), tagged by session,
so Context Manager (Sprint 2.8) can retrieve recent turns for a live
conversation. It deliberately does NOT score, promote, or semantically
retrieve turns across sessions — no "relevance"/"importance" column exists
here, and none should be added by a future sprint. That is Level 3's job:
Phase 3.1 (Memory Engine) and Phase 3.2 (Dynamic Memory, per
02_System_Architecture.md's Dynamic Memory Formula) own long-term,
scored, cross-session retrieval. See docs/sprint_book/sprint_2_7.md.

Retention is time-based and bounded (purge_older_than()) — this table is a
rolling log, not permanent storage.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config.schema import DatabaseConfig
from core.logging_setup import get_logger
from database.sqlite_client import SqliteClient
from voice.errors import ConversationStoreError

logger = get_logger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS conversation_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    persona_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    user_text TEXT NOT NULL,
    response_text TEXT NOT NULL
)
"""


@dataclass
class ConversationTurn:
    """One completed voice turn. timestamp is stored/compared as an
    ISO 8601 string in UTC — always construct it via datetime.now(UTC),
    matching VoiceSession's convention (voice/session_manager.py), so
    lexicographic string comparison in SQL stays consistent with
    chronological order."""

    session_id: str
    persona_name: str
    timestamp: datetime
    user_text: str
    response_text: str


class ConversationSessionStore:
    """Records and retrieves conversation turns via an injected SqliteClient.

    Constructor DI per 03_Engineering_Standards.md: receives the
    SqliteClient and DatabaseConfig it depends on rather than constructing
    either itself. database_config supplies conversation_retention_days as
    purge_older_than()'s default window, so callers don't each need to
    know/re-derive the configured retention policy themselves.
    """

    def __init__(self, sqlite_client: SqliteClient, database_config: DatabaseConfig) -> None:
        self._sqlite_client = sqlite_client
        self._database_config = database_config
        self._started = False

    def start(self) -> None:
        """Open the SQLite connection and ensure the conversation-turns
        table exists (idempotent)."""
        try:
            self._sqlite_client.connect()
            self._sqlite_client.execute(_CREATE_TABLE_SQL)
        except Exception as exc:
            raise ConversationStoreError(f"Failed to start conversation store: {exc}") from exc
        self._started = True
        logger.info("Conversation session store started.")

    def stop(self) -> None:
        self._sqlite_client.close()
        self._started = False
        logger.info("Conversation session store stopped.")

    def health_check(self) -> bool:
        """Started AND a trivial query still succeeds — a real liveness
        check, not just a "was start() called" flag."""
        if not self._started:
            return False
        try:
            self._sqlite_client.query("SELECT 1")
            return True
        except Exception:
            logger.exception("Conversation session store health check query failed.")
            return False

    def record_turn(self, turn: ConversationTurn) -> None:
        """Persist one turn. A failed write is caught and logged, never
        raised out to the caller — Voice Session Manager must not crash a
        live conversation because a disk write failed (same discipline as
        Sprint 1.8's ConfigLoader.save() lesson)."""
        try:
            self._sqlite_client.execute(
                "INSERT INTO conversation_turns "
                "(session_id, persona_name, timestamp, user_text, response_text) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    turn.session_id,
                    turn.persona_name,
                    turn.timestamp.isoformat(),
                    turn.user_text,
                    turn.response_text,
                ),
            )
        except Exception:
            logger.exception("Failed to record conversation turn for session %s.", turn.session_id)

    def get_recent_turns(self, session_id: str, limit: int) -> list[ConversationTurn]:
        """Return up to `limit` most recent turns for a session, oldest
        first — the order a conversation actually happened in, ready for a
        caller (Context Manager, Sprint 2.8) to consume directly.

        Sprint 2.13 hardening: a failed read is caught and logged,
        returning an empty list — the same Fail Gracefully discipline as
        record_turn(), so a broken persistence layer degrades the
        conversation's context to "none available" rather than aborting
        the whole turn (Context Manager already treats an empty list as a
        normal, valid case — Sprint 2.8's own "empty session" handling —
        so no caller needed to change for this)."""
        try:
            rows = self._sqlite_client.query(
                "SELECT session_id, persona_name, timestamp, user_text, response_text "
                "FROM conversation_turns WHERE session_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            )
        except Exception:
            logger.exception("Failed to read recent turns for session %s.", session_id)
            return []
        turns = [
            ConversationTurn(
                session_id=row[0],
                persona_name=row[1],
                timestamp=datetime.fromisoformat(row[2]),
                user_text=row[3],
                response_text=row[4],
            )
            for row in rows
        ]
        return list(reversed(turns))

    def purge_older_than(self, days: int | None = None) -> int:
        """Delete turns strictly older than `days` (default:
        DatabaseConfig.conversation_retention_days). Returns the count
        removed, or 0 if the purge itself failed.

        Sprint 2.14 hardening (found during the Level 2 adversarial
        re-read, fixed here since this file owns ConversationSessionStore):
        this method had no failure handling at all, unlike record_turn()/
        get_recent_turns() (Sprint 2.7/2.13). No caller exists yet
        (backlog/technical_debt.md item 11), but a future caller
        shouldn't inherit an unprotected failure path — same Fail
        Gracefully discipline as this class's other two methods."""
        if days is None:
            days = self._database_config.conversation_retention_days
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        try:
            removed = self._sqlite_client.query(
                "SELECT COUNT(*) FROM conversation_turns WHERE timestamp < ?", (cutoff,)
            )[0][0]
            self._sqlite_client.execute(
                "DELETE FROM conversation_turns WHERE timestamp < ?", (cutoff,)
            )
        except Exception:
            logger.exception("Failed to purge conversation turns older than %s days.", days)
            return 0
        return removed
