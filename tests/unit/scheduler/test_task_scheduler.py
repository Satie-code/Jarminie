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
