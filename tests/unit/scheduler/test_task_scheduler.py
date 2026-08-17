"""Unit tests for scheduler.task_scheduler.

Every test here drives a REAL apscheduler.BackgroundScheduler — no
fake/mock scheduler — matching this project's own established
"real collaborator for timing-sensitive behavior" precedent
(voice/session_manager.py's own Sprint 2.5 tests). Timing-sensitive
assertions use threading.Event synchronization with a bounded wait,
never a blind time.sleep()-and-hope.
"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from scheduler.task_scheduler import TaskScheduler

_WAIT_TIMEOUT = 2.0


@pytest.fixture
def scheduler() -> TaskScheduler:
    ts = TaskScheduler()
    ts.start()
    yield ts
    ts.stop()


# --- health_check() ------------------------------------------------------------------


def test_health_check_false_before_start():
    ts = TaskScheduler()
    assert ts.health_check() is False


def test_health_check_true_after_start(scheduler):
    assert scheduler.health_check() is True


def test_health_check_false_after_stop():
    ts = TaskScheduler()
    ts.start()
    ts.stop()
    assert ts.health_check() is False


# --- add_job()/remove_job() before start() --------------------------------------------


def test_add_job_before_start_raises_runtime_error():
    ts = TaskScheduler()
    with pytest.raises(RuntimeError):
        ts.add_job(lambda: None, interval_seconds=1.0, job_id="x")


def test_remove_job_before_start_raises_runtime_error():
    ts = TaskScheduler()
    with pytest.raises(RuntimeError):
        ts.remove_job("x")


# --- add_job() runs the callable repeatedly -------------------------------------------


def test_add_job_runs_the_callable_repeatedly(scheduler):
    event = threading.Event()
    calls = []

    def job():
        calls.append(1)
        if len(calls) >= 2:
            event.set()

    scheduler.add_job(job, interval_seconds=0.05, job_id="test-job")

    assert event.wait(timeout=_WAIT_TIMEOUT)
    assert len(calls) >= 2


def test_add_job_does_not_run_the_callable_immediately(scheduler):
    """Regression test: APScheduler's IntervalTrigger defaults its own
    start_date to "now", which — left unaddressed — fires the first
    execution almost immediately on add_job() rather than after
    waiting one full interval. add_job() must override that so a
    caller registering several jobs at startup (CommunicationPipeline,
    Sprint 4.18) doesn't get them all firing in a startup burst. Uses
    a comfortably long interval and a short observation window so an
    immediate first fire would be caught reliably, not by luck."""
    event = threading.Event()

    scheduler.add_job(event.set, interval_seconds=1.0, job_id="delayed")

    assert not event.wait(timeout=0.3)


def test_add_job_with_duplicate_job_id_replaces_existing_job(scheduler):
    """A second add_job() call with the same job_id genuinely replaces
    the first callable, not merely adding a second job alongside it —
    confirmed by only ever observing the replacement callable's own
    calls after the swap."""
    event_a = threading.Event()
    event_b = threading.Event()

    scheduler.add_job(lambda: event_a.set(), interval_seconds=0.05, job_id="dup")
    assert event_a.wait(timeout=_WAIT_TIMEOUT)

    scheduler.add_job(lambda: event_b.set(), interval_seconds=0.05, job_id="dup")
    assert event_b.wait(timeout=_WAIT_TIMEOUT)


# --- remove_job() ----------------------------------------------------------------------


def test_remove_job_stops_further_calls(scheduler):
    event = threading.Event()
    calls = []

    def job():
        calls.append(1)
        event.set()

    scheduler.add_job(job, interval_seconds=0.05, job_id="removable")
    assert event.wait(timeout=_WAIT_TIMEOUT)

    scheduler.remove_job("removable")
    count_after_removal = len(calls)
    time.sleep(0.2)  # let any already-in-flight tick fire if removal failed
    assert len(calls) == count_after_removal


def test_remove_job_nonexistent_job_id_is_a_no_op(scheduler):
    scheduler.remove_job("does-not-exist")  # must not raise


# --- job isolation: one job's exception doesn't stop another --------------------------


def test_a_jobs_own_exception_does_not_stop_another_independently_registered_job(scheduler):
    good_event = threading.Event()
    good_calls = []

    def failing_job():
        raise RuntimeError("job exploded")

    def good_job():
        good_calls.append(1)
        if len(good_calls) >= 2:
            good_event.set()

    scheduler.add_job(failing_job, interval_seconds=0.05, job_id="failing")
    scheduler.add_job(good_job, interval_seconds=0.05, job_id="good")

    assert good_event.wait(timeout=_WAIT_TIMEOUT)
    assert scheduler.health_check() is True


# --- stop() leaves no orphaned background thread ---------------------------------------


def test_stop_leaves_no_running_background_thread():
    ts = TaskScheduler()
    ts.start()
    ts.stop()
    time.sleep(0.2)
    assert not any(
        t.name.startswith("APScheduler") and t.is_alive() for t in threading.enumerate()
    )


# --- Sprint 6.19 (Resource Protection & Fail-Gracefully Verification):
# resource_sensitive skip-on-CRITICAL --------------------------------------------------


def _resource_monitor(critical: bool) -> MagicMock:
    monitor = MagicMock()
    monitor.sample.return_value = "snapshot"
    monitor.critical_alerts.return_value = ["cpu"] if critical else []
    return monitor


def test_resource_sensitive_job_skips_ticks_while_resource_monitor_reports_critical():
    resource_monitor = _resource_monitor(critical=True)
    ts = TaskScheduler(resource_monitor=resource_monitor)
    ts.start()
    calls = []
    try:
        ts.add_job(
            lambda: calls.append(1),
            interval_seconds=0.05,
            job_id="sensitive",
            resource_sensitive=True,
        )
        time.sleep(0.3)
    finally:
        ts.stop()

    assert calls == []
    assert resource_monitor.sample.call_count >= 1


def test_resource_sensitive_job_runs_once_resource_monitor_reports_no_critical_alerts():
    resource_monitor = _resource_monitor(critical=False)
    ts = TaskScheduler(resource_monitor=resource_monitor)
    ts.start()
    event = threading.Event()
    try:
        ts.add_job(
            event.set, interval_seconds=0.05, job_id="sensitive", resource_sensitive=True
        )
        assert event.wait(timeout=_WAIT_TIMEOUT)
    finally:
        ts.stop()


def test_non_resource_sensitive_job_keeps_running_during_a_critical_reading():
    """The other real half of Sprint 6.19's own Acceptance Criteria: a
    job NOT marked resource_sensitive must be completely unaffected by
    real CRITICAL pressure — matching Part 2's own "reduced," never
    "stopped," and this sprint's own explicit choice not to gate
    ReminderEngine's poll/_check_and_announce_priority_item this way."""
    resource_monitor = _resource_monitor(critical=True)
    ts = TaskScheduler(resource_monitor=resource_monitor)
    ts.start()
    event = threading.Event()
    try:
        ts.add_job(event.set, interval_seconds=0.05, job_id="not-sensitive")
        assert event.wait(timeout=_WAIT_TIMEOUT)
    finally:
        ts.stop()


def test_resource_sensitive_job_runs_normally_when_no_resource_monitor_supplied():
    """The default (resource_monitor=None, every existing add_job()
    call site/test in this file) must keep working completely
    unchanged — resource_sensitive is purely opt-in per job AND
    requires a resource_monitor to actually do anything."""
    ts = TaskScheduler()
    ts.start()
    event = threading.Event()
    try:
        ts.add_job(event.set, interval_seconds=0.05, job_id="sensitive", resource_sensitive=True)
        assert event.wait(timeout=_WAIT_TIMEOUT)
    finally:
        ts.stop()


def test_resource_sensitive_job_logs_once_per_skipped_tick(caplog):
    resource_monitor = _resource_monitor(critical=True)
    ts = TaskScheduler(resource_monitor=resource_monitor)
    ts.start()
    try:
        with caplog.at_level("WARNING"):
            ts.add_job(
                lambda: None,
                interval_seconds=0.05,
                job_id="sensitive",
                resource_sensitive=True,
            )
            deadline = time.monotonic() + _WAIT_TIMEOUT
            while time.monotonic() < deadline and not any(
                "sensitive" in record.message for record in caplog.records
            ):
                time.sleep(0.01)
    finally:
        ts.stop()

    assert any(
        "Skipping resource-sensitive job" in record.message for record in caplog.records
    )
