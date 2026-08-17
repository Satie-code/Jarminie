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

import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler

from core.logging_setup import get_logger

if TYPE_CHECKING:
    from core.resource_monitor import ResourceMonitor

logger = get_logger(__name__)

_SHUTDOWN_JOIN_TIMEOUT_SECONDS = 5.0
"""Sprint 6.18 (Stress & Recovery Testing) hardening — see stop()'s own
docstring for the real race this closes. Mirrors voice/session_manager.py's
own identical _THREAD_JOIN_TIMEOUT_SECONDS bounded-join precedent
(Sprint 6.17), applied here to APScheduler's own shutdown() instead of a
raw daemon thread."""


class TaskScheduler:
    """Owns its BackgroundScheduler outright — there is nothing to
    inject for that, it is the root of this particular resource.

    resource_monitor (Sprint 6.19, Resource Protection & Fail-Gracefully
    Verification) is the one real optional collaborator: keyword-only,
    defaults to None, the same "optional, degrades to prior unthrottled
    behavior when absent" pattern every other cross-cutting collaborator
    in this codebase already uses (mirroring, e.g., WellnessTracker's
    own optional emotional_state_manager). When supplied, add_job()'s
    own new resource_sensitive=True jobs skip their tick under real
    CRITICAL resource pressure — see add_job()'s own docstring."""

    def __init__(self, resource_monitor: ResourceMonitor | None = None) -> None:
        self._scheduler: BackgroundScheduler | None = None
        self._resource_monitor = resource_monitor

    def start(self) -> None:
        self._scheduler = BackgroundScheduler()
        self._scheduler.start()
        logger.info("Task scheduler started.")

    def stop(self) -> None:
        """Sprint 6.18 (Stress & Recovery Testing) hardening: shutdown(
        wait=True), not the original wait=False, but run on a helper
        thread and bounded-joined here rather than called directly —
        the same "wait for the common case, don't risk an unbounded
        hang" shape voice/session_manager.py's own VoiceSessionManager.
        stop() already established for _listen_thread/_watchdog_thread
        (Sprint 6.17).

        Found directly, not theorized: the original wait=False let
        shutdown() return immediately while any in-flight job (e.g. a
        maintenance pass mid-SqliteClient.execute()) kept running on
        APScheduler's own worker thread — CoreManager.shutdown()'s
        reverse-order pass would then go on to close that same job's
        own store's SqliteClient connection while the job was still
        using it, surfacing as a real, reproducible "SqliteClient.
        connect() must be called before use" error (confirmed via
        tests/system/test_level6_part_b_stress.py's own sustained-load
        scenario, which runs every job at an accelerated cadence that
        made the race easy to hit). A plain, unbounded wait=True would
        close that race but risks the opposite failure — a job blocked
        on a real, held SQLite lock (this same sprint's own recovery
        scenario (b) proves that's a real, reachable state) could then
        hang CoreManager.shutdown() indefinitely. Bounding it here gets
        both: shutdown() waits for the common case (a job's own
        in-flight write finishing in milliseconds), but never blocks
        the app closing for longer than
        _SHUTDOWN_JOIN_TIMEOUT_SECONDS."""
        if self._scheduler is not None:
            scheduler = self._scheduler
            shutdown_thread = threading.Thread(
                target=lambda: scheduler.shutdown(wait=True),
                name="task-scheduler-shutdown",
                daemon=True,
            )
            shutdown_thread.start()
            shutdown_thread.join(timeout=_SHUTDOWN_JOIN_TIMEOUT_SECONDS)
            if shutdown_thread.is_alive():
                logger.error(
                    "Task scheduler shutdown did not complete within %.1fs; "
                    "abandoning the wait (a job may still be running).",
                    _SHUTDOWN_JOIN_TIMEOUT_SECONDS,
                )
            self._scheduler = None
        logger.info("Task scheduler stopped.")

    def health_check(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def add_job(
        self,
        func: Callable[[], None],
        interval_seconds: float,
        job_id: str,
        resource_sensitive: bool = False,
    ) -> None:
        """Registers func to run every interval_seconds. A duplicate
        job_id replaces the existing job — idempotent registration,
        safe to call again from a restarted module without manual
        bookkeeping by the caller.

        resource_sensitive (Sprint 6.19 — Resource Protection &
        Fail-Gracefully Verification): when True AND a resource_monitor
        was supplied at construction, func is wrapped so a real CRITICAL
        reading (core.resource_monitor.ResourceMonitor.critical_alerts(),
        the same CRITICAL-severity check device_control/resource_gate.py's
        ActionResourceGate already uses, not the lower warning-level
        breached_resources()) skips that single tick — the job is never
        removed or rescheduled, just not run this cycle, the cheapest
        and safest degrade (matching Part 2's own "background work is
        reduced," not "stopped"). Logged once per skipped tick. A job
        with resource_sensitive=True but no resource_monitor supplied
        (the default) behaves exactly as before — this parameter is
        purely additive and opt-in per job, never a blanket throttle;
        see this module's own Sprint 6.19 classification of which of
        this project's 13 real jobs actually get it.

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
        tests/system/test_level4_part_a_acceptance.py timing failure).

        max_instances=1 is passed explicitly (Sprint 6.17 — Async
        Background Task Audit): APScheduler's own default is already 1,
        so this changes no observed behavior, but every one of this
        project's 13 real jobs was previously relying on an *unstated*
        library default for the exact guarantee (a slow-running tick
        never overlaps with its own next scheduled tick) every job
        isolation test in this codebase depends on. Stating it here
        closes that "implicit dependency on an unstated default" gap
        directly rather than leaving it to APScheduler's own
        documentation."""
        scheduler = self._require_scheduler()
        first_run = datetime.now(scheduler.timezone) + timedelta(seconds=interval_seconds)
        target = (
            self._wrap_resource_sensitive(func, job_id)
            if resource_sensitive and self._resource_monitor is not None
            else func
        )
        scheduler.add_job(
            target,
            trigger="interval",
            seconds=interval_seconds,
            id=job_id,
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )

    def _wrap_resource_sensitive(self, func: Callable[[], None], job_id: str) -> Callable[[], None]:
        """See add_job()'s own resource_sensitive docstring. Only called
        when self._resource_monitor is not None (checked by the one
        caller, add_job()) — no None-check needed inside the wrapper
        itself."""
        resource_monitor = self._resource_monitor

        def _wrapped() -> None:
            snapshot = resource_monitor.sample()
            if resource_monitor.critical_alerts(snapshot):
                logger.warning(
                    "Skipping resource-sensitive job %r this tick — CRITICAL resource pressure.",
                    job_id,
                )
                return
            func()

        return _wrapped

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
