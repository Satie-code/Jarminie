"""Unit tests for core.manager."""

from unittest.mock import MagicMock

from config.schema import AppConfig, UIConfig
from core.manager import CoreManager


class _RecordingModule:
    def __init__(self, name: str, calls: list[str], fail_on: str | None = None) -> None:
        self._name = name
        self._calls = calls
        self._fail_on = fail_on

    def start(self) -> None:
        if self._fail_on == "start":
            raise RuntimeError(f"{self._name} failed to start")
        self._calls.append(f"{self._name}.start")

    def stop(self) -> None:
        if self._fail_on == "stop":
            raise RuntimeError(f"{self._name} failed to stop")
        self._calls.append(f"{self._name}.stop")

    def health_check(self) -> bool:
        if self._fail_on == "health_check":
            raise RuntimeError(f"{self._name} health check failed")
        return True


def _manager() -> CoreManager:
    return CoreManager(config=AppConfig(), resource_monitor=MagicMock(), config_loader=MagicMock())


def test_startup_starts_all_modules_in_registration_order():
    manager = _manager()
    calls: list[str] = []
    manager.register_module("a", _RecordingModule("a", calls))
    manager.register_module("b", _RecordingModule("b", calls))

    manager.startup()

    assert calls == ["a.start", "b.start"]


def test_shutdown_stops_all_modules_in_reverse_order():
    manager = _manager()
    calls: list[str] = []
    manager.register_module("a", _RecordingModule("a", calls))
    manager.register_module("b", _RecordingModule("b", calls))
    manager.startup()
    calls.clear()

    manager.shutdown()

    assert calls == ["b.stop", "a.stop"]


def test_module_start_failure_does_not_block_other_modules():
    manager = _manager()
    calls: list[str] = []
    manager.register_module("broken", _RecordingModule("broken", calls, fail_on="start"))
    manager.register_module("ok", _RecordingModule("ok", calls))

    manager.startup()  # must not raise

    assert calls == ["ok.start"]
    assert manager.module_states()["broken"] == "failed"
    assert manager.module_states()["ok"] == "running"


def test_module_stop_failure_is_caught_and_logged():
    manager = _manager()
    calls: list[str] = []
    manager.register_module("broken", _RecordingModule("broken", calls, fail_on="stop"))
    manager.startup()

    manager.shutdown()  # must not raise

    assert manager.module_states()["broken"] == "failed"


def test_restart_module_stops_then_starts():
    manager = _manager()
    calls: list[str] = []
    manager.register_module("a", _RecordingModule("a", calls))
    manager.startup()
    calls.clear()

    result = manager.restart_module("a")

    assert result is True
    assert calls == ["a.stop", "a.start"]
    assert manager.module_states()["a"] == "running"


def test_restart_attempts_start_even_if_stop_failed():
    manager = _manager()
    calls: list[str] = []
    manager.register_module("flaky", _RecordingModule("flaky", calls, fail_on="stop"))
    manager.startup()
    calls.clear()

    manager.restart_module("flaky")

    assert calls == ["flaky.start"]
    assert manager.module_states()["flaky"] == "running"


def test_check_health_returns_true_when_healthy():
    manager = _manager()
    manager.register_module("a", _RecordingModule("a", []))

    assert manager.check_health("a") is True


def test_check_health_returns_false_when_health_check_raises():
    manager = _manager()
    manager.register_module("broken", _RecordingModule("broken", [], fail_on="health_check"))

    assert manager.check_health("broken") is False


def test_check_health_of_unregistered_module_returns_false_not_keyerror():
    manager = _manager()

    assert manager.check_health("does-not-exist") is False


def test_restart_module_of_unregistered_module_returns_false_not_keyerror():
    manager = _manager()

    assert manager.restart_module("does-not-exist") is False


def test_check_resources_delegates_to_resource_monitor():
    resource_monitor = MagicMock()
    manager = CoreManager(
        config=AppConfig(), resource_monitor=resource_monitor, config_loader=MagicMock()
    )

    manager.check_resources()

    resource_monitor.sample.assert_called_once()


def test_ui_config_returns_the_ui_slice_of_the_injected_config():
    config = AppConfig(ui=UIConfig(status_refresh_interval_ms=1234))
    manager = CoreManager(config=config, resource_monitor=MagicMock(), config_loader=MagicMock())

    assert manager.ui_config().status_refresh_interval_ms == 1234


def test_config_returns_the_injected_config():
    config = AppConfig()
    manager = CoreManager(config=config, resource_monitor=MagicMock(), config_loader=MagicMock())

    assert manager.config() is config


def test_config_loader_returns_the_injected_loader():
    config_loader = MagicMock()
    manager = CoreManager(
        config=AppConfig(), resource_monitor=MagicMock(), config_loader=config_loader
    )

    assert manager.config_loader() is config_loader
