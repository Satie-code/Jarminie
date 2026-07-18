"""Unit tests for core.resource_monitor."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from config.schema import ResourceThresholds
from core.resource_monitor import ResourceAlert, ResourceMonitor, ResourceSnapshot


def _thresholds(**overrides):
    defaults = dict(
        cpu_warning_percent=70.0,
        cpu_critical_percent=90.0,
        ram_warning_percent=75.0,
        ram_critical_percent=90.0,
        battery_warning_percent=20.0,
        battery_critical_percent=10.0,
        disk_warning_percent=85.0,
        disk_critical_percent=95.0,
    )
    defaults.update(overrides)
    return ResourceThresholds(**defaults)


def _snapshot(**overrides):
    defaults = dict(
        cpu_percent=10.0,
        ram_percent=10.0,
        disk_percent=10.0,
        battery_percent=80.0,
        timestamp=datetime.now(UTC),
    )
    defaults.update(overrides)
    return ResourceSnapshot(**defaults)


@patch("core.resource_monitor.psutil")
def test_sample_returns_populated_snapshot(mock_psutil):
    mock_psutil.cpu_percent.return_value = 12.5
    mock_psutil.virtual_memory.return_value = MagicMock(percent=45.0)
    mock_psutil.disk_usage.return_value = MagicMock(percent=60.0)
    mock_psutil.sensors_battery.return_value = MagicMock(percent=88.0)

    monitor = ResourceMonitor(_thresholds())
    snapshot = monitor.sample()

    assert snapshot.cpu_percent == 12.5
    assert snapshot.ram_percent == 45.0
    assert snapshot.disk_percent == 60.0
    assert snapshot.battery_percent == 88.0
    assert snapshot.timestamp is not None


@patch("core.resource_monitor.psutil")
def test_sample_handles_no_battery(mock_psutil):
    mock_psutil.cpu_percent.return_value = 12.5
    mock_psutil.virtual_memory.return_value = MagicMock(percent=45.0)
    mock_psutil.disk_usage.return_value = MagicMock(percent=60.0)
    mock_psutil.sensors_battery.return_value = None

    monitor = ResourceMonitor(_thresholds())
    snapshot = monitor.sample()

    assert snapshot.battery_percent is None


def test_is_over_threshold_false_when_all_under():
    monitor = ResourceMonitor(_thresholds())
    snapshot = _snapshot(
        cpu_percent=10.0, ram_percent=10.0, disk_percent=10.0, battery_percent=80.0
    )
    assert monitor.is_over_threshold(snapshot) is False
    assert monitor.breached_resources(snapshot) == []


def test_cpu_breach_detected():
    monitor = ResourceMonitor(_thresholds(cpu_warning_percent=70.0))
    snapshot = _snapshot(cpu_percent=75.0)
    assert monitor.is_over_threshold(snapshot) is True
    assert monitor.breached_resources(snapshot) == ["cpu"]


def test_ram_breach_detected():
    monitor = ResourceMonitor(_thresholds(ram_warning_percent=75.0))
    snapshot = _snapshot(ram_percent=80.0)
    assert monitor.breached_resources(snapshot) == ["ram"]


def test_disk_breach_detected():
    monitor = ResourceMonitor(_thresholds(disk_warning_percent=85.0))
    snapshot = _snapshot(disk_percent=90.0)
    assert monitor.breached_resources(snapshot) == ["disk"]


def test_battery_breach_is_inverted_low_is_bad():
    monitor = ResourceMonitor(_thresholds(battery_warning_percent=20.0))
    snapshot = _snapshot(battery_percent=15.0)
    assert monitor.breached_resources(snapshot) == ["battery"]


def test_battery_none_does_not_breach():
    monitor = ResourceMonitor(_thresholds(battery_warning_percent=20.0))
    snapshot = _snapshot(battery_percent=None)
    assert monitor.breached_resources(snapshot) == []


def test_multiple_breaches_all_reported():
    monitor = ResourceMonitor(_thresholds(cpu_warning_percent=70.0, ram_warning_percent=75.0))
    snapshot = _snapshot(cpu_percent=90.0, ram_percent=95.0)
    breached = monitor.breached_resources(snapshot)
    assert set(breached) == {"cpu", "ram"}


# --- critical_alerts() (Sprint 3.10 addition) --------------------------------


def test_critical_alerts_empty_when_all_under_critical():
    monitor = ResourceMonitor(_thresholds())
    snapshot = _snapshot(cpu_percent=75.0, ram_percent=80.0)  # over warning, under critical
    assert monitor.critical_alerts(snapshot) == []


def test_cpu_critical_alert_detected():
    monitor = ResourceMonitor(_thresholds(cpu_critical_percent=90.0))
    snapshot = _snapshot(cpu_percent=95.0)
    alerts = monitor.critical_alerts(snapshot)
    assert len(alerts) == 1
    assert alerts[0] == ResourceAlert(
        resource="cpu", value=95.0, threshold=90.0, timestamp=snapshot.timestamp
    )


def test_ram_critical_alert_detected():
    monitor = ResourceMonitor(_thresholds(ram_critical_percent=90.0))
    snapshot = _snapshot(ram_percent=92.0)
    alerts = monitor.critical_alerts(snapshot)
    assert [a.resource for a in alerts] == ["ram"]


def test_disk_critical_alert_detected():
    monitor = ResourceMonitor(_thresholds(disk_critical_percent=95.0))
    snapshot = _snapshot(disk_percent=99.0)
    alerts = monitor.critical_alerts(snapshot)
    assert [a.resource for a in alerts] == ["disk"]


def test_battery_critical_alert_is_inverted_low_is_bad():
    monitor = ResourceMonitor(_thresholds(battery_critical_percent=10.0))
    snapshot = _snapshot(battery_percent=5.0)
    alerts = monitor.critical_alerts(snapshot)
    assert [a.resource for a in alerts] == ["battery"]


def test_battery_none_does_not_trigger_critical_alert():
    monitor = ResourceMonitor(_thresholds(battery_critical_percent=10.0))
    snapshot = _snapshot(battery_percent=None)
    assert monitor.critical_alerts(snapshot) == []


def test_multiple_critical_alerts_all_reported():
    monitor = ResourceMonitor(_thresholds(cpu_critical_percent=90.0, ram_critical_percent=90.0))
    snapshot = _snapshot(cpu_percent=95.0, ram_percent=99.0)
    alerts = monitor.critical_alerts(snapshot)
    assert {a.resource for a in alerts} == {"cpu", "ram"}


def test_warning_level_breach_alone_does_not_produce_a_critical_alert():
    """A resource over its warning threshold but under critical must not
    appear in critical_alerts() — the two methods check independent
    thresholds, not a shared one."""
    monitor = ResourceMonitor(_thresholds(cpu_warning_percent=70.0, cpu_critical_percent=90.0))
    snapshot = _snapshot(cpu_percent=75.0)
    assert monitor.breached_resources(snapshot) == ["cpu"]
    assert monitor.critical_alerts(snapshot) == []
