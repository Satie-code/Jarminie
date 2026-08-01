"""Calendar Store — persistent CRUD for ScheduledItems. See
docs/sprint_book/sprint_4_14.md.

Owns its own single-table DDL (scheduled_items) against the shared
SqliteClient, following ConversationSessionStore's (2.7), MemoryStore's
(3.1), and WorkflowStore's (4.9) own "caller owns its own DDL"
precedent — no second database-access layer invented.

Sprint 4.19 (Error Handling & Recovery Hardening, Part B) hardening,
scenario (e): list_due_within() now degrades to [] on a SQLite failure,
matching MemoryStore.recent()'s own established Fail Gracefully
convention — its only real caller today, ReminderEngine._poll_due_
items(), already treats "nothing due" as a normal, safe outcome, and a
transient failure simply means that one poll cycle finds nothing; the
next successful poll still finds the same still-persisted item. get()/
list_all()/mark_completed()/delete() remain deliberately unhardened —
none has a real production caller yet (postpone()/reschedule()/
acknowledge() are real, tested, and callable, but nothing live calls any
of them), the same "don't harden speculatively ahead of a real caller"
discipline WorkflowStore's own get()/list_all()-only hardening already
established. save() is ALSO deliberately left unwrapped here, despite
having a real caller (CommunicationPipeline._handle_scheduler_turn()) —
that call site needs to compose an honest degraded spoken reply on
failure, which only the caller, not this store, can do; see voice/
pipeline.py's own Sprint 4.19 hardening for where that guard actually
lives, and why wrapping save() to silently swallow here would risk the
opposite problem (a false "Done" reply the user never actually got).

CalendarStore has zero knowledge of reminders, notification timing, or
postponement — see scheduler_model.py's own module docstring for the
storage/execution split this mirrors from Workflow (4.9/4.10).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from config.schema import SchedulerConfig
from core.logging_setup import get_logger
from database.sqlite_client import SqliteClient
from scheduler.scheduler_model import ItemType, ScheduledItem

logger = get_logger(__name__)

_CREATE_SCHEDULED_ITEMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scheduled_items (
    item_id TEXT PRIMARY KEY,
    item_type TEXT NOT NULL,
    title TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    description TEXT,
    is_completed INTEGER NOT NULL
)
"""


class CalendarStore:
    """Constructor DI: (sqlite_client, scheduler_config)."""

    def __init__(self, sqlite_client: SqliteClient, scheduler_config: SchedulerConfig) -> None:
        self._sqlite_client = sqlite_client
        self._config = scheduler_config
        self._started = False

    def start(self) -> None:
        self._sqlite_client.connect()
        self._sqlite_client.execute(_CREATE_SCHEDULED_ITEMS_TABLE_SQL)
        self._started = True
        logger.info("Calendar store started.")

    def stop(self) -> None:
        self._sqlite_client.close()
        self._started = False
        logger.info("Calendar store stopped.")

    def health_check(self) -> bool:
        if not self._started:
            return False
        try:
            self._sqlite_client.query("SELECT 1")
            return True
        except Exception:
            logger.exception("Calendar store health check query failed.")
            return False

    def save(self, item: ScheduledItem) -> None:
        self._sqlite_client.execute(
            "INSERT OR REPLACE INTO scheduled_items "
            "(item_id, item_type, title, scheduled_at, created_at, description, is_completed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                item.item_id,
                item.item_type.value,
                item.title,
                item.scheduled_at.isoformat(),
                item.created_at.isoformat(),
                item.description,
                int(item.is_completed),
            ),
        )

    def get(self, item_id: str) -> ScheduledItem | None:
        rows = self._sqlite_client.query(
            "SELECT item_id, item_type, title, scheduled_at, created_at, description, "
            "is_completed FROM scheduled_items WHERE item_id = ?",
            (item_id,),
        )
        if not rows:
            return None
        return self._build_item(rows[0])

    def list_all(self) -> list[ScheduledItem]:
        rows = self._sqlite_client.query(
            "SELECT item_id, item_type, title, scheduled_at, created_at, description, "
            "is_completed FROM scheduled_items"
        )
        return [self._build_item(row) for row in rows]

    def list_due_within(
        self, window_end: datetime, *, include_completed: bool = False
    ) -> list[ScheduledItem]:
        """Every item whose scheduled_at is at or before window_end,
        soonest-first. Deliberately open-ended on the lower bound (no
        window_start) — an item that should have fired in the past
        (e.g. the process was offline) still surfaces honestly rather
        than silently vanishing because it's "in the past" relative to
        the query window. See this module's own docstring.

        Raises ValueError (no query run) if window_end is further than
        max_lookahead_days from now — the defensive bound
        SchedulerConfig.max_lookahead_days exists for, the same
        "enforced here, not left to a caller's own discipline" pattern
        WorkflowStore.save()'s max_steps_per_workflow check already
        established. The ValueError check runs BEFORE the try/except
        below and is never itself caught — it's a real programming-error
        signal (a caller passing an unreasonable window), not a SQLite
        failure, and degrading it to an empty list would hide a genuine
        caller bug behind a misleadingly benign "nothing due" result.

        Sprint 4.19 hardening (scenario e): a SQLite failure degrades to
        an empty list rather than raising — see this module's own
        docstring for why."""
        now = datetime.now(window_end.tzinfo)
        max_allowed = now + timedelta(days=self._config.max_lookahead_days)
        if window_end > max_allowed:
            raise ValueError(
                f"window_end {window_end.isoformat()} exceeds max_lookahead_days "
                f"({self._config.max_lookahead_days} days from now)"
            )
        sql = (
            "SELECT item_id, item_type, title, scheduled_at, created_at, description, "
            "is_completed FROM scheduled_items WHERE scheduled_at <= ?"
        )
        if not include_completed:
            sql += " AND is_completed = 0"
        sql += " ORDER BY scheduled_at ASC"
        try:
            rows = self._sqlite_client.query(sql, (window_end.isoformat(),))
        except Exception:
            logger.exception("Failed to query due scheduled items; treating as none due.")
            return []
        return [self._build_item(row) for row in rows]

    def mark_completed(self, item_id: str) -> bool:
        if self.get(item_id) is None:
            return False
        self._sqlite_client.execute(
            "UPDATE scheduled_items SET is_completed = 1 WHERE item_id = ?", (item_id,)
        )
        return True

    def delete(self, item_id: str) -> bool:
        if self.get(item_id) is None:
            return False
        self._sqlite_client.execute(
            "DELETE FROM scheduled_items WHERE item_id = ?", (item_id,)
        )
        return True

    def _build_item(self, row: tuple) -> ScheduledItem:
        item_id, item_type, title, scheduled_at, created_at, description, is_completed = row
        return ScheduledItem(
            item_id=item_id,
            item_type=ItemType(item_type),
            title=title,
            scheduled_at=datetime.fromisoformat(scheduled_at),
            created_at=datetime.fromisoformat(created_at),
            description=description,
            is_completed=bool(is_completed),
        )
