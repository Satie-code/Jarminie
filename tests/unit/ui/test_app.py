"""Unit tests for ui.app.

Runtime Phase 4 (Runtime Refactor Sprint) — the first test to ever
exercise run_app() at all. Uses a real CoreManager (not the MagicMock-
based mock_core_manager fixture other tests/unit/ui/ files share) since
the whole point here is proving the real Tier A -> show() -> background
Tier B/C ordering, driven by synthetic tiers rather than any real
subsystem (main.py itself doesn't tag anything WARM/COLD until Runtime
Phases 5-8).
"""

import threading
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from config.schema import AppConfig
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
from core.runtime_manager import ServiceTier
from ui.app import run_app
from ui.main_window import MainWindow

WAIT_TIMEOUT = 5.0


class _FastModule:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")

    def health_check(self) -> bool:
        return True


class _SlowWarmModule:
    """start() blocks until the test signals release_event — stands in
    for a real Tier B module (e.g. Whisper/Coqui, once Runtime Phase 5
    retags them) whose load must not be waited on before the window
    shows."""

    def __init__(self, release_event: threading.Event) -> None:
        self._release_event = release_event
        self.started = threading.Event()

    def start(self) -> None:
        self._release_event.wait(timeout=WAIT_TIMEOUT)
        self.started.set()

    def stop(self) -> None:
        pass

    def health_check(self) -> bool:
        return True


def _real_core_manager() -> CoreManager:
    resource_monitor = ResourceMonitor(AppConfig().resources)
    return CoreManager(AppConfig(), resource_monitor, config_loader=MagicMock())


def test_run_app_shows_window_before_a_warm_tier_module_finishes_loading(
    qtbot, monkeypatch, mock_presentation_handles
):
    """The core Runtime Phase 4 guarantee: the window appears without
    waiting for a slow WARM-tier service to finish loading."""
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)

    core_manager = _real_core_manager()
    core_manager.register_module("always", _FastModule(), tier=ServiceTier.ALWAYS_LOADED)
    release_event = threading.Event()
    slow_module = _SlowWarmModule(release_event)
    core_manager.register_module("warm", slow_module, tier=ServiceTier.WARM)

    shown = threading.Event()
    original_show = MainWindow.show

    def _tracking_show(self) -> None:
        shown.set()
        original_show(self)

    monkeypatch.setattr(MainWindow, "show", _tracking_show)

    exit_code = run_app(core_manager, **mock_presentation_handles)

    # run_app() has already returned (app.exec() is mocked to return
    # immediately), but the background warm-up thread is still blocked
    # inside slow_module.start(), waiting on release_event — which this
    # test hasn't set yet. This is the actual proof: the window was
    # already shown while a WARM-tier module was still loading.
    assert exit_code == 0
    assert shown.is_set()
    assert not slow_module.started.is_set()
    assert core_manager.module_states()["always"] == "running"

    # Let the background thread finish before the test ends, so it isn't
    # still running against this CoreManager once the next test starts.
    release_event.set()
    assert slow_module.started.wait(timeout=WAIT_TIMEOUT)


def test_run_app_fully_starts_tier_a_before_window_show(
    qtbot, monkeypatch, mock_presentation_handles
):
    """Not just "eventually" — Tier A must be fully RUNNING by the exact
    moment window.show() is called, not merely registered or in
    progress."""
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)

    core_manager = _real_core_manager()
    core_manager.register_module("always", _FastModule(), tier=ServiceTier.ALWAYS_LOADED)

    state_when_shown = []
    original_show = MainWindow.show

    def _tracking_show(self) -> None:
        state_when_shown.append(core_manager.module_states().get("always"))
        original_show(self)

    monkeypatch.setattr(MainWindow, "show", _tracking_show)

    run_app(core_manager, **mock_presentation_handles)

    assert state_when_shown == ["running"]


def test_background_warm_up_starts_warm_then_cold_in_registration_order(
    qtbot, monkeypatch, mock_presentation_handles
):
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)

    core_manager = _real_core_manager()
    warm_module = _FastModule()
    cold_module = _FastModule()
    core_manager.register_module("warm", warm_module, tier=ServiceTier.WARM)
    core_manager.register_module("cold", cold_module, tier=ServiceTier.COLD)

    run_app(core_manager, **mock_presentation_handles)

    def _both_started() -> bool:
        return warm_module.calls == ["start"] and cold_module.calls == ["start"]

    qtbot.waitUntil(_both_started, timeout=int(WAIT_TIMEOUT * 1000))
    assert _both_started()
