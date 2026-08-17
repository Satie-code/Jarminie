"""Level 6 Part B — Resource Protection & Fail-Gracefully Verification
(Sprint 6.19).

System-level re-confirmation of scheduler/task_scheduler.py's own new
resource_sensitive mechanism (Sprint 6.19's own Objectives/Implementation
Task 5) against the real, complete CoreManager graph — proving both
halves of the Acceptance Criteria in one real, timed observation:

- A resource_sensitive=True job (UsageTracker._on_tick, one of this
  sprint's own explicitly named classifications) genuinely skips its own
  tick while a real, induced ResourceMonitor CRITICAL reading holds.
- A non-sensitive job (ReminderEngine._poll_due_items — real user-facing
  lateness cost, deliberately excluded from this sprint's own
  classification) keeps running completely normally throughout the same
  window.

Reuses Sprint 6.18's own real-induced-CRITICAL technique
(test_level6_part_b_stress.py's test_recovery_resource_critical_then_normal):
only ResourceMonitor.sample() itself is monkeypatched, the one seam that
class actually exposes — not a separate fake ResourceMonitor double, so
TaskScheduler's own real critical_alerts()/breached_resources() logic
runs unmodified against the substituted reading.

No conversation turn is driven anywhere in this file — unlike
test_level6_part_b_stress.py's own recovery scenarios, this sprint's own
mechanism lives entirely inside TaskScheduler/ResourceMonitor, with no
voice-pipeline involvement at all, so wait_for_active_capture/
wait_for_dormant/push_utterance are never needed here.
"""

import time
from datetime import UTC, datetime

import pytest

from analytics.usage_tracker import UsageTracker
from core.resource_monitor import ResourceSnapshot
from scheduler.reminder_engine import ReminderEngine

_OBSERVATION_WINDOW_SECONDS = 2.0
"""~6-7 ticks at fast_resource_protection_app_harness's own 0.3s interval
— comfortably enough for a real, non-flaky "the sensitive job's own tick
count stayed at zero" observation, matching this project's own generous,
host-tolerant threshold philosophy (test_startup_performance.py's/
test_level6_part_b_stress.py's own identical reasoning)."""


def _critical_snapshot() -> ResourceSnapshot:
    return ResourceSnapshot(
        cpu_percent=99.0,
        ram_percent=50.0,
        disk_percent=50.0,
        battery_percent=None,
        timestamp=datetime.now(UTC),
    )


def _normal_snapshot() -> ResourceSnapshot:
    return ResourceSnapshot(
        cpu_percent=10.0,
        ram_percent=30.0,
        disk_percent=40.0,
        battery_percent=None,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def job_tick_counts(monkeypatch):
    """Wraps UsageTracker._on_tick()/ReminderEngine._poll_due_items() at
    the CLASS level with a counting-but-still-real wrapper (each still
    calls the genuine original implementation) — mirrors tests/
    integration/test_scheduler_integration.py's own maintenance_call_
    counts fixture exactly, for the identical reason its own docstring
    documents.

    Must be requested BEFORE fast_resource_protection_app_harness in a
    test's own parameter list: CommunicationPipeline.start()/
    UsageTracker.start()/ReminderEngine.register() each capture their
    own tick method as a bound method the instant TaskScheduler.add_job()
    is called, during the harness fixture's own setup — patching has to
    land on the class before that happens, not after the harness is
    handed back. pytest instantiates same-scoped, independent fixtures
    in the order a test function lists them, which is what makes this
    ordering reliable rather than incidental."""
    counts = {"usage_sample": 0, "reminder_poll": 0}

    original_on_tick = UsageTracker._on_tick
    original_poll = ReminderEngine._poll_due_items

    def counting_on_tick(self):
        counts["usage_sample"] += 1
        return original_on_tick(self)

    def counting_poll(self):
        counts["reminder_poll"] += 1
        return original_poll(self)

    monkeypatch.setattr(UsageTracker, "_on_tick", counting_on_tick)
    monkeypatch.setattr(ReminderEngine, "_poll_due_items", counting_poll)
    return counts


def test_resource_sensitive_job_skips_while_non_sensitive_job_keeps_running(
    job_tick_counts, fast_resource_protection_app_harness, monkeypatch
):
    h = fast_resource_protection_app_harness
    # Fixture setup itself (real model loading etc., often 50-90s on this
    # machine) already far exceeds this harness's own 0.3s job interval,
    # so both jobs have already ticked several times against real,
    # non-CRITICAL host readings before this test body ever runs. Patch
    # resource_monitor.sample() to CRITICAL FIRST, then reset the
    # counts — in that order, even a tick that started its own sample()
    # call a hair before the patch landed (a real but narrow race
    # against this thread's own two adjacent statements, not the whole
    # multi-second fixture-setup window above) still gets its own count
    # zeroed out immediately after, so what's measured is genuinely
    # "ticks since CRITICAL took effect."
    monkeypatch.setattr(h.resource_monitor, "sample", _critical_snapshot)
    job_tick_counts["usage_sample"] = 0
    job_tick_counts["reminder_poll"] = 0

    time.sleep(_OBSERVATION_WINDOW_SECONDS)

    assert job_tick_counts["usage_sample"] == 0, (
        "usage_tracker_sample (resource_sensitive=True) ticked at least once while a "
        "real CRITICAL ResourceMonitor reading held — should have skipped every tick."
    )
    assert job_tick_counts["reminder_poll"] >= 3, (
        "reminder_engine_poll (not resource_sensitive) failed to keep running normally "
        f"during the same CRITICAL window — only {job_tick_counts['reminder_poll']} tick(s)."
    )


def test_resource_sensitive_job_resumes_once_resource_pressure_clears(
    job_tick_counts, fast_resource_protection_app_harness, monkeypatch
):
    """Companion to the test above: a skip is only ever "this tick," per
    add_job()'s own docstring — the job itself is never removed or
    delayed to a specific later time, so once CRITICAL pressure clears
    it must resume ticking on its own, without re-registration or a
    restart, the same "real, restart-free recovery" property every
    Sprint 6.18 recovery scenario already proved for a different
    mechanism."""
    h = fast_resource_protection_app_harness
    # See the sibling test immediately above for why the patch lands
    # before the reset, not after.
    monkeypatch.setattr(h.resource_monitor, "sample", _critical_snapshot)
    job_tick_counts["usage_sample"] = 0

    time.sleep(_OBSERVATION_WINDOW_SECONDS)
    assert job_tick_counts["usage_sample"] == 0

    monkeypatch.setattr(h.resource_monitor, "sample", _normal_snapshot)
    time.sleep(_OBSERVATION_WINDOW_SECONDS)

    assert job_tick_counts["usage_sample"] >= 3, (
        "usage_tracker_sample never resumed ticking after CRITICAL pressure cleared "
        f"(only {job_tick_counts['usage_sample']} tick(s) since)."
    )
