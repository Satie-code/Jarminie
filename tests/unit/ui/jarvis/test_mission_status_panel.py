"""Unit tests for ui.jarvis.mission_status_panel."""

from unittest.mock import MagicMock

from config.schema import UIConfig
from core.module_registry import ServiceState
from ui.jarvis.mission_status_panel import MissionStatusPanel


def _core_manager(states: dict[str, ServiceState], interval_ms: int = 3000) -> MagicMock:
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    runtime_manager = MagicMock()
    runtime_manager.names.return_value = list(states.keys())
    runtime_manager.state_of.side_effect = lambda name: states[name]
    manager.runtime_manager.return_value = runtime_manager
    return manager


def test_shows_a_row_per_registered_service(qtbot):
    manager = _core_manager(
        {"memory_store": ServiceState.READY, "task_scheduler": ServiceState.IDLE}
    )
    panel = MissionStatusPanel(manager)
    qtbot.addWidget(panel)

    assert set(panel._row_labels.keys()) == {"memory_store", "task_scheduler"}


def test_row_text_includes_service_name_and_state(qtbot):
    manager = _core_manager({"memory_store": ServiceState.ACTIVE})
    panel = MissionStatusPanel(manager)
    qtbot.addWidget(panel)

    text = panel._row_labels["memory_store"].text()
    assert "memory_store" in text
    assert "active" in text


def test_refresh_removes_rows_for_services_no_longer_present(qtbot):
    manager = _core_manager(
        {"memory_store": ServiceState.READY, "task_scheduler": ServiceState.READY}
    )
    panel = MissionStatusPanel(manager)
    qtbot.addWidget(panel)

    manager.runtime_manager.return_value.names.return_value = ["memory_store"]
    panel.refresh()

    assert set(panel._row_labels.keys()) == {"memory_store"}


def test_refresh_updates_an_existing_rows_text_in_place(qtbot):
    manager = _core_manager({"memory_store": ServiceState.LOADING})
    panel = MissionStatusPanel(manager)
    qtbot.addWidget(panel)
    label = panel._row_labels["memory_store"]

    manager.runtime_manager.return_value.state_of.side_effect = lambda name: ServiceState.READY
    panel.refresh()

    assert panel._row_labels["memory_store"] is label  # same widget, reused
    assert "ready" in label.text()


def test_refresh_survives_a_failing_runtime_manager(qtbot):
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig()
    manager.runtime_manager.side_effect = RuntimeError("boom")

    panel = MissionStatusPanel(manager)  # construction itself calls refresh() once
    qtbot.addWidget(panel)

    panel.refresh()  # must not raise on a later call either


def test_no_services_registered_shows_no_rows(qtbot):
    manager = _core_manager({})
    panel = MissionStatusPanel(manager)
    qtbot.addWidget(panel)

    assert panel._row_labels == {}


def test_timer_interval_comes_from_config(qtbot):
    manager = _core_manager({}, interval_ms=1234)
    panel = MissionStatusPanel(manager)
    qtbot.addWidget(panel)

    assert panel._timer.interval() == 1234
