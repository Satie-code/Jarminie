"""Task Scheduler — the one real periodic-task mechanism this project's
Scheduler Engine, and later sprints, share. See
docs/sprint_book/sprint_4_15.md.

Deliberately generic: knows nothing about reminders, memory cleanup, or
any other specific job's purpose — a pure "run this callable on this
interval" primitive over the one real APScheduler BackgroundScheduler
instance. This is what lets Sprint 4.18 register
MemoryLifecycleManager's passes, ConversationSessionStore.
purge_older_than(), and ActionAuditLog.purge_older_than() as jobs on
the identical instance ReminderEngine (4.15) already uses — finally
giving backlog/technical_debt.md items 11/15's still-open recurring-
cadence half a real caller. See docs/sprint_book/INDEX.md's "Level 4
Part B breakdown changes" note.

BackgroundScheduler (not BlockingScheduler) runs its own thread without
blocking the Qt event loop (ui/app.py's run_app()) — the same
"background thread, not the main loop" shape WakeWordDetector's
passive-listening thread and VoiceSessionManager's watchdog thread
already establish. APScheduler's own default executor catches and logs
a job function's own exception without stopping the scheduler thread or
any other registered job — verified directly by this module's own test
suite, not merely assumed from APScheduler's documentation.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler

from core.logging_setup import get_logger

logger = get_logger(__name__)


class TaskScheduler:
    """No constructor DI — owns its BackgroundScheduler outright; there
    is nothing to inject, it is the root of this particular resource."""

    def __init__(self) -> None:
        self._scheduler: BackgroundScheduler | None = None

    def start(self) -> None:
        self._scheduler = BackgroundScheduler()
        self._scheduler.start()
        logger.info("Task scheduler started.")

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        logger.info("Task scheduler stopped.")

    def health_check(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def add_job(self, func: Callable[[], None], interval_seconds: float, job_id: str) -> None:
        """Registers func to run every interval_seconds. A duplicate
        job_id replaces the existing job — idempotent registration,
        safe to call again from a restarted module without manual
        bookkeeping by the caller.

        next_run_time is set explicitly to now + interval_seconds:
        APScheduler's IntervalTrigger otherwise defaults its own
        start_date to "now", which makes the *first* execution fire
        almost immediately on registration rather than after waiting
        one full interval. Left at that default, every add_job() call
        made during CoreManager.startup() (CommunicationPipeline
        registers five — four maintenance passes plus the proactive-
        reminder check, Sprint 4.18) would fire in a burst on every
        single application startup, including maintenance jobs meant
        to run hourly — real, reproducible background SQLite
        contention during startup, not merely a cosmetic surprise
        (first caught via a genuinely reproducible
        tests/system/test_level4_part_a_acceptance.py timing failure)."""
        scheduler = self._require_scheduler()
        first_run = datetime.now(scheduler.timezone) + timedelta(seconds=interval_seconds)
        scheduler.add_job(
            func,
            trigger="interval",
            seconds=interval_seconds,
            id=job_id,
            replace_existing=True,
            next_run_time=first_run,
        )

    def remove_job(self, job_id: str) -> None:
        """No-op (not an error) if job_id isn't registered — the same
        tolerant-removal convention WorkflowStore.delete()/
        CalendarStore.delete() already established for "remove
        something that may already be gone."""
        scheduler = self._require_scheduler()
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass

    def _require_scheduler(self) -> BackgroundScheduler:
        if self._scheduler is None:
            raise RuntimeError("TaskScheduler.start() must be called before use.")
        return self._scheduler
