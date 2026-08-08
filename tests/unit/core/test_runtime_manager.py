"""Unit tests for core.runtime_manager.

Runtime Phase 2 (Runtime Refactor Sprint) — RuntimeManager has no
consumers in the real app yet (that arrives with Runtime Phase 3), so
every test here drives it in isolation against local doubles, mirroring
the existing _RecordingModule/_StubModule pattern from
tests/unit/core/test_manager.py and test_module_registry.py.
"""

from datetime import UTC, datetime, timedelta

import pytest

from core.module_registry import ServiceState
from core.runtime_manager import RuntimeManager, ServiceTier


class _StubLazyModule:
    """Satisfies LazyModule in full — start()/stop() drive a real
    internal ServiceState so tests can assert on RuntimeManager's own
    state_of()/ensure_started()/stop_service() logic without needing a
    real subsystem."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._state = ServiceState.NOT_LOADED
        self.last_used_at_value: datetime | None = None

    def start(self) -> None:
        self.calls.append("start")
        self._state = ServiceState.READY

    def stop(self) -> None:
        self.calls.append("stop")
        self._state = ServiceState.UNLOADED

    def health_check(self) -> bool:
        return self._state in (ServiceState.READY, ServiceState.ACTIVE, ServiceState.IDLE)

    def state(self) -> ServiceState:
        return self._state

    def last_used_at(self) -> datetime | None:
        return self.last_used_at_value

    def mark_idle_timeout(self, seconds: float) -> None:
        self.calls.append(f"mark_idle_timeout:{seconds}")


class _StubLegacyModule:
    """Satisfies only plain ManagedModule — no state()/last_used_at()/
    mark_idle_timeout(). Registered with lazy=False (the default)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")

    def health_check(self) -> bool:
        return True


def test_register_and_tier_of():
    manager = RuntimeManager()
    manager.register("stt", _StubLazyModule(), ServiceTier.WARM, lazy=True)

    assert manager.tier_of("stt") is ServiceTier.WARM


def test_register_duplicate_raises():
    manager = RuntimeManager()
    manager.register("stt", _StubLazyModule(), ServiceTier.WARM, lazy=True)

    with pytest.raises(ValueError, match="already registered"):
        manager.register("stt", _StubLazyModule(), ServiceTier.WARM, lazy=True)


def test_names_preserves_registration_order():
    manager = RuntimeManager()
    manager.register("a", _StubLegacyModule(), ServiceTier.ALWAYS_LOADED)
    manager.register("b", _StubLegacyModule(), ServiceTier.ALWAYS_LOADED)

    assert manager.names() == ["a", "b"]


def test_is_lazy_reflects_registration_flag():
    manager = RuntimeManager()
    manager.register("legacy", _StubLegacyModule(), ServiceTier.ALWAYS_LOADED)
    manager.register("lazy", _StubLazyModule(), ServiceTier.WARM, lazy=True)

    assert manager.is_lazy("legacy") is False
    assert manager.is_lazy("lazy") is True


def test_state_of_legacy_module_is_always_ready():
    manager = RuntimeManager()
    manager.register("legacy", _StubLegacyModule(), ServiceTier.ALWAYS_LOADED)

    assert manager.state_of("legacy") is ServiceState.READY


def test_state_of_lazy_module_delegates_to_module_state():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True)

    assert manager.state_of("lazy") is ServiceState.NOT_LOADED
    module.start()
    assert manager.state_of("lazy") is ServiceState.READY


def test_ensure_started_loads_a_not_loaded_lazy_module():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True)

    manager.ensure_started("lazy")

    assert module.calls == ["start"]
    assert manager.state_of("lazy") is ServiceState.READY


def test_ensure_started_is_idempotent_once_ready():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True)

    manager.ensure_started("lazy")
    manager.ensure_started("lazy")

    assert module.calls == ["start"]


def test_ensure_started_reloads_after_stop_service():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True)
    manager.ensure_started("lazy")
    manager.stop_service("lazy")

    manager.ensure_started("lazy")

    assert module.calls == ["start", "stop", "start"]


def test_ensure_started_never_calls_start_on_a_legacy_module():
    manager = RuntimeManager()
    module = _StubLegacyModule()
    manager.register("legacy", module, ServiceTier.ALWAYS_LOADED, lazy=False)

    manager.ensure_started("legacy")

    assert module.calls == []


def test_stop_service_unloads_a_loaded_lazy_module():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True)
    manager.ensure_started("lazy")

    manager.stop_service("lazy")

    assert module.calls == ["start", "stop"]
    assert manager.state_of("lazy") is ServiceState.UNLOADED


def test_stop_service_is_a_noop_when_already_not_loaded():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True)

    manager.stop_service("lazy")

    assert module.calls == []


def test_stop_service_never_calls_stop_on_a_legacy_module():
    manager = RuntimeManager()
    module = _StubLegacyModule()
    manager.register("legacy", module, ServiceTier.ALWAYS_LOADED, lazy=False)

    manager.stop_service("legacy")

    assert module.calls == []


# --- Runtime Phase 9 (Runtime Refactor Sprint) — idle-timeout / resource-pressure eviction ---


def test_register_forwards_idle_timeout_to_a_lazy_module():
    manager = RuntimeManager()
    module = _StubLazyModule()

    manager.register("lazy", module, ServiceTier.WARM, lazy=True, idle_timeout_seconds=300.0)

    assert module.calls == ["mark_idle_timeout:300.0"]


def test_register_never_calls_mark_idle_timeout_on_a_legacy_module():
    manager = RuntimeManager()
    module = _StubLegacyModule()

    manager.register(
        "legacy", module, ServiceTier.ALWAYS_LOADED, lazy=False, idle_timeout_seconds=300.0
    )

    assert module.calls == []


def test_sweep_idle_services_evicts_a_service_past_its_idle_timeout():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True, idle_timeout_seconds=60.0)
    manager.ensure_started("lazy")
    module.last_used_at_value = datetime.now(UTC) - timedelta(seconds=61.0)

    evicted = manager.sweep_idle_services()

    assert evicted == ["lazy"]
    assert manager.state_of("lazy") is ServiceState.UNLOADED


def test_sweep_idle_services_leaves_a_service_within_its_idle_timeout():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True, idle_timeout_seconds=60.0)
    manager.ensure_started("lazy")
    module.last_used_at_value = datetime.now(UTC) - timedelta(seconds=5.0)

    evicted = manager.sweep_idle_services()

    assert evicted == []
    assert manager.state_of("lazy") is ServiceState.READY


def test_sweep_idle_services_never_evicts_a_service_mid_request():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True, idle_timeout_seconds=60.0)
    manager.ensure_started("lazy")
    module._state = ServiceState.ACTIVE
    module.last_used_at_value = datetime.now(UTC) - timedelta(seconds=999.0)

    evicted = manager.sweep_idle_services()

    assert evicted == []
    assert manager.state_of("lazy") is ServiceState.ACTIVE


def test_sweep_idle_services_skips_a_service_never_actually_used():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True, idle_timeout_seconds=60.0)
    manager.ensure_started("lazy")

    evicted = manager.sweep_idle_services()

    assert evicted == []


def test_sweep_idle_services_skips_a_service_with_no_idle_timeout_configured():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True)
    manager.ensure_started("lazy")
    module.last_used_at_value = datetime.now(UTC) - timedelta(seconds=999.0)

    evicted = manager.sweep_idle_services()

    assert evicted == []


def test_sweep_idle_services_skips_a_legacy_module_entirely():
    manager = RuntimeManager()
    module = _StubLegacyModule()
    manager.register("legacy", module, ServiceTier.ALWAYS_LOADED, lazy=False)

    evicted = manager.sweep_idle_services()

    assert evicted == []


def test_evict_least_recently_used_picks_the_oldest_first():
    manager = RuntimeManager()
    older = _StubLazyModule()
    newer = _StubLazyModule()
    manager.register("older", older, ServiceTier.WARM, lazy=True)
    manager.register("newer", newer, ServiceTier.WARM, lazy=True)
    manager.ensure_started("older")
    manager.ensure_started("newer")
    older.last_used_at_value = datetime.now(UTC) - timedelta(seconds=500.0)
    newer.last_used_at_value = datetime.now(UTC) - timedelta(seconds=5.0)

    evicted = manager.evict_least_recently_used(1)

    assert evicted == ["older"]
    assert manager.state_of("older") is ServiceState.UNLOADED
    assert manager.state_of("newer") is ServiceState.READY


def test_evict_least_recently_used_prefers_a_never_used_service():
    manager = RuntimeManager()
    never_used = _StubLazyModule()
    used_recently = _StubLazyModule()
    manager.register("never_used", never_used, ServiceTier.WARM, lazy=True)
    manager.register("used_recently", used_recently, ServiceTier.WARM, lazy=True)
    manager.ensure_started("never_used")
    manager.ensure_started("used_recently")
    used_recently.last_used_at_value = datetime.now(UTC) - timedelta(seconds=5.0)

    evicted = manager.evict_least_recently_used(1)

    assert evicted == ["never_used"]


def test_evict_least_recently_used_never_evicts_an_active_service():
    manager = RuntimeManager()
    module = _StubLazyModule()
    manager.register("lazy", module, ServiceTier.WARM, lazy=True)
    manager.ensure_started("lazy")
    module._state = ServiceState.ACTIVE

    evicted = manager.evict_least_recently_used(5)

    assert evicted == []


def test_evict_least_recently_used_never_evicts_a_legacy_module():
    manager = RuntimeManager()
    module = _StubLegacyModule()
    manager.register("legacy", module, ServiceTier.ALWAYS_LOADED, lazy=False)

    evicted = manager.evict_least_recently_used(5)

    assert evicted == []


def test_evict_least_recently_used_respects_max_count():
    manager = RuntimeManager()
    for name in ("a", "b", "c"):
        module = _StubLazyModule()
        manager.register(name, module, ServiceTier.WARM, lazy=True)
        manager.ensure_started(name)

    evicted = manager.evict_least_recently_used(2)

    assert len(evicted) == 2
