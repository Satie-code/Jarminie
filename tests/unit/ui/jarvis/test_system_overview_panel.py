"""Unit tests for ui.jarvis.system_overview_panel."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from core.resource_monitor import ResourceSnapshot
from ui.jarvis.system_overview_panel import SystemOverviewPanel


def _snapshot(**overrides) -> ResourceSnapshot:
    defaults = dict(
        cpu_percent=18.0, ram_percent=32.0, disk_percent=45.0, battery_percent=80.0,
        timestamp=datetime.now(UTC),
    )
    defaults.update(overrides)
    return ResourceSnapshot(**defaults)


def test_gpu_gauge_always_shows_no_data(qtbot):
    panel = SystemOverviewPanel(MagicMock())
    qtbot.addWidget(panel)

    assert panel._gpu._value is None


def test_resources_updated_updates_cpu_ram_disk_gauges(qtbot):
    adapter = MagicMock()
    panel = SystemOverviewPanel(adapter)
    qtbot.addWidget(panel)

    panel._on_resources_updated(_snapshot(cpu_percent=42.0, ram_percent=55.0, disk_percent=60.0))

    assert panel._cpu._value == 42.0
    assert panel._ram._value == 55.0
    assert panel._disk._value == 60.0


def test_gpu_gauge_stays_none_after_a_real_resources_update(qtbot):
    adapter = MagicMock()
    panel = SystemOverviewPanel(adapter)
    qtbot.addWidget(panel)

    panel._on_resources_updated(_snapshot())

    assert panel._gpu._value is None


def test_subscribes_to_the_metrics_adapters_resources_updated_signal(qtbot):
    adapter = MagicMock()
    panel = SystemOverviewPanel(adapter)
    qtbot.addWidget(panel)

    adapter.resources_updated.connect.assert_called_once()
