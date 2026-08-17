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

from config.schema import AppConfig, PresentationConfig, ResourceThresholds, UIConfig
from core.resource_monitor import ResourceSnapshot
from emotion.state_manager import EmotionalState


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
    load_from_config() iterates/formats its fields.

    JARVIS Holographic HUD reskin, Phase 7: resource_thresholds() backs
    AnimationManager's own ResourceMonitor — a real ResourceThresholds,
    not a bare MagicMock, so classifying a real ResourceSnapshot against
    it doesn't compare a float against a MagicMock attribute (which
    on_resources_updated()'s own Fail Gracefully try/except would
    swallow silently rather than crash, but a spuriously-logged
    exception on every construction-only test is worth avoiding).

    Phase 9: presentation_config() backs HudShell's own one-time
    jarvis_ui_accent read — a real PresentationConfig, not a bare
    MagicMock, so QColor(accent) never receives a MagicMock attribute
    (a real crash risk in NavigationRail/HudFrame's own paintEvent(),
    neither of which wraps color usage in a try/except the way
    on_resources_updated() does)."""
    manager = MagicMock()
    manager.module_states.return_value = {}
    manager.check_resources.return_value = resource_snapshot_factory()
    manager.ui_config.return_value = UIConfig()
    manager.resource_thresholds.return_value = ResourceThresholds()
    manager.presentation_config.return_value = PresentationConfig()
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
    needing a real QWidget back from a mock.

    JARVIS Holographic HUD reskin, Phase 4: calendar_store/action_registry
    are MainWindow's two newest constructor parameters — real HudShell
    construction now builds RemindersPanel/QuickCommandsPanel from them,
    so calendar_store.list_due_within() must return a real empty list
    (not a bare MagicMock — RemindersPanel.refresh() only guards the
    list_due_within() call itself against a raising mock, not against a
    non-list return value from an unconfigured one, matching
    CalendarStore's own real "degrades to [] on failure" contract rather
    than a crash-shaped default).

    Phase 6: voice_session_manager/pipeline are MainWindow's two newest
    constructor parameters (TopBar's own VoiceVisualizer and CommandBar,
    respectively) — plain MagicMocks are safe here: VoiceVisualizer's
    _on_tick() falls back to VoiceVisualState.IDLE for any
    current_session_state() return value dict.get() doesn't recognize
    (a bare MagicMock included, not just a real SessionState), and
    CommandBar never calls pipeline.submit_text() until a user actually
    submits input, which no construction-only test does.

    Minie Persona UI workstream: three more constructor parameters
    (avatar_renderer/emotional_state_manager/weather_service) — MainWindow
    now also builds a real MinieShell. presentation_controller.
    last_state_for() returns None (its own real, documented "nothing
    computed yet" default — see PresentationController's own docstring),
    emotional_state_manager.current_state() returns a real EmotionalState
    (so MinieUiStateAdapter's derive_display_emotions() call does real
    arithmetic against real floats rather than MagicMock attributes),
    and avatar_renderer.is_connected() returns a real False — the same
    "real value, not a bare MagicMock, wherever a widget does real work
    with the result" discipline this fixture already applies to
    calendar_store above."""
    calendar_store = MagicMock()
    calendar_store.list_due_within.return_value = []
    presentation_controller = MagicMock()
    presentation_controller.last_state_for.return_value = None
    emotional_state_manager = MagicMock()
    emotional_state_manager.current_state.return_value = EmotionalState()
    avatar_renderer = MagicMock()
    avatar_renderer.is_connected.return_value = False
    weather_service = MagicMock()
    weather_service.current.return_value = None
    return {
        "presentation_controller": presentation_controller,
        "jarvis_renderer": MagicMock(),
        "minie_renderer": MagicMock(),
        "transition_engine": MagicMock(),
        "calendar_store": calendar_store,
        "action_registry": MagicMock(),
        "voice_session_manager": MagicMock(),
        "pipeline": MagicMock(),
        "avatar_renderer": avatar_renderer,
        "emotional_state_manager": emotional_state_manager,
        "weather_service": weather_service,
    }
