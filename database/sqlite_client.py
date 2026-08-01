"""SqliteClient — a thin, schema-agnostic SQLite connection wrapper.

Deliberately knows nothing about what tables exist: connect/execute/query/
close only (Interface First / Single Responsibility — schema ownership
belongs to each caller, e.g. ConversationSessionStore owns its own table's
DDL). Created by Sprint 2.7 (Conversation Session Store) because Sprint 3.1
(Memory Store Foundation) was always going to need exactly this piece first
— see docs/sprint_book/sprint_2_7.md's Engineering Rationale. Whether this
class is generic enough to also serve config/scheduler is a Sprint 3.1
layering decision, deferred (not resolved) here.

WAL (Write-Ahead Logging) mode is enabled on every connect() so concurrent
readers don't block a writer — relevant once more than one subsystem
(Conversation Session Store now, others from Sprint 3.1 onward) may touch
the same database file.

A single threading.Lock guards every operation that touches self._connection
(Post-Sprint Fix, Sprint 4.18). check_same_thread=False only disables
Python's own same-thread safety check — it does NOT make a single
sqlite3.Connection object safe for genuinely concurrent use from more than
one thread; Python's own sqlite3 docs are explicit that the underlying C
library must be built in "serialized" threading mode for that, which isn't
guaranteed. Confirmed as a real, not theoretical, problem: before this fix,
several real background threads hammering execute()/query() on the same
connection concurrently produced genuinely corrupted results (sqlite3.
InterfaceError "bad parameter or other API misuse", DatabaseError "another
row available") — every prior caller in this project used one SqliteClient
from a single thread at a time, so this was latent until Sprint 4.18 gave
MemoryLifecycleManager.run_cleanup_pass()/run_monthly_review() (both
sharing MemoryStore's one connection) their first real, independent,
concurrently-ticking TaskScheduler jobs.
"""

import sqlite3
import threading
from pathlib import Path

from core.logging_setup import get_logger

logger = get_logger(__name__)


class SqliteClient:
    """Owns exactly one SQLite connection to a single file, opened by
    connect() and closed by close(). execute()/query() require an open
    connection — calling either first raises RuntimeError, a plain
    programming-error signal rather than a domain-specific exception, since
    this class has no domain of its own."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Open the connection, creating the parent directory if needed,
        and enable WAL mode. Safe to call again after close()."""
        path = Path(self._db_path)
        if path.parent != Path():
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
            self._connection.execute("PRAGMA journal_mode=WAL")
        logger.info("SqliteClient connected: %s", self._db_path)

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Run a non-query statement (INSERT/UPDATE/DELETE/DDL) and commit."""
        with self._lock:
            connection = self._require_connection()
            connection.execute(sql, params)
            connection.commit()

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        """Run a SELECT and return every resulting row."""
        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(sql, params)
            return cursor.fetchall()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
        logger.info("SqliteClient closed: %s", self._db_path)

    def _require_connection(self) -> sqlite3.Connection:
        """Caller must already hold self._lock."""
        if self._connection is None:
            raise RuntimeError("SqliteClient.connect() must be called before use.")
        return self._connection
