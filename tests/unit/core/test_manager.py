"""Unit tests for core.manager."""

import logging
from unittest.mock import MagicMock

from config.schema import AppConfig, ResourceThresholds, UIConfig
from core.manager import CoreManager
from core.module_registry import ServiceState
from core.runtime_manager import RuntimeManager, ServiceTier


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


class _RecordingLazyModule(_RecordingModule):
    """Satisfies LazyModule in full (Runtime Phase 9's own
    idle_timeout_seconds passthrough test needs a real mark_idle_timeout()
    to assert against — _RecordingModule above only satisfies plain
    ManagedModule)."""

    def __init__(self, name: str, calls: list[str]) -> None:
        super().__init__(name, calls)
        self.marked_idle_timeout: float | None = None

    def state(self) -> ServiceState:
        return ServiceState.READY

    def last_used_at(self):
        return None

    def mark_idle_timeout(self, seconds: float) -> None:
        self.marked_idle_timeout = seconds


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


def test_resource_thresholds_returns_the_resources_slice_of_the_injected_config():
    config = AppConfig(resources=ResourceThresholds(cpu_warning_percent=55.0))
    manager = CoreManager(config=config, resource_monitor=MagicMock(), config_loader=MagicMock())

    assert manager.resource_thresholds().cpu_warning_percent == 55.0


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


def test_start_and_stop_emit_timing_log_records(caplog):
    """Runtime Phase 1 (Baseline & Instrumentation) — every module
    start()/stop() and the overall startup()/shutdown() must log a
    duration, so later Runtime Phases can measure real before/after
    numbers instead of estimating them. Deliberately asserts only that a
    record was emitted, never a specific timing value — timing is
    inherently non-deterministic."""
    manager = _manager()
    manager.register_module("a", _RecordingModule("a", []))

    with caplog.at_level(logging.INFO):
        manager.startup()
        manager.shutdown()

    assert any("Module started: a" in record.message for record in caplog.records)
    assert any("Module stopped: a" in record.message for record in caplog.records)
    assert any("JARMINEI Core startup complete" in record.message for record in caplog.records)
    assert any("JARMINEI Core shutdown complete" in record.message for record in caplog.records)


def test_runtime_manager_defaults_to_a_fresh_instance_when_not_injected():
    manager = _manager()

    assert isinstance(manager.runtime_manager(), RuntimeManager)


def test_runtime_manager_returns_the_injected_instance():
    runtime_manager = RuntimeManager()
    manager = CoreManager(
        config=AppConfig(),
        resource_monitor=MagicMock(),
        config_loader=MagicMock(),
        runtime_manager=runtime_manager,
    )

    assert manager.runtime_manager() is runtime_manager


def test_register_module_defaults_to_always_loaded_tier_and_not_lazy():
    manager = _manager()

    manager.register_module("a", _RecordingModule("a", []))

    assert manager.runtime_manager().tier_of("a") is ServiceTier.ALWAYS_LOADED
    assert manager.runtime_manager().is_lazy("a") is False


def test_register_module_threads_explicit_tier_and_lazy_through():
    manager = _manager()

    manager.register_module(
        "stt", _RecordingModule("stt", []), tier=ServiceTier.WARM, lazy=True
    )

    assert manager.runtime_manager().tier_of("stt") is ServiceTier.WARM
    assert manager.runtime_manager().is_lazy("stt") is True


def test_register_module_forwards_idle_timeout_seconds_to_a_lazy_module():
    """Runtime Phase 9 — idle_timeout_seconds is passed straight through
    to RuntimeManager.register(), which forwards it to the module's own
    mark_idle_timeout()."""
    manager = _manager()
    module = _RecordingLazyModule("stt", [])

    manager.register_module(
        "stt", module, tier=ServiceTier.WARM, lazy=True, idle_timeout_seconds=300.0
    )

    assert module.marked_idle_timeout == 300.0


def test_startup_still_starts_modules_in_registration_order_regardless_of_tier():
    """Runtime Phase 3 anchor test: tier/lazy metadata is now tracked
    alongside every registration, but startup()'s own control flow is
    completely untouched until Runtime Phase 4 — this proves it."""
    manager = _manager()
    calls: list[str] = []
    manager.register_module("a", _RecordingModule("a", calls), tier=ServiceTier.WARM, lazy=True)
    manager.register_module("b", _RecordingModule("b", calls))

    manager.startup()

    assert calls == ["a.start", "b.start"]


def test_startup_tier_only_starts_modules_registered_in_that_tier():
    manager = _manager()
    calls: list[str] = []
    manager.register_module("a", _RecordingModule("a", calls), tier=ServiceTier.ALWAYS_LOADED)
    manager.register_module("b", _RecordingModule("b", calls), tier=ServiceTier.WARM)
    manager.register_module("c", _RecordingModule("c", calls), tier=ServiceTier.COLD)

    manager.startup_tier(ServiceTier.WARM)

    assert calls == ["b.start"]
    assert manager.module_states()["b"] == "running"
    assert manager.module_states()["a"] == "registered"
    assert manager.module_states()["c"] == "registered"


def test_startup_tier_preserves_relative_registration_order_within_the_tier():
    manager = _manager()
    calls: list[str] = []
    manager.register_module("first", _RecordingModule("first", calls), tier=ServiceTier.WARM)
    manager.register_module(
        "interleaved", _RecordingModule("interleaved", calls), tier=ServiceTier.ALWAYS_LOADED
    )
    manager.register_module("second", _RecordingModule("second", calls), tier=ServiceTier.WARM)

    manager.startup_tier(ServiceTier.WARM)

    assert calls == ["first.start", "second.start"]


def test_startup_tier_called_multiple_times_covers_every_tier_exactly_once():
    manager = _manager()
    calls: list[str] = []
    manager.register_module("a", _RecordingModule("a", calls))
    manager.register_module("b", _RecordingModule("b", calls), tier=ServiceTier.WARM)
    manager.register_module("c", _RecordingModule("c", calls), tier=ServiceTier.COLD)

    manager.startup_tier(ServiceTier.ALWAYS_LOADED)
    manager.startup_tier(ServiceTier.WARM)
    manager.startup_tier(ServiceTier.COLD)

    assert calls == ["a.start", "b.start", "c.start"]


def test_startup_tier_module_failure_does_not_block_other_modules_in_the_same_tier():
    manager = _manager()
    calls: list[str] = []
    manager.register_module(
        "broken", _RecordingModule("broken", calls, fail_on="start"), tier=ServiceTier.WARM
    )
    manager.register_module("ok", _RecordingModule("ok", calls), tier=ServiceTier.WARM)

    manager.startup_tier(ServiceTier.WARM)  # must not raise

    assert calls == ["ok.start"]
    assert manager.module_states()["broken"] == "failed"
    assert manager.module_states()["ok"] == "running"
