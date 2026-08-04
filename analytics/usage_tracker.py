"""Usage Tracker — samples the real foreground window/process on a
TaskScheduler-driven interval and records it via UsageStore. See
docs/sprint_book/sprint_5/sprint_5_17.md.

Reuses scheduler/task_scheduler.py's TaskScheduler.add_job()/
remove_job() (Sprint 4.15) rather than owning a timer of its own — the
first real caller beyond ReminderEngine of that shared, generic
primitive, exactly what docs/sprint_book/INDEX.md's own "Level 4 Part B
breakdown changes" note anticipated.

_sample_foreground_window() never interprets what it observes — no
"this is work" / "this is a distraction" judgment anywhere in this
class, matching the Learning Engine's own "never makes major autonomous
decisions" mandate applied here at the data-collection layer first (see
usage_store.py's own module docstring). A missing foreground window
(the desktop itself focused, hwnd == 0) and a process that has already
exited by the time psutil.Process() resolves it (psutil.NoSuchProcess,
or a small number of protected/elevated processes, psutil.AccessDenied)
are both ordinary, expected races — degrading to "no sample recorded
this tick," never a raised exception.
"""

from __future__ import annotations

from datetime import UTC, datetime

import psutil
import win32gui
import win32process

from analytics.usage_model import AppFocusSample
from analytics.usage_store import UsageStore
from config.schema import AnalyticsConfig
from core.logging_setup import get_logger
from scheduler.task_scheduler import TaskScheduler

logger = get_logger(__name__)

_JOB_ID = "usage_tracker_sample"


class UsageTracker:
    """Constructor DI: (task_scheduler, usage_store, analytics_config)."""

    def __init__(
        self,
        task_scheduler: TaskScheduler,
        usage_store: UsageStore,
        analytics_config: AnalyticsConfig,
    ) -> None:
        self._task_scheduler = task_scheduler
        self._usage_store = usage_store
        self._config = analytics_config
        self._started = False

    def start(self) -> None:
        self._task_scheduler.add_job(self._on_tick, self._config.sample_interval_seconds, _JOB_ID)
        self._started = True
        logger.info(
            "Usage tracker started (sample_interval_seconds=%s).",
            self._config.sample_interval_seconds,
        )

    def stop(self) -> None:
        self._task_scheduler.remove_job(_JOB_ID)
        self._started = False
        logger.info("Usage tracker stopped.")

    def health_check(self) -> bool:
        return self._started

    def _sample_foreground_window(self) -> AppFocusSample | None:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        try:
            process_name = psutil.Process(process_id).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
        window_title = win32gui.GetWindowText(hwnd)
        return AppFocusSample(
            process_name=process_name,
            window_title=window_title,
            sampled_at=datetime.now(UTC),
        )

    def _on_tick(self) -> None:
        sample = self._sample_foreground_window()
        if sample is not None:
            self._usage_store.record_sample(sample)
