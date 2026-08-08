"""Unit tests for ui.runtime_diagnostics_panel."""

from unittest.mock import MagicMock

from config.schema import UIConfig
from core.module_registry import ServiceState
from core.runtime_manager import RuntimeManager, ServiceTier
from ui.runtime_diagnostics_panel import RuntimeDiagnosticsPanel


class _StubLazyModule:
    """Satisfies LazyModule in full — mirrors tests/unit/core/
    test_runtime_manager.py's own _StubLazyModule, needed here since
    RuntimeManager.state_of()/tier_of()/is_lazy() all read real registered
    entries, not a mock."""

    def __init__(self) -> None:
        self._state = ServiceState.NOT_LOADED

    def start(self) -> None:
        self._state = ServiceState.READY

    def stop(self) -> None:
        self._state = ServiceState.UNLOADED

    def health_check(self) -> bool:
        return True

    def state(self) -> ServiceState:
        return self._state

    def last_used_at(self):
        return None

    def mark_idle_timeout(self, seconds: float) -> None:
        pass


class _StubLegacyModule:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def health_check(self) -> bool:
        return True


def _core_manager(runtime_manager: RuntimeManager, interval_ms: int = 3000) -> MagicMock:
    manager = MagicMock()
    manager.runtime_manager.return_value = runtime_manager
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    return manager


def test_refresh_shows_placeholder_when_no_services(qtbot):
    manager = _core_manager(RuntimeManager())
    panel = RuntimeDiagnosticsPanel(manager)
    qtbot.addWidget(panel)

    panel.refresh()

    assert "No services registered" in panel._services_label.text()


def test_refresh_shows_tier_lazy_and_state_for_a_legacy_module(qtbot):
    runtime_manager = RuntimeManager()
    runtime_manager.register("wake_word_detector", _StubLegacyModule(), ServiceTier.ALWAYS_LOADED)
    manager = _core_manager(runtime_manager)
    panel = RuntimeDiagnosticsPanel(manager)
    qtbot.addWidget(panel)

    panel.refresh()

    text = panel._services_label.text()
    assert "wake_word_detector" in text
    assert "tier=always_loaded" in text
    assert "lazy=False" in text
    assert "state=ready" in text


def test_refresh_shows_state_for_a_lazy_module(qtbot):
    runtime_manager = RuntimeManager()
    module = _StubLazyModule()
    runtime_manager.register("speech_to_text", module, ServiceTier.WARM, lazy=True)
    manager = _core_manager(runtime_manager)
    panel = RuntimeDiagnosticsPanel(manager)
    qtbot.addWidget(panel)

    panel.refresh()
    text_before_start = panel._services_label.text()
    module.start()
    panel.refresh()
    text_after_start = panel._services_label.text()

    assert "state=not_loaded" in text_before_start
    assert "state=ready" in text_after_start
    assert "lazy=True" in text_after_start


def test_initial_refresh_happens_on_construction(qtbot):
    runtime_manager = RuntimeManager()
    runtime_manager.register("task_scheduler", _StubLegacyModule(), ServiceTier.ALWAYS_LOADED)
    manager = _core_manager(runtime_manager)

    panel = RuntimeDiagnosticsPanel(manager)
    qtbot.addWidget(panel)

    assert "task_scheduler" in panel._services_label.text()


def test_timer_interval_comes_from_config_not_hardcoded(qtbot):
    manager = _core_manager(RuntimeManager(), interval_ms=1234)
    panel = RuntimeDiagnosticsPanel(manager)
    qtbot.addWidget(panel)

    assert panel._timer.interval() == 1234


def test_refresh_survives_a_failed_read_without_crashing(qtbot):
    """Regression test: refresh() runs on a QTimer callback with no caller
    to propagate an exception to — a failed read must not crash
    construction (which calls refresh() once) or any later timer tick."""
    manager = MagicMock()
    manager.runtime_manager.side_effect = RuntimeError("registry exploded")
    manager.ui_config.return_value = UIConfig()

    panel = RuntimeDiagnosticsPanel(manager)  # construction itself calls refresh() once
    qtbot.addWidget(panel)

    panel.refresh()  # must not raise on a later call either


def test_refresh_keeps_last_known_good_display_after_a_later_failure(qtbot):
    runtime_manager = RuntimeManager()
    runtime_manager.register("task_scheduler", _StubLegacyModule(), ServiceTier.ALWAYS_LOADED)
    manager = _core_manager(runtime_manager)
    panel = RuntimeDiagnosticsPanel(manager)
    qtbot.addWidget(panel)
    good_text = panel._services_label.text()

    manager.runtime_manager.side_effect = RuntimeError("registry exploded")
    panel.refresh()

    assert panel._services_label.text() == good_text
