"""Unit tests for core.module_registry."""

import pytest

from core.module_registry import ModuleRegistry, ModuleState


class _StubModule:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def health_check(self) -> bool:
        return True


def test_register_and_get():
    registry = ModuleRegistry()
    module = _StubModule()
    registry.register("voice", module)
    assert registry.get("voice") is module


def test_register_duplicate_raises():
    registry = ModuleRegistry()
    registry.register("voice", _StubModule())
    with pytest.raises(ValueError, match="already registered"):
        registry.register("voice", _StubModule())


def test_new_module_starts_in_registered_state():
    registry = ModuleRegistry()
    registry.register("voice", _StubModule())
    assert registry.state_of("voice") == ModuleState.REGISTERED


def test_set_state_updates():
    registry = ModuleRegistry()
    registry.register("voice", _StubModule())
    registry.set_state("voice", ModuleState.RUNNING)
    assert registry.state_of("voice") == ModuleState.RUNNING


def test_names_preserves_registration_order():
    registry = ModuleRegistry()
    registry.register("first", _StubModule())
    registry.register("second", _StubModule())
    registry.register("third", _StubModule())
    assert registry.names() == ["first", "second", "third"]


def test_states_returns_all_as_strings():
    registry = ModuleRegistry()
    registry.register("voice", _StubModule())
    registry.set_state("voice", ModuleState.FAILED)
    assert registry.states() == {"voice": "failed"}
