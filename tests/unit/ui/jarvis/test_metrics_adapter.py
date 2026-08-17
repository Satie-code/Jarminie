"""Unit tests for ui.jarvis.metrics_adapter."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from config.schema import UIConfig
from core.module_registry import ServiceState
from core.resource_monitor import ResourceSnapshot
from ui.jarvis.metrics_adapter import MetricsAdapter


def _core_manager(interval_ms: int = 3000) -> MagicMock:
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    manager.check_resources.return_value = ResourceSnapshot(
        cpu_percent=10.0, ram_percent=20.0, disk_percent=30.0, battery_percent=80.0,
        timestamp=datetime.now(UTC),
    )
    runtime_manager = MagicMock()
    runtime_manager.names.return_value = ["memory_store"]
    runtime_manager.state_of.return_value = ServiceState.READY
    manager.runtime_manager.return_value = runtime_manager
    return manager


def test_emits_resources_updated_on_construction(qtbot):
    manager = _core_manager()
    adapter = MetricsAdapter(manager)

    received = []
    adapter.resources_updated.connect(received.append)
    adapter.refresh()

    assert len(received) == 1
    assert received[0].cpu_percent == 10.0


def test_emits_runtime_updated_on_construction(qtbot):
    manager = _core_manager()
    adapter = MetricsAdapter(manager)

    received = []
    adapter.runtime_updated.connect(received.append)
    adapter.refresh()

    assert received == [{"memory_store": ServiceState.READY}]


def test_timer_interval_comes_from_config(qtbot):
    adapter = MetricsAdapter(_core_manager(interval_ms=1234))

    assert adapter._timer.interval() == 1234


def test_a_failing_resource_sample_does_not_suppress_a_working_runtime_read(qtbot):
    manager = _core_manager()
    manager.check_resources.side_effect = RuntimeError("boom")
    adapter = MetricsAdapter(manager)

    resource_events = []
    runtime_events = []
    adapter.resources_updated.connect(resource_events.append)
    adapter.runtime_updated.connect(runtime_events.append)
    adapter.refresh()

    assert resource_events == []
    assert len(runtime_events) == 1


def test_a_failing_runtime_read_does_not_suppress_a_working_resource_sample(qtbot):
    manager = _core_manager()
    manager.runtime_manager.side_effect = RuntimeError("boom")
    adapter = MetricsAdapter(manager)

    resource_events = []
    runtime_events = []
    adapter.resources_updated.connect(resource_events.append)
    adapter.runtime_updated.connect(runtime_events.append)
    adapter.refresh()

    assert len(resource_events) == 1
    assert runtime_events == []


def test_refresh_survives_both_sources_failing(qtbot):
    manager = _core_manager()
    manager.check_resources.side_effect = RuntimeError("boom")
    manager.runtime_manager.side_effect = RuntimeError("boom")

    adapter = MetricsAdapter(manager)  # construction itself calls refresh() once

    adapter.refresh()  # must not raise on a later call either
