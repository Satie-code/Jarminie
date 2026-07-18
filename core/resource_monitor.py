"""Health Monitor — resource usage probe (CPU/RAM/disk/battery).

A pure probe: reports resource usage and flags threshold breaches. It does
not itself decide what to throttle — that belongs to whichever subsystem
consumes it (Core Manager, and the full System Monitoring work in Phase
4.1). No GPU metric: psutil has no built-in GPU support, a documented
limitation, not an oversight. See docs/sprint_book/sprint_1_4.md.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psutil

from config.schema import ResourceThresholds
from core.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class ResourceSnapshot:
    """A single point-in-time reading of system resource usage."""

    cpu_percent: float
    ram_percent: float
    disk_percent: float
    battery_percent: float | None
    timestamp: datetime


@dataclass
class ResourceAlert:
    """One resource at or beyond its CRITICAL threshold — added during
    Sprint 3.10 (Priority Queue), which needs a real critical-severity
    signal to feed PriorityQueueManager.classify_resource_alert(). Sprint
    1.4 shipped the *_critical_percent config fields and their Settings
    Window display, but nothing that actually checked a live sample
    against them — only breached_resources() below, which checks warning
    thresholds only and returns plain resource names, not alert objects.
    """

    resource: str
    value: float
    threshold: float
    timestamp: datetime


class ResourceMonitor:
    """Samples system resource usage and compares it against configured thresholds."""

    def __init__(self, thresholds: ResourceThresholds) -> None:
        self._thresholds = thresholds

    def sample(self) -> ResourceSnapshot:
        """Take a fresh reading.

        Note: psutil.cpu_percent() compares against the previous call, so
        the very first sample() in a process always reads 0.0 for CPU —
        expected psutil behavior, not a bug. It becomes meaningful from
        the second sample() onward.
        """
        battery = psutil.sensors_battery()
        disk = psutil.disk_usage(str(Path.cwd().anchor))
        snapshot = ResourceSnapshot(
            cpu_percent=psutil.cpu_percent(),
            ram_percent=psutil.virtual_memory().percent,
            disk_percent=disk.percent,
            battery_percent=battery.percent if battery is not None else None,
            timestamp=datetime.now(UTC),
        )
        logger.debug(
            "Resource sample: cpu=%.1f%% ram=%.1f%% disk=%.1f%% battery=%s",
            snapshot.cpu_percent,
            snapshot.ram_percent,
            snapshot.disk_percent,
            f"{snapshot.battery_percent:.1f}%" if snapshot.battery_percent is not None else "n/a",
        )
        return snapshot

    def is_over_threshold(self, snapshot: ResourceSnapshot) -> bool:
        """True if any resource is at or beyond its warning threshold."""
        return bool(self.breached_resources(snapshot))

    def breached_resources(self, snapshot: ResourceSnapshot) -> list[str]:
        """Names of resources at or beyond their warning threshold.

        Battery is inverted relative to cpu/ram/disk: a breach means the
        charge is at or *below* the warning threshold, matching the
        direction established in config.schema.ResourceThresholds.
        """
        breached = []
        if snapshot.cpu_percent >= self._thresholds.cpu_warning_percent:
            breached.append("cpu")
        if snapshot.ram_percent >= self._thresholds.ram_warning_percent:
            breached.append("ram")
        if snapshot.disk_percent >= self._thresholds.disk_warning_percent:
            breached.append("disk")
        if (
            snapshot.battery_percent is not None
            and snapshot.battery_percent <= self._thresholds.battery_warning_percent
        ):
            breached.append("battery")
        if breached:
            logger.warning("Resource threshold(s) breached: %s", ", ".join(breached))
        return breached

    def critical_alerts(self, snapshot: ResourceSnapshot) -> list[ResourceAlert]:
        """ResourceAlerts for every resource at or beyond its CRITICAL
        threshold — the critical-severity counterpart to
        breached_resources() (warning-only, plain names). Added for
        Sprint 3.10's PriorityQueueManager; additive, does not change
        breached_resources()'s existing behavior/signature."""
        alerts = []
        checks = (
            ("cpu", snapshot.cpu_percent, self._thresholds.cpu_critical_percent),
            ("ram", snapshot.ram_percent, self._thresholds.ram_critical_percent),
            ("disk", snapshot.disk_percent, self._thresholds.disk_critical_percent),
        )
        for name, value, threshold in checks:
            if value >= threshold:
                alerts.append(
                    ResourceAlert(
                        resource=name,
                        value=value,
                        threshold=threshold,
                        timestamp=snapshot.timestamp,
                    )
                )
        if (
            snapshot.battery_percent is not None
            and snapshot.battery_percent <= self._thresholds.battery_critical_percent
        ):
            alerts.append(
                ResourceAlert(
                    resource="battery",
                    value=snapshot.battery_percent,
                    threshold=self._thresholds.battery_critical_percent,
                    timestamp=snapshot.timestamp,
                )
            )
        if alerts:
            logger.warning(
                "Resource CRITICAL threshold(s) breached: %s", ", ".join(a.resource for a in alerts)
            )
        return alerts
