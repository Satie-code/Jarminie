"""Unit tests for ui.jarvis.hud_shell."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from PySide6.QtWidgets import QWidget

from config.schema import PresentationConfig, ResourceThresholds, UIConfig
from core.resource_monitor import ResourceSnapshot
from device_control.action_engine import ActionResult, ActionStatus
from ui.jarvis.hud_shell import HudShell
from ui.jarvis.navigation_rail import NavItem


def _core_manager():
    """JARVIS Holographic HUD reskin, Phase 5: HudShell now also builds
    a MetricsAdapter from core_manager, whose right-rail panels call
    real attributes on whatever check_resources()/runtime_manager()
    return — a bare, unconfigured MagicMock for either would let a
    MagicMock attribute (not a real float/ServiceState) reach
    CircularMetric.set_value()'s own arithmetic, an unpredictable and
    hard-to-debug way for an unrelated test to fail. Both are
    configured with real, minimal return values instead.

    Phase 7: resource_thresholds() backs AnimationManager's own
    ResourceMonitor — a real ResourceThresholds, not a bare MagicMock,
    for the identical reason.

    Phase 9: presentation_config() backs HudShell's own one-time
    jarvis_ui_accent read — a real PresentationConfig, not a bare
    MagicMock, so QColor(accent) never receives a MagicMock attribute."""
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig()
    manager.check_resources.return_value = ResourceSnapshot(
        cpu_percent=10.0,
        ram_percent=20.0,
        disk_percent=30.0,
        battery_percent=80.0,
        timestamp=datetime.now(UTC),
    )
    manager.resource_thresholds.return_value = ResourceThresholds()
    manager.presentation_config.return_value = PresentationConfig()
    runtime_manager = MagicMock()
    runtime_manager.names.return_value = []
    manager.runtime_manager.return_value = runtime_manager
    return manager


def _calendar_store():
    store = MagicMock()
    store.list_due_within.return_value = []
    return store


def _build_shell(host: QWidget | None = None) -> HudShell:
    return HudShell(
        _core_manager(),
        host if host is not None else QWidget(),
        _calendar_store(),
        MagicMock(),  # action_registry
        MagicMock(),  # voice_session_manager
        MagicMock(),  # pipeline
        MagicMock(),  # jarvis_renderer
    )


def test_constructs_with_all_five_zones(qtbot):
    shell = _build_shell()
    qtbot.addWidget(shell)

    assert shell.top_bar_zone is not None
    assert shell.left_zone is not None
    assert shell.center_zone is not None
    assert shell.right_zone is not None
    assert shell.command_bar_zone is not None


def test_presentation_host_widget_starts_in_center_zone(qtbot):
    host = QWidget()
    shell = _build_shell(host=host)
    qtbot.addWidget(shell)

    assert shell.center_zone.layout_().indexOf(host) != -1


def test_right_zone_holds_the_four_phase_5_panels(qtbot):
    """JARVIS Holographic HUD reskin, Phase 5: StatusPanel is gone from
    the right zone — System Overview/Temperature/Network/Active Modules
    supersede it (four widgets, matching the panels HudShell's own
    __init__ adds in that exact order)."""
    shell = _build_shell()
    qtbot.addWidget(shell)

    assert shell.right_zone.layout_().count() == 4


def test_system_overview_panel_is_populated_immediately_not_after_the_first_tick(qtbot):
    """Regression test: MetricsAdapter's own constructor-time refresh()
    fires before SystemOverviewPanel/ActiveModulesPanel have subscribed
    to it (both are constructed afterward) — without HudShell refreshing
    it again once every subscriber is wired up, the right rail would sit
    on N/A/empty until the first real QTimer tick, up to
    status_refresh_interval_ms (3s by default) after launch. Found by an
    actual screenshot during this phase's own verification, not assumed."""
    shell = _build_shell()
    qtbot.addWidget(shell)

    right_zone_layout = shell.right_zone.layout_()
    system_overview_panel = right_zone_layout.itemAt(0).widget()

    assert system_overview_panel._cpu._value == 10.0


def test_navigation_rail_lives_in_left_zone(qtbot):
    """JARVIS Holographic HUD reskin, Phase 10: navigation_rail is no
    longer a DIRECT child of left_zone's own layout — it now lives
    inside an inner scrollable container (see hud_shell.py's own Phase
    10 docstring) — so this checks ancestry via isAncestorOf() rather
    than the immediate layout's own indexOf()."""
    shell = _build_shell()
    qtbot.addWidget(shell)

    assert shell.left_zone.isAncestorOf(shell.navigation_rail)


def test_selecting_a_placeholder_page_swaps_out_the_presentation_host(qtbot):
    host = QWidget()
    shell = _build_shell(host=host)
    qtbot.addWidget(shell)

    shell.navigation_rail._buttons[NavItem.MEMORY].click()

    assert shell.center_zone.layout_().indexOf(host) == -1
    assert shell.center_zone.layout_().count() == 1


def test_selecting_dashboard_again_restores_the_presentation_host(qtbot):
    host = QWidget()
    shell = _build_shell(host=host)
    qtbot.addWidget(shell)
    shell.navigation_rail._buttons[NavItem.MEMORY].click()

    shell.navigation_rail._buttons[NavItem.DASHBOARD].click()

    assert shell.center_zone.layout_().indexOf(host) != -1


def test_placeholder_pages_are_cached_not_rebuilt(qtbot):
    shell = _build_shell()
    qtbot.addWidget(shell)

    shell.navigation_rail._buttons[NavItem.TASKS].click()
    first_page = shell._placeholder_pages[NavItem.TASKS]
    shell.navigation_rail._buttons[NavItem.DASHBOARD].click()
    shell.navigation_rail._buttons[NavItem.TASKS].click()

    assert shell._placeholder_pages[NavItem.TASKS] is first_page


def test_resize_keeps_hud_frame_covering_the_shell(qtbot):
    """resizeEvent() only fires synchronously once a widget has a real
    window handle — i.e. after show() — so this test shows the shell
    first, matching how MainWindow actually uses it (central widget of
    a shown QMainWindow), rather than resizing a never-shown widget."""
    shell = _build_shell()
    qtbot.addWidget(shell)
    shell.show()

    shell.resize(1000, 700)

    assert shell._hud_frame.rect().width() == shell.rect().width()
    assert shell._hud_frame.rect().height() == shell.rect().height()


def test_code_nav_item_is_enabled_now_that_action_registry_exists(qtbot):
    """JARVIS Holographic HUD reskin, Phase 4: Phase 2 left the rail's
    Code button disabled specifically until HudShell had a real
    ActionRegistry — this phase gives it one."""
    shell = _build_shell()
    qtbot.addWidget(shell)

    assert shell.navigation_rail._buttons[NavItem.CODE].isEnabled()


def test_system_stats_requested_bubbles_up_from_quick_commands_panel(qtbot):
    shell = _build_shell()
    qtbot.addWidget(shell)
    received = []
    shell.system_stats_requested.connect(lambda: received.append(True))

    shell.quick_commands_panel.system_stats_requested.emit()

    assert received == [True]


def test_code_nav_item_dispatches_the_same_action_as_the_quick_commands_button(qtbot):
    action_registry = MagicMock()
    action_registry.dispatch.return_value = ActionResult(
        request=MagicMock(), status=ActionStatus.SUCCEEDED, completed_at=datetime.now(UTC)
    )
    shell = HudShell(
        _core_manager(),
        QWidget(),
        _calendar_store(),
        action_registry,
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    qtbot.addWidget(shell)

    shell.navigation_rail._buttons[NavItem.CODE].click()

    action_registry.dispatch.assert_called_once()
