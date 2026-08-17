"""Unit tests for presentation.jarvis_renderer and its two widgets
(Sprint 5.7).

pytest-qt's own qtbot fixture provides the QApplication every widget
construction in these tests needs — the same established precedent
tests/unit/ui/test_status_panel.py/test_main_window.py already use.
Verifies internal widget state/target values, never rendered pixels
(this sprint's own Implementation Tasks) — real visual confirmation is
named explicitly as Sprint 5.16's own manual-verification job, not
claimed provable by any unit test here.
"""

import glob
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from PySide6.QtGui import QColor

from config.schema import PresentationConfig, UIConfig
from core.resource_monitor import ResourceSnapshot
from presentation.adaptive_workspace import WorkspaceProfile
from presentation.animation_manager import DegradationLevel
from presentation.jarvis_renderer import JarvisRenderer, _derive_ring_state
from presentation.presentation_state import PresentationState
from presentation.widgets.holographic_sphere_widget import HolographicSphereWidget
from presentation.widgets.segmented_ring_widget import (
    _LIT_FRACTION,
    RingState,
    SegmentedRingWidget,
)


def _fake_core_manager(module_states=None, interval_ms=3000) -> MagicMock:
    """Mirrors tests/unit/ui/conftest.py's own mock_core_manager fixture
    shape — not reused directly since tests/unit/presentation/ is a
    sibling directory with no shared conftest.py of its own yet (one
    file's own need doesn't justify adding one, per this project's own
    "don't build speculatively" discipline)."""
    manager = MagicMock()
    manager.module_states.return_value = module_states if module_states is not None else {}
    manager.check_resources.return_value = ResourceSnapshot(
        cpu_percent=10.0,
        ram_percent=20.0,
        disk_percent=30.0,
        battery_percent=80.0,
        timestamp=datetime.now(UTC),
    )
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    return manager


def _sample_state(avatar_focus: str = "user", animation_speed: float = 1.0) -> PresentationState:
    return PresentationState(
        smile_intensity=0.0,
        eye_openness=0.6,
        voice_warmth=0.3,
        animation_speed=animation_speed,
        particle_density=0.0,
        lighting_color="#0A84FF",
        ui_accent="#22D3EE",
        gesture_probability=0.1,
        avatar_focus=avatar_focus,
        persona_name="jarvis",
        computed_at=datetime.now(UTC),
    )


@pytest.fixture
def config() -> PresentationConfig:
    return PresentationConfig(jarvis_animation_tick_ms=20)


@pytest.fixture
def core_manager() -> MagicMock:
    return _fake_core_manager()


@pytest.fixture
def renderer(qtbot, config, core_manager) -> JarvisRenderer:
    jr = JarvisRenderer(config, core_manager)
    qtbot.addWidget(jr.widget())
    return jr


# --- mount()/unmount() lifecycle (Acceptance Criteria: idempotent) -----------


def test_widget_returns_the_top_level_container_before_mount(renderer):
    assert renderer.widget() is not None


def test_widget_is_the_same_instance_across_calls(renderer):
    assert renderer.widget() is renderer.widget()


def test_mount_starts_the_animation_timer(renderer):
    renderer.mount()
    assert renderer._timer.isActive()


def test_double_mount_is_idempotent(renderer):
    renderer.mount()
    first_timer = renderer._timer
    renderer.mount()

    assert renderer._timer is first_timer
    assert renderer._timer.isActive()


def test_unmount_stops_the_animation_timer(renderer):
    renderer.mount()
    renderer.unmount()
    assert not renderer._timer.isActive()


def test_double_unmount_is_safe(renderer):
    renderer.mount()
    renderer.unmount()
    renderer.unmount()  # must not raise
    assert not renderer._timer.isActive()


def test_unmount_before_mount_is_safe(renderer):
    renderer.unmount()  # never mounted — must not raise
    assert renderer._mounted is False


def test_remount_after_unmount_restarts_the_timer(renderer):
    renderer.mount()
    renderer.unmount()
    renderer.mount()
    assert renderer._timer.isActive()


def test_remount_reuses_the_existing_widget_hierarchy(renderer):
    """unmount() does not destroy the widget hierarchy — cheaply
    re-mountable (this sprint's own Expected Interfaces)."""
    original_container = renderer.widget()
    renderer.mount()
    renderer.unmount()
    renderer.mount()
    assert renderer.widget() is original_container


# --- render_state() never triggers a synchronous repaint (Acceptance Criteria) --


def test_render_state_sets_sphere_and_ring_targets(renderer):
    renderer.mount()
    state = _sample_state(avatar_focus="idle", animation_speed=1.5)

    renderer.render_state(state)

    assert renderer._sphere._target_color.name() == "#0a84ff"
    assert renderer._sphere._animation_speed == 1.5
    assert renderer._ring._ring_state is RingState.IDLE
    assert renderer._ring._animation_speed == 1.5


def test_render_state_does_not_call_update_on_either_widget(renderer):
    renderer.mount()
    renderer._sphere.update = MagicMock()
    renderer._ring.update = MagicMock()

    renderer.render_state(_sample_state())

    renderer._sphere.update.assert_not_called()
    renderer._ring.update.assert_not_called()


def test_render_state_before_mount_does_not_raise(renderer):
    """Building the hierarchy via widget() alone (no mount()) must still
    let render_state() work safely, and calling it before either is a
    logged no-op, never a crash."""
    renderer.render_state(_sample_state())  # widget() already built it via the fixture


def test_render_state_before_any_widget_build_is_a_safe_noop(qtbot, config, core_manager):
    bare_renderer = JarvisRenderer(config, core_manager)
    bare_renderer.render_state(_sample_state())  # must not raise, no widget() call yet


# --- animation timer genuinely ticks (bounded real-timer wait) ---------------


def test_animation_timer_genuinely_advances_the_sphere_and_ring_phase(qtbot, renderer):
    renderer.mount()
    renderer.render_state(_sample_state())
    phase_before = renderer._sphere._phase
    rotation_before = renderer._ring._rotation_phase

    qtbot.wait(120)  # several ticks at the fixture's 20ms interval

    assert renderer._sphere._phase != phase_before
    assert renderer._ring._rotation_phase != rotation_before


def test_animation_timer_does_not_advance_after_unmount(qtbot, renderer):
    renderer.mount()
    renderer.unmount()
    phase_before = renderer._sphere._phase

    qtbot.wait(120)

    assert renderer._sphere._phase == phase_before


# --- _derive_ring_state() mapping (Testing Checklist) -------------------------


def test_derive_ring_state_idle_avatar_focus_maps_to_idle():
    assert _derive_ring_state(_sample_state(avatar_focus="idle")) is RingState.IDLE


@pytest.mark.parametrize("avatar_focus", ["user", "task"])
def test_derive_ring_state_everything_else_maps_to_processing(avatar_focus):
    """This sprint's own honestly-narrow mapping (Architecture Notes):
    PresentationState alone cannot distinguish Listening/Thinking/
    Speaking, so every non-idle avatar_focus collapses to PROCESSING
    today. Real per-phase states are Sprint 5.14's own job — documented
    here as today's actual behavior, not a TODO comment alone."""
    assert _derive_ring_state(_sample_state(avatar_focus=avatar_focus)) is RingState.PROCESSING


# --- trigger_gesture() (Sprint 5.9) -------------------------------------------


def test_trigger_gesture_triggers_a_pulse_on_the_ring(renderer):
    renderer.mount()

    renderer.trigger_gesture("head_tilt")

    assert renderer._ring._pulse_ticks_remaining == renderer._config.jarvis_gesture_pulse_ticks


def test_trigger_gesture_applies_the_same_pulse_regardless_of_gesture_id(renderer):
    """This sprint's own deliberately narrow, honestly-disclosed
    interpretation (module docstring): Jarvis applies one uniform accent
    pulse no matter which gesture_id GestureEngine chose upstream."""
    renderer.mount()
    renderer.trigger_gesture("some_gesture")
    first_pulse = renderer._ring._pulse_ticks_remaining

    renderer._ring._pulse_ticks_remaining = 0
    renderer.trigger_gesture("a_totally_different_gesture")
    second_pulse = renderer._ring._pulse_ticks_remaining

    assert first_pulse == second_pulse == renderer._config.jarvis_gesture_pulse_ticks


def test_trigger_gesture_before_any_widget_build_is_a_safe_noop(qtbot, config, core_manager):
    bare_renderer = JarvisRenderer(config, core_manager)
    bare_renderer.trigger_gesture("head_tilt")  # must not raise, no widget() call yet


def test_trigger_gesture_pulse_decays_over_real_ticks(qtbot, renderer):
    renderer.mount()
    renderer.trigger_gesture("head_tilt")
    initial_remaining = renderer._ring._pulse_ticks_remaining

    qtbot.wait(120)  # several ticks at the fixture's 20ms interval

    assert renderer._ring._pulse_ticks_remaining < initial_remaining


# --- apply_workspace_profile() (Sprint 5.12) -----------------------------------


def test_apply_workspace_profile_always_includes_the_system_status_panel(renderer):
    renderer.apply_workspace_profile(WorkspaceProfile.CODING)

    layout = renderer._panel_container.layout()
    assert layout.count() == 2  # system status + one profile-specific placeholder


def test_apply_workspace_profile_general_has_only_the_system_status_panel(renderer):
    renderer.apply_workspace_profile(WorkspaceProfile.GENERAL)

    layout = renderer._panel_container.layout()
    assert layout.count() == 1  # GENERAL's own safe-failure role: no extra placeholder


@pytest.mark.parametrize(
    "profile",
    [
        WorkspaceProfile.CODING,
        WorkspaceProfile.RESEARCH,
        WorkspaceProfile.STUDY,
        WorkspaceProfile.PROJECTS,
    ],
)
def test_apply_workspace_profile_each_non_general_profile_has_two_panels(renderer, profile):
    renderer.apply_workspace_profile(profile)

    layout = renderer._panel_container.layout()
    assert layout.count() == 2


def test_apply_workspace_profile_sets_current_workspace_profile(renderer):
    renderer.apply_workspace_profile(WorkspaceProfile.RESEARCH)
    assert renderer._current_workspace_profile is WorkspaceProfile.RESEARCH


def test_apply_workspace_profile_switching_profiles_replaces_the_previous_panels(renderer):
    renderer.apply_workspace_profile(WorkspaceProfile.CODING)
    renderer.apply_workspace_profile(WorkspaceProfile.STUDY)

    layout = renderer._panel_container.layout()
    assert layout.count() == 2  # not accumulated across the two calls
    assert renderer._current_workspace_profile is WorkspaceProfile.STUDY


def test_apply_workspace_profile_builds_the_widget_hierarchy_if_not_already_built(
    qtbot, config, core_manager
):
    bare_renderer = JarvisRenderer(config, core_manager)
    bare_renderer.apply_workspace_profile(WorkspaceProfile.GENERAL)  # no widget()/mount() first
    assert bare_renderer._panel_container is not None


def test_system_status_panel_reflects_the_real_core_manager_data(renderer, core_manager):
    core_manager.module_states.return_value = {"voice": "running", "memory": "running"}

    renderer.apply_workspace_profile(WorkspaceProfile.GENERAL)

    status_panel = renderer._panel_container.layout().itemAt(0).widget()
    assert "2/2 modules running" in status_panel._label.text()


def test_system_status_panel_survives_a_core_manager_failure(renderer, core_manager):
    core_manager.module_states.side_effect = RuntimeError("boom")

    renderer.apply_workspace_profile(WorkspaceProfile.GENERAL)  # must not raise


# --- no QML anywhere under presentation/ (mechanical check) ------------------


def test_no_qml_files_under_presentation():
    presentation_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "presentation")
    qml_files = glob.glob(os.path.join(presentation_dir, "**", "*.qml"), recursive=True)
    assert qml_files == []


def test_no_qquick_import_under_presentation():
    presentation_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "presentation")
    for path in glob.glob(os.path.join(presentation_dir, "**", "*.py"), recursive=True):
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        assert "QQuick" not in content, f"{path} references QQuick*, which is not permitted"


# --- HolographicSphereWidget / SegmentedRingWidget, in isolation -------------


def test_sphere_widget_paints_without_raising(qtbot):
    widget = HolographicSphereWidget()
    qtbot.addWidget(widget)
    widget.resize(64, 64)
    widget.set_target(QColor("#0A84FF"), 1.0)

    pixmap = widget.grab()  # forces a real paintEvent() call

    assert not pixmap.isNull()


def test_sphere_widget_phase_wraps_within_two_pi(qtbot):
    widget = HolographicSphereWidget()
    qtbot.addWidget(widget)
    widget._animation_speed = 5.0

    for _ in range(1000):
        widget._on_tick()

    assert 0.0 <= widget._phase < 6.283185307179586  # 2*pi


# --- HolographicSphereWidget._on_tick() exception guarding (Sprint 5.15c) ----
#
# A corrupted _animation_speed (a str, not a float) forces a real
# TypeError from _on_tick()'s own arithmetic — portable across PySide6
# versions, unlike monkeypatching Qt's own C++-backed update() method.


def test_sphere_widget_on_tick_survives_a_raising_tick(qtbot, caplog):
    widget = HolographicSphereWidget()
    qtbot.addWidget(widget)
    widget._animation_speed = "not-a-number"
    last_good_phase = widget._phase

    with caplog.at_level("ERROR"):
        widget._on_tick()  # must not raise

    assert any("_on_tick" in r.message for r in caplog.records)
    assert widget._phase == last_good_phase  # last-good frame retained


def test_sphere_widget_on_tick_logs_a_repeated_failure_only_once(qtbot, caplog):
    widget = HolographicSphereWidget()
    qtbot.addWidget(widget)
    widget._animation_speed = "not-a-number"

    with caplog.at_level("ERROR"):
        widget._on_tick()
        widget._on_tick()
        widget._on_tick()

    failures = [r for r in caplog.records if "_on_tick" in r.message]
    assert len(failures) == 1


def test_sphere_widget_on_tick_recovers_after_a_transient_failure(qtbot, caplog):
    widget = HolographicSphereWidget()
    qtbot.addWidget(widget)

    with caplog.at_level("ERROR"):
        widget._animation_speed = "not-a-number"
        widget._on_tick()  # fails, logs once
        widget._animation_speed = 1.0
        widget._on_tick()  # recovers
        widget._animation_speed = "not-a-number"
        widget._on_tick()  # fails again — logs again, since the flag reset on recovery

    failures = [r for r in caplog.records if "_on_tick" in r.message]
    assert len(failures) == 2


def test_ring_widget_paints_without_raising(qtbot):
    widget = SegmentedRingWidget(segment_count=12)
    qtbot.addWidget(widget)
    widget.resize(64, 64)
    widget.set_ring_state(RingState.PROCESSING, 1.0)

    pixmap = widget.grab()  # forces a real paintEvent() call

    assert not pixmap.isNull()


def test_ring_widget_set_ring_state_updates_fields(qtbot):
    widget = SegmentedRingWidget(segment_count=8)
    qtbot.addWidget(widget)

    widget.set_ring_state(RingState.SPEAKING, 2.0)

    assert widget._ring_state is RingState.SPEAKING
    assert widget._animation_speed == 2.0


def test_ring_widget_processing_state_lights_more_segments_than_idle(qtbot):
    assert _LIT_FRACTION[RingState.PROCESSING] > _LIT_FRACTION[RingState.IDLE]


def test_ring_widget_zero_size_paint_does_not_raise(qtbot):
    """A degenerate 0x0 widget (radius <= 0) must not crash paintEvent()
    — a real edge case before any layout has assigned real geometry."""
    widget = SegmentedRingWidget(segment_count=12)
    qtbot.addWidget(widget)
    widget.resize(0, 0)

    widget.grab()  # must not raise


# --- SegmentedRingWidget.trigger_pulse() (Sprint 5.9) -------------------------


def test_trigger_pulse_sets_the_remaining_tick_count(qtbot):
    widget = SegmentedRingWidget(segment_count=12)
    qtbot.addWidget(widget)

    widget.trigger_pulse(5)

    assert widget._pulse_ticks_remaining == 5


def test_trigger_pulse_negative_duration_is_a_safe_noop(qtbot):
    widget = SegmentedRingWidget(segment_count=12)
    qtbot.addWidget(widget)

    widget.trigger_pulse(-3)

    assert widget._pulse_ticks_remaining == 0


def test_on_tick_decrements_the_pulse_and_stops_at_zero(qtbot):
    widget = SegmentedRingWidget(segment_count=12)
    qtbot.addWidget(widget)
    widget.trigger_pulse(2)

    widget._on_tick()
    assert widget._pulse_ticks_remaining == 1
    widget._on_tick()
    assert widget._pulse_ticks_remaining == 0
    widget._on_tick()  # must not go negative
    assert widget._pulse_ticks_remaining == 0


def test_ring_widget_paints_without_raising_while_pulsing(qtbot):
    widget = SegmentedRingWidget(segment_count=12)
    qtbot.addWidget(widget)
    widget.resize(64, 64)
    widget.trigger_pulse(5)

    pixmap = widget.grab()  # forces a real paintEvent() call while pulsing

    assert not pixmap.isNull()


# --- SegmentedRingWidget._on_tick() exception guarding (Sprint 5.15c) --------
#
# A corrupted _animation_speed (a str, not a float) forces a real
# TypeError from _on_tick()'s own arithmetic — the same portable
# technique HolographicSphereWidget's own tests above use.


def test_ring_widget_on_tick_survives_a_raising_tick(qtbot, caplog):
    widget = SegmentedRingWidget(segment_count=12)
    qtbot.addWidget(widget)
    widget._animation_speed = "not-a-number"
    last_good_phase = widget._rotation_phase

    with caplog.at_level("ERROR"):
        widget._on_tick()  # must not raise

    assert any("_on_tick" in r.message for r in caplog.records)
    assert widget._rotation_phase == last_good_phase  # last-good frame retained


def test_ring_widget_on_tick_logs_a_repeated_failure_only_once(qtbot, caplog):
    widget = SegmentedRingWidget(segment_count=12)
    qtbot.addWidget(widget)
    widget._animation_speed = "not-a-number"

    with caplog.at_level("ERROR"):
        widget._on_tick()
        widget._on_tick()
        widget._on_tick()

    failures = [r for r in caplog.records if "_on_tick" in r.message]
    assert len(failures) == 1


def test_ring_widget_on_tick_recovers_after_a_transient_failure(qtbot, caplog):
    widget = SegmentedRingWidget(segment_count=12)
    qtbot.addWidget(widget)

    with caplog.at_level("ERROR"):
        widget._animation_speed = "not-a-number"
        widget._on_tick()  # fails, logs once
        widget._animation_speed = 1.0
        widget._on_tick()  # recovers
        widget._animation_speed = "not-a-number"
        widget._on_tick()  # fails again — logs again, since the flag reset on recovery

    failures = [r for r in caplog.records if "_on_tick" in r.message]
    assert len(failures) == 2


# --- JARVIS Holographic HUD reskin, Phase 3: floor/particles/status label ----


def test_render_state_sets_the_floor_color(renderer):
    renderer.mount()

    renderer.render_state(_sample_state())

    assert renderer._floor._color.name() == "#0a84ff"


def test_render_state_sets_the_particle_field_target(renderer):
    renderer.mount()
    state = _sample_state(animation_speed=1.5)
    state.particle_density = 0.03

    renderer.render_state(state)

    assert renderer._particles._animation_speed == 1.5


def test_render_state_updates_the_status_label_for_idle(renderer):
    renderer.mount()

    renderer.render_state(_sample_state(avatar_focus="idle"))

    assert renderer._status_label.text() == "Ready."


def test_render_state_updates_the_status_label_for_processing(renderer):
    renderer.mount()

    renderer.render_state(_sample_state(avatar_focus="user"))

    assert renderer._status_label.text() == "Working on that..."


def test_apply_turn_phase_updates_the_status_label(renderer):
    renderer.mount()

    renderer.apply_turn_phase(RingState.LISTENING)

    assert renderer._status_label.text() == "Listening..."


def test_status_label_defaults_to_ready_before_any_render_state_call(renderer):
    assert renderer._status_label.text() == "Ready."


def test_on_tick_advances_the_particle_field_too(qtbot, renderer):
    renderer.mount()
    state = _sample_state()
    state.particle_density = 1.0
    renderer.render_state(state)
    angle_before = renderer._particles._particles[0].angle

    qtbot.wait(120)  # several ticks at the fixture's 20ms interval

    assert renderer._particles._particles[0].angle != angle_before


def test_hologram_stage_layers_floor_sphere_and_ring_around_a_shared_core(renderer):
    """The floor is a background layer (full stage rect); sphere/ring
    share a smaller, centered core rect (not the full stage — see
    _HologramStage's own docstring for why); the particle field is an
    orbit layer (full stage rect, so an orbit beyond the ring's edge is
    never clipped) but anchored on the core's own center. resizeEvent()
    only fires synchronously once a widget has a real window handle
    (i.e. after show()), the same quirk this workstream's own
    ui/jarvis/hud_shell.py test already found — show() first, matching
    how MainWindow actually uses this hierarchy."""
    stage = renderer._stage
    assert stage._background_layers == [renderer._floor]
    assert stage._core_layers == [renderer._sphere, renderer._ring]
    assert stage._orbit_layers == [renderer._particles]
    renderer.widget().show()

    stage.resize(300, 300)
    core_rect = stage.core_rect()

    assert renderer._floor.geometry() == stage.rect()
    assert renderer._particles.geometry() == stage.rect()
    assert renderer._sphere.geometry() == core_rect
    assert renderer._ring.geometry() == core_rect
    # The core rect is smaller than the full stage (real margin exists
    # for the floor beneath it and the particles orbiting beyond it).
    assert core_rect.width() < stage.rect().width()


# --- JARVIS Holographic HUD reskin, Phase 7: apply_resource_degradation() ----


def test_apply_resource_degradation_minimal_disables_particles(renderer):
    renderer.mount()

    renderer.apply_resource_degradation(DegradationLevel.MINIMAL)
    renderer.render_state(_sample_state())

    assert renderer._particles._visible_count == 0


def test_apply_resource_degradation_minimal_widens_the_tick_interval(renderer, config):
    renderer.mount()

    renderer.apply_resource_degradation(DegradationLevel.MINIMAL)

    assert renderer._timer.interval() == config.jarvis_animation_tick_ms * 4


def test_apply_resource_degradation_reduced_widens_the_tick_interval_less(renderer, config):
    renderer.mount()

    renderer.apply_resource_degradation(DegradationLevel.REDUCED)

    assert renderer._timer.interval() == config.jarvis_animation_tick_ms * 2


def test_apply_resource_degradation_normal_restores_the_original_interval(renderer, config):
    renderer.mount()
    renderer.apply_resource_degradation(DegradationLevel.MINIMAL)

    renderer.apply_resource_degradation(DegradationLevel.NORMAL)

    assert renderer._timer.interval() == config.jarvis_animation_tick_ms


def test_apply_resource_degradation_before_any_widget_build_is_a_safe_noop(
    qtbot, config, core_manager
):
    bare_renderer = JarvisRenderer(config, core_manager)
    bare_renderer.apply_resource_degradation(DegradationLevel.MINIMAL)  # must not raise
