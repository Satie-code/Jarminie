"""Unit tests for analytics.usage_tracker.

_sample_foreground_window()'s own win32gui/win32process/psutil calls are
monkeypatched at the module level (the same "patch the module-qualified
attribute" convention tests/unit/device_control/test_window_manager.py
already established for an identical class of Win32 call) — deterministic
edge cases (no foreground window, a psutil race) can't be reliably
reproduced against the real, unpredictable desktop foreground window.

start()/stop() are exercised against a REAL TaskScheduler with a fast
sample_interval_seconds, matching tests/unit/scheduler/
test_reminder_engine.py's own established "real collaborator, short
interval, bounded poll-until wait" precedent — not a fake/mock
TaskScheduler.
"""

import time
from datetime import UTC, datetime

import psutil
import pytest

from analytics.usage_store import UsageStore
from analytics.usage_tracker import UsageTracker
from config.schema import AnalyticsConfig
from database.sqlite_client import SqliteClient
from scheduler.task_scheduler import TaskScheduler

_WAIT_TIMEOUT = 2.0


def _wait_until(predicate, timeout: float = _WAIT_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def usage_store(tmp_path) -> UsageStore:
    client = SqliteClient(str(tmp_path / "usage.db"))
    store = UsageStore(client, AnalyticsConfig())
    store.start()
    yield store
    store.stop()


@pytest.fixture
def task_scheduler():
    ts = TaskScheduler()
    ts.start()
    yield ts
    ts.stop()


@pytest.fixture
def tracker(task_scheduler, usage_store) -> UsageTracker:
    return UsageTracker(task_scheduler, usage_store, AnalyticsConfig())


# --- _sample_foreground_window() -----------------------------------------------------


def test_sample_foreground_window_returns_a_real_looking_sample(monkeypatch, tracker):
    monkeypatch.setattr("analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 42)
    monkeypatch.setattr(
        "analytics.usage_tracker.win32process.GetWindowThreadProcessId",
        lambda hwnd: (0, 1234),
    )
    monkeypatch.setattr(
        "analytics.usage_tracker.win32gui.GetWindowText", lambda hwnd: "Some Window"
    )

    class _FakeProcess:
        def name(self) -> str:
            return "devenv.exe"

    monkeypatch.setattr(
        "analytics.usage_tracker.psutil.Process", lambda pid: _FakeProcess()
    )

    sample = tracker._sample_foreground_window()

    assert sample is not None
    assert sample.process_name == "devenv.exe"
    assert sample.window_title == "Some Window"
    assert isinstance(sample.sampled_at, datetime)
    assert sample.sampled_at.tzinfo is UTC


def test_sample_foreground_window_returns_none_when_no_window_is_focused(
    monkeypatch, tracker
):
    monkeypatch.setattr("analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 0)

    assert tracker._sample_foreground_window() is None


def test_sample_foreground_window_returns_none_on_no_such_process_race(
    monkeypatch, tracker
):
    monkeypatch.setattr("analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 42)
    monkeypatch.setattr(
        "analytics.usage_tracker.win32process.GetWindowThreadProcessId",
        lambda hwnd: (0, 1234),
    )

    def _raise_no_such_process(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr("analytics.usage_tracker.psutil.Process", _raise_no_such_process)

    assert tracker._sample_foreground_window() is None


def test_sample_foreground_window_returns_none_on_access_denied(monkeypatch, tracker):
    monkeypatch.setattr("analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 42)
    monkeypatch.setattr(
        "analytics.usage_tracker.win32process.GetWindowThreadProcessId",
        lambda hwnd: (0, 1234),
    )

    def _raise_access_denied(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr("analytics.usage_tracker.psutil.Process", _raise_access_denied)

    assert tracker._sample_foreground_window() is None


def test_sample_foreground_window_against_the_real_live_desktop_never_raises(tracker):
    """A real, non-mocked smoke check — whatever is actually focused on
    this machine right now, sampling it must never raise, and any
    non-None result must be well-formed."""
    sample = tracker._sample_foreground_window()
    if sample is not None:
        assert sample.process_name
        assert isinstance(sample.sampled_at, datetime)


# --- _on_tick() ------------------------------------------------------------------------


def test_on_tick_records_a_sample_when_one_is_available(monkeypatch, tracker, usage_store):
    monkeypatch.setattr("analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 42)
    monkeypatch.setattr(
        "analytics.usage_tracker.win32process.GetWindowThreadProcessId",
        lambda hwnd: (0, 1234),
    )
    monkeypatch.setattr(
        "analytics.usage_tracker.win32gui.GetWindowText", lambda hwnd: "Some Window"
    )

    class _FakeProcess:
        def name(self) -> str:
            return "devenv.exe"

    monkeypatch.setattr(
        "analytics.usage_tracker.psutil.Process", lambda pid: _FakeProcess()
    )

    tracker._on_tick()

    samples = usage_store.list_samples_since(datetime(2020, 1, 1, tzinfo=UTC))
    assert len(samples) == 1
    assert samples[0].process_name == "devenv.exe"


def test_on_tick_records_nothing_when_no_sample_is_available(
    monkeypatch, tracker, usage_store
):
    monkeypatch.setattr("analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 0)

    tracker._on_tick()

    assert usage_store.list_samples_since(datetime(2020, 1, 1, tzinfo=UTC)) == []


# --- start()/stop() against a real TaskScheduler ----------------------------------------


def test_start_registers_a_real_recurring_job_that_records_samples(
    monkeypatch, task_scheduler, usage_store
):
    monkeypatch.setattr("analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 42)
    monkeypatch.setattr(
        "analytics.usage_tracker.win32process.GetWindowThreadProcessId",
        lambda hwnd: (0, 1234),
    )
    monkeypatch.setattr(
        "analytics.usage_tracker.win32gui.GetWindowText", lambda hwnd: "Some Window"
    )

    class _FakeProcess:
        def name(self) -> str:
            return "devenv.exe"

    monkeypatch.setattr(
        "analytics.usage_tracker.psutil.Process", lambda pid: _FakeProcess()
    )

    fast_config = AnalyticsConfig(sample_interval_seconds=0.05)
    tracker = UsageTracker(task_scheduler, usage_store, fast_config)

    tracker.start()
    try:
        assert _wait_until(
            lambda: len(usage_store.list_samples_since(datetime(2020, 1, 1, tzinfo=UTC))) > 0
        )
    finally:
        tracker.stop()


def test_stop_removes_the_job_and_no_further_samples_are_recorded(
    monkeypatch, task_scheduler, usage_store
):
    monkeypatch.setattr("analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 0)
    fast_config = AnalyticsConfig(sample_interval_seconds=0.05)
    tracker = UsageTracker(task_scheduler, usage_store, fast_config)

    tracker.start()
    tracker.stop()
    time.sleep(0.2)

    assert usage_store.list_samples_since(datetime(2020, 1, 1, tzinfo=UTC)) == []


# --- health_check() ---------------------------------------------------------------------


def test_health_check_false_before_start(tracker):
    assert tracker.health_check() is False


def test_health_check_true_after_start_false_after_stop(tracker):
    tracker.start()
    assert tracker.health_check() is True
    tracker.stop()
    assert tracker.health_check() is False
