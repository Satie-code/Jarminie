"""Unit tests for presentation.presentation_host_widget (Sprint 5.14;
the widened exception guard and the deferred-bookkeeping-update fix are
both Sprint 5.16 Post-Sprint Fixes, found during that sprint's own
adversarial re-read — no dedicated test file existed for this class
before now).
"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QWidget

from presentation.presentation_host_widget import PresentationHostWidget


def _core_manager(interval_ms: int = 3000) -> MagicMock:
    manager = MagicMock()
    manager.ui_config.return_value.status_refresh_interval_ms = interval_ms
    return manager


@pytest.fixture
def presentation_controller() -> MagicMock:
    controller = MagicMock()
    controller.mounted_persona_name = None
    return controller


@pytest.fixture
def jarvis_renderer(qtbot) -> MagicMock:
    renderer = MagicMock()
    renderer.widget.return_value = QWidget()
    return renderer


@pytest.fixture
def minie_renderer(qtbot) -> MagicMock:
    renderer = MagicMock()
    renderer.status_widget.return_value = QWidget()
    return renderer


@pytest.fixture
def host_widget(qtbot, presentation_controller, jarvis_renderer, minie_renderer):
    widget = PresentationHostWidget(
        presentation_controller, jarvis_renderer, minie_renderer, _core_manager()
    )
    qtbot.addWidget(widget)
    return widget


def test_nothing_mounted_displays_nothing(host_widget):
    assert host_widget._displayed_widget is None
    assert host_widget._displayed_persona_name is None


def test_jarvis_mounted_embeds_jarvis_widget(host_widget, presentation_controller, jarvis_renderer):
    presentation_controller.mounted_persona_name = "jarvis"

    host_widget.refresh()

    jarvis_renderer.widget.assert_called_once()
    assert host_widget._displayed_persona_name == "jarvis"
    assert host_widget._displayed_widget is jarvis_renderer.widget.return_value


def test_minie_mounted_embeds_minie_status_widget(
    host_widget, presentation_controller, minie_renderer
):
    presentation_controller.mounted_persona_name = "minie"

    host_widget.refresh()

    minie_renderer.status_widget.assert_called_once()
    assert host_widget._displayed_persona_name == "minie"


def test_switching_personas_replaces_the_displayed_widget(
    host_widget, presentation_controller, jarvis_renderer, minie_renderer
):
    presentation_controller.mounted_persona_name = "jarvis"
    host_widget.refresh()
    first_widget = host_widget._displayed_widget

    presentation_controller.mounted_persona_name = "minie"
    host_widget.refresh()

    assert host_widget._displayed_widget is minie_renderer.status_widget.return_value
    assert host_widget._displayed_widget is not first_widget


def test_refresh_is_a_noop_when_the_mounted_persona_has_not_changed(
    host_widget, presentation_controller, jarvis_renderer
):
    presentation_controller.mounted_persona_name = "jarvis"
    host_widget.refresh()
    jarvis_renderer.widget.reset_mock()

    host_widget.refresh()

    jarvis_renderer.widget.assert_not_called()


# --- Fail Gracefully (Sprint 5.16 Post-Sprint Fixes) --------------------------


def test_refresh_never_raises_when_mounted_persona_name_raises(
    qtbot, jarvis_renderer, minie_renderer
):
    class _RaisingController:
        @property
        def mounted_persona_name(self):
            raise RuntimeError("read failed")

    widget = PresentationHostWidget(
        _RaisingController(), jarvis_renderer, minie_renderer, _core_manager()
    )
    qtbot.addWidget(widget)

    widget.refresh()  # must not raise


def test_refresh_never_raises_when_widget_construction_raises(
    host_widget, presentation_controller, jarvis_renderer
):
    presentation_controller.mounted_persona_name = "jarvis"
    jarvis_renderer.widget.side_effect = RuntimeError("widget() exploded")

    host_widget.refresh()  # must not raise

    assert host_widget._displayed_widget is None


def test_a_failed_swap_leaves_bookkeeping_out_of_sync_so_the_next_tick_retries(
    host_widget, presentation_controller, jarvis_renderer
):
    """The real second gap found alongside the missing guard: previously,
    _displayed_persona_name was set to the new mounted_name BEFORE the
    widget was actually built, so a failure here permanently short-
    circuited every future refresh() (mounted_name == _displayed_persona_name
    would already match). Now a failed swap leaves them genuinely out of
    sync, so the very next refresh() call retries for real."""
    presentation_controller.mounted_persona_name = "jarvis"
    jarvis_renderer.widget.side_effect = RuntimeError("widget() exploded")
    host_widget.refresh()
    assert host_widget._displayed_persona_name != "jarvis"

    jarvis_renderer.widget.side_effect = None
    jarvis_renderer.widget.return_value = QWidget()
    host_widget.refresh()

    assert host_widget._displayed_persona_name == "jarvis"
    assert host_widget._displayed_widget is jarvis_renderer.widget.return_value
