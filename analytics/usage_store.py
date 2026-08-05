"""Usage Store — persistent recording of AppFocusSamples plus
session-derivation queries. See docs/sprint_book/sprint_5/sprint_5_17.md.

Owns its own single-table DDL (app_focus_samples) against the shared
SqliteClient, following CalendarStore's (4.14), WorkflowStore's (4.9),
and MemoryStore's (3.1) own "caller owns its own DDL" precedent — no
second database-access layer invented.

list_sessions_since() derives UsageSessions from real, persisted
samples at READ time, never at write time: consecutive samples sharing
process_name, with a gap of at most AnalyticsConfig.session_gap_seconds
between them, collapse into one session; a wider gap, or a different
process_name, starts a new one. A single sample with no eligible
neighbor becomes its own one-sample session, never dropped. See
usage_model.py's own module docstring for why this grouping happens at
read time rather than via a mutable in-memory "current session"
tracked across polls.

Sprint 5.25 hardening (scenario b): list_samples_since() degrades to []
on a real SQLite failure, matching CalendarStore.list_due_within()'s own
Sprint 4.19 precedent — its real callers (Sprint 5.20's
AnalyticsDashboardService, Sprint 5.24's live turn/TaskScheduler call
sites) already treat "no samples" as an ordinary, valid input.
list_sessions_since() inherits the same degrade automatically, since it
derives its own result entirely from list_samples_since(). record_sample()
(the write path) is deliberately left unwrapped, the same
"wrapping the write path here would risk a false success the caller
never actually got" reasoning CalendarStore.save() already established.

UsageStore has zero knowledge of Wellness, Learning, or any dashboard —
this class answers only "what was the foreground application, and
when," the same storage/interpretation separation CalendarStore already
established for reminders (Sprint 4.14).
"""

from __future__ import annotations

from datetime import datetime

from analytics.usage_model import AppFocusSample, UsageSession
from config.schema import AnalyticsConfig
from core.logging_setup import get_logger
from database.sqlite_client import SqliteClient

logger = get_logger(__name__)

_CREATE_APP_FOCUS_SAMPLES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_focus_samples (
    sample_id TEXT PRIMARY KEY,
    process_name TEXT NOT NULL,
    window_title TEXT NOT NULL,
    sampled_at TEXT NOT NULL
)
"""


class UsageStore:
    """Constructor DI: (sqlite_client, analytics_config)."""

    def __init__(self, sqlite_client: SqliteClient, analytics_config: AnalyticsConfig) -> None:
        self._sqlite_client = sqlite_client
        self._config = analytics_config
        self._started = False

    def start(self) -> None:
        self._sqlite_client.connect()
        self._sqlite_client.execute(_CREATE_APP_FOCUS_SAMPLES_TABLE_SQL)
        self._started = True
        logger.info("Usage store started.")

    def stop(self) -> None:
        self._sqlite_client.close()
        self._started = False
        logger.info("Usage store stopped.")

    def health_check(self) -> bool:
        if not self._started:
            return False
        try:
            self._sqlite_client.query("SELECT 1")
            return True
        except Exception:
            logger.exception("Usage store health check query failed.")
            return False

    def record_sample(self, sample: AppFocusSample) -> None:
        self._sqlite_client.execute(
            "INSERT OR REPLACE INTO app_focus_samples "
            "(sample_id, process_name, window_title, sampled_at) VALUES (?, ?, ?, ?)",
            (
                sample.sample_id,
                sample.process_name,
                sample.window_title,
                sample.sampled_at.isoformat(),
            ),
        )

    def list_samples_since(self, since: datetime) -> list[AppFocusSample]:
        """Oldest-first — session derivation below needs chronological
        order; nothing in this sprint needs newest-first.

        Sprint 5.25 hardening (scenario b): a SQLite failure degrades to
        an empty list rather than raising — see this module's own
        docstring."""
        try:
            rows = self._sqlite_client.query(
                "SELECT sample_id, process_name, window_title, sampled_at "
                "FROM app_focus_samples WHERE sampled_at >= ? ORDER BY sampled_at ASC",
                (since.isoformat(),),
            )
        except Exception:
            logger.exception("Failed to query usage samples; treating as none recorded.")
            return []
        return [self._build_sample(row) for row in rows]

    def list_sessions_since(self, since: datetime) -> list[UsageSession]:
        """Groups list_samples_since()'s own result into UsageSessions —
        see this module's own docstring for the grouping rule."""
        samples = self.list_samples_since(since)
        sessions: list[UsageSession] = []
        current_process: str | None = None
        current_started_at: datetime | None = None
        current_ended_at: datetime | None = None
        current_count = 0

        def _flush() -> None:
            if current_process is None:
                return
            sessions.append(
                UsageSession(
                    process_name=current_process,
                    category=self._config.category_map.get(current_process),
                    started_at=current_started_at,
                    ended_at=current_ended_at,
                    sample_count=current_count,
                )
            )

        for sample in samples:
            gap_too_wide = (
                current_ended_at is not None
                and (sample.sampled_at - current_ended_at).total_seconds()
                > self._config.session_gap_seconds
            )
            if current_process is None or sample.process_name != current_process or gap_too_wide:
                _flush()
                current_process = sample.process_name
                current_started_at = sample.sampled_at
                current_count = 0
            current_ended_at = sample.sampled_at
            current_count += 1
        _flush()
        return sessions

    def _build_sample(self, row: tuple) -> AppFocusSample:
        sample_id, process_name, window_title, sampled_at = row
        return AppFocusSample(
            sample_id=sample_id,
            process_name=process_name,
            window_title=window_title,
            sampled_at=datetime.fromisoformat(sampled_at),
        )
