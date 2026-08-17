"""Unit tests for ui.jarvis.active_modules_panel."""

from unittest.mock import MagicMock

from core.module_registry import ServiceState
from ui.jarvis.active_modules_panel import ActiveModulesPanel


def test_shows_a_row_per_module(qtbot):
    panel = ActiveModulesPanel(MagicMock())
    qtbot.addWidget(panel)

    panel._on_runtime_updated(
        {"voice_session_manager": ServiceState.ACTIVE, "learning_engine": ServiceState.IDLE}
    )

    assert set(panel._row_labels.keys()) == {"voice_session_manager", "learning_engine"}


def test_row_text_includes_name_and_uppercased_state(qtbot):
    panel = ActiveModulesPanel(MagicMock())
    qtbot.addWidget(panel)

    panel._on_runtime_updated({"voice_session_manager": ServiceState.ACTIVE})

    text = panel._row_labels["voice_session_manager"].text()
    assert "voice_session_manager" in text
    assert "ACTIVE" in text


def test_removes_rows_for_modules_no_longer_present(qtbot):
    panel = ActiveModulesPanel(MagicMock())
    qtbot.addWidget(panel)
    panel._on_runtime_updated(
        {"memory_store": ServiceState.READY, "task_scheduler": ServiceState.READY}
    )

    panel._on_runtime_updated({"memory_store": ServiceState.READY})

    assert set(panel._row_labels.keys()) == {"memory_store"}


def test_updates_an_existing_row_in_place(qtbot):
    panel = ActiveModulesPanel(MagicMock())
    qtbot.addWidget(panel)
    panel._on_runtime_updated({"memory_store": ServiceState.LOADING})
    label = panel._row_labels["memory_store"]

    panel._on_runtime_updated({"memory_store": ServiceState.READY})

    assert panel._row_labels["memory_store"] is label
    assert "READY" in label.text()


def test_subscribes_to_the_metrics_adapters_runtime_updated_signal(qtbot):
    adapter = MagicMock()
    panel = ActiveModulesPanel(adapter)
    qtbot.addWidget(panel)

    adapter.runtime_updated.connect.assert_called_once()
