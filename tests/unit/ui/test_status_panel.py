"""Unit tests for ui.status_panel."""

from unittest.mock import MagicMock

from config.schema import UIConfig
from ui.status_panel import StatusPanel


def _core_manager(resource_snapshot_factory, module_states=None, snapshot=None, interval_ms=3000):
    manager = MagicMock()
    manager.module_states.return_value = module_states if module_states is not None else {}
    manager.check_resources.return_value = snapshot or resource_snapshot_factory()
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    return manager


def test_refresh_updates_module_label(qtbot, resource_snapshot_factory):
    manager = _core_manager(
        resource_snapshot_factory, module_states={"voice": "running", "memory": "stopped"}
    )
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)

    panel.refresh()

    text = panel._module_label.text()
    assert "voice: running" in text
    assert "memory: stopped" in text


def test_refresh_shows_placeholder_when_no_modules(qtbot, resource_snapshot_factory):
    manager = _core_manager(resource_snapshot_factory, module_states={})
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)

    panel.refresh()

    assert "No modules registered" in panel._module_label.text()


def test_refresh_updates_resource_label(qtbot, resource_snapshot_factory):
    snapshot = resource_snapshot_factory(
        cpu_percent=42.0, ram_percent=55.0, disk_percent=60.0, battery_percent=77.0
    )
    manager = _core_manager(resource_snapshot_factory, snapshot=snapshot)
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)

    panel.refresh()

    text = panel._resource_label.text()
    assert "42" in text
    assert "55" in text
    assert "60" in text
    assert "77" in text


def test_refresh_handles_missing_battery(qtbot, resource_snapshot_factory):
    manager = _core_manager(
        resource_snapshot_factory, snapshot=resource_snapshot_factory(battery_percent=None)
    )
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)

    panel.refresh()

    assert "n/a" in panel._resource_label.text()


def test_initial_refresh_happens_on_construction(qtbot, resource_snapshot_factory):
    manager = _core_manager(resource_snapshot_factory, module_states={"voice": "running"})
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)

    assert "voice: running" in panel._module_label.text()


def test_timer_interval_comes_from_config_not_hardcoded(qtbot, resource_snapshot_factory):
    manager = _core_manager(resource_snapshot_factory, interval_ms=1234)
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)

    assert panel._timer.interval() == 1234


def test_timer_does_not_poll_faster_than_configured_interval(qtbot, resource_snapshot_factory):
    manager = _core_manager(resource_snapshot_factory, interval_ms=50)
    panel = StatusPanel(manager)
    qtbot.addWidget(panel)

    calls_before = manager.check_resources.call_count
    qtbot.wait(220)  # ~4 intervals at 50ms

    new_calls = manager.check_resources.call_count - calls_before
    assert 1 <= new_calls <= 10
