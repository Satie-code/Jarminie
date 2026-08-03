"""Shared test fixtures for ui/ unit tests.

Plain helper functions can't be imported across files here (tests/ has no
__init__.py, by convention since Sprint 1.1 — see docs/sprint_book/
sprint_1_1.md — so relative imports like `from .conftest import x` fail).
Fixtures are pytest's own auto-discovery mechanism and work regardless,
so shared helpers are exposed as fixtures instead.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from config.schema import AppConfig, UIConfig
from core.resource_monitor import ResourceSnapshot


@pytest.fixture
def resource_snapshot_factory():
    """Factory fixture: build a ResourceSnapshot with sensible defaults,
    overridable per test via keyword arguments."""

    def _make(**overrides):
        defaults = dict(
            cpu_percent=10.0,
            ram_percent=20.0,
            disk_percent=30.0,
            battery_percent=80.0,
            timestamp=datetime.now(UTC),
        )
        defaults.update(overrides)
        return ResourceSnapshot(**defaults)

    return _make


@pytest.fixture
def mock_core_manager(resource_snapshot_factory):
    """A CoreManager double with sane defaults for widgets that call
    module_states() / check_resources() / ui_config() during construction
    (e.g. StatusPanel, embedded inside MainWindow), plus config() /
    config_loader() for Settings Window (Sprint 1.8) — config() must
    return a real AppConfig, not a bare MagicMock, since SettingsWindow's
    load_from_config() iterates/formats its fields."""
    manager = MagicMock()
    manager.module_states.return_value = {}
    manager.check_resources.return_value = resource_snapshot_factory()
    manager.ui_config.return_value = UIConfig()
    manager.config.return_value = AppConfig()
    manager.config_loader.return_value = MagicMock()
    return manager


@pytest.fixture
def mock_presentation_handles():
    """Sprint 5.14: MainWindow's four new Level 5 constructor parameters
    (presentation_controller/jarvis_renderer/minie_renderer/
    transition_engine) — plain MagicMocks are enough for every test in
    this directory, none of which exercises real presentation behavior
    (that's tests/unit/presentation/'s own job). mounted_persona_name
    defaults to a MagicMock attribute (neither the literal string
    "jarvis" nor "minie"), so PresentationHostWidget's own refresh()
    harmlessly no-ops during MainWindow construction rather than trying
    to call jarvis_renderer.widget()/minie_renderer.status_widget() and
    needing a real QWidget back from a mock."""
    return {
        "presentation_controller": MagicMock(),
        "jarvis_renderer": MagicMock(),
        "minie_renderer": MagicMock(),
        "transition_engine": MagicMock(),
    }
