"""Unit tests for presentation.widgets.particle_field_widget."""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from presentation.animation_manager import DegradationLevel
from presentation.widgets.particle_field_widget import ParticleFieldWidget, target_count


def test_target_count_always_includes_the_ambient_minimum():
    assert target_count(particle_density=0.0, ambient_minimum=4, max_particles=18) == 4


def test_target_count_never_exceeds_max_particles():
    assert target_count(particle_density=1.0, ambient_minimum=4, max_particles=18) == 18


def test_target_count_scales_between_ambient_minimum_and_max():
    low = target_count(particle_density=0.1, ambient_minimum=4, max_particles=18)
    high = target_count(particle_density=0.9, ambient_minimum=4, max_particles=18)
    assert 4 <= low < high <= 18


def test_target_count_clamps_out_of_range_density():
    assert target_count(particle_density=-1.0, ambient_minimum=4, max_particles=18) == 4
    assert target_count(particle_density=5.0, ambient_minimum=4, max_particles=18) == 18


def test_widget_paints_without_raising(qtbot):
    widget = ParticleFieldWidget(max_particles=10)
    qtbot.addWidget(widget)
    widget.resize(80, 80)
    widget.set_ambient_minimum(3)
    widget.set_target(QColor("#0A84FF"), particle_density=0.2, animation_speed=1.0)
    widget.set_orbit_geometry(QPointF(40, 40), core_half_size=30.0)

    pixmap = widget.grab()  # forces a real paintEvent() call

    assert not pixmap.isNull()


def test_paint_event_is_a_safe_noop_before_orbit_geometry_is_set(qtbot):
    """A widget added via _HologramStage.add_orbit_layer() always gets
    set_orbit_geometry() at construction, but a bare widget (as in most
    of this file's own tests) never calling it must still paint safely —
    _orbit_half_size defaults to 0.0, which paintEvent treats as "nothing
    to draw yet", not an error."""
    widget = ParticleFieldWidget(max_particles=10)
    qtbot.addWidget(widget)
    widget.resize(80, 80)
    widget.set_ambient_minimum(3)
    widget.set_target(QColor("#0A84FF"), particle_density=0.2, animation_speed=1.0)

    pixmap = widget.grab()

    assert not pixmap.isNull()


def test_widget_paints_without_raising_when_no_particles_visible(qtbot):
    widget = ParticleFieldWidget(max_particles=10)
    qtbot.addWidget(widget)
    widget.resize(80, 80)
    widget.set_orbit_geometry(QPointF(40, 40), core_half_size=30.0)
    # set_ambient_minimum()/set_target() never called — _visible_count stays 0.

    pixmap = widget.grab()

    assert not pixmap.isNull()


def test_set_ambient_minimum_is_bounded_by_the_particle_pool_size():
    widget = ParticleFieldWidget(max_particles=5)
    widget.set_ambient_minimum(100)

    widget.set_target(QColor("#0A84FF"), particle_density=0.0, animation_speed=1.0)

    assert widget._visible_count == 5


def test_on_tick_advances_only_the_currently_visible_particles(qtbot):
    widget = ParticleFieldWidget(max_particles=10)
    qtbot.addWidget(widget)
    widget.set_ambient_minimum(2)
    widget.set_target(QColor("#0A84FF"), particle_density=0.0, animation_speed=1.0)
    hidden_angle_before = widget._particles[5].angle

    widget._on_tick()

    assert widget._particles[5].angle == hidden_angle_before


def test_on_tick_survives_a_raising_tick(qtbot, caplog):
    widget = ParticleFieldWidget(max_particles=4)
    qtbot.addWidget(widget)
    widget.set_ambient_minimum(4)
    widget.set_target(QColor("#0A84FF"), particle_density=1.0, animation_speed="not-a-number")

    with caplog.at_level("ERROR"):
        widget._on_tick()  # must not raise

    assert any("_on_tick" in r.message for r in caplog.records)


def test_on_tick_logs_a_repeated_failure_only_once(qtbot, caplog):
    widget = ParticleFieldWidget(max_particles=4)
    qtbot.addWidget(widget)
    widget.set_ambient_minimum(4)
    widget.set_target(QColor("#0A84FF"), particle_density=1.0, animation_speed="not-a-number")

    with caplog.at_level("ERROR"):
        widget._on_tick()
        widget._on_tick()
        widget._on_tick()

    failures = [r for r in caplog.records if "_on_tick" in r.message]
    assert len(failures) == 1


def test_minimal_degradation_disables_particles_entirely():
    widget = ParticleFieldWidget(max_particles=10)
    widget.set_ambient_minimum(4)
    widget.set_resource_degradation(DegradationLevel.MINIMAL)

    widget.set_target(QColor("#0A84FF"), particle_density=1.0, animation_speed=1.0)

    assert widget._visible_count == 0


def test_reduced_degradation_caps_at_ambient_minimum():
    widget = ParticleFieldWidget(max_particles=18)
    widget.set_ambient_minimum(4)
    widget.set_resource_degradation(DegradationLevel.REDUCED)

    widget.set_target(QColor("#0A84FF"), particle_density=1.0, animation_speed=1.0)

    assert widget._visible_count == 4


def test_normal_degradation_is_a_no_op():
    widget = ParticleFieldWidget(max_particles=18)
    widget.set_ambient_minimum(4)
    widget.set_resource_degradation(DegradationLevel.NORMAL)

    widget.set_target(QColor("#0A84FF"), particle_density=1.0, animation_speed=1.0)

    assert widget._visible_count == 18


def test_degradation_takes_effect_on_the_next_set_target_call_not_retroactively():
    widget = ParticleFieldWidget(max_particles=18)
    widget.set_ambient_minimum(4)
    widget.set_target(QColor("#0A84FF"), particle_density=1.0, animation_speed=1.0)
    assert widget._visible_count == 18

    widget.set_resource_degradation(DegradationLevel.MINIMAL)

    assert widget._visible_count == 18  # unchanged until the next set_target()


def test_zero_max_particles_is_safe(qtbot):
    widget = ParticleFieldWidget(max_particles=0)
    qtbot.addWidget(widget)
    widget.resize(40, 40)
    widget.set_ambient_minimum(0)
    widget.set_target(QColor("#0A84FF"), particle_density=1.0, animation_speed=1.0)

    widget._on_tick()
    pixmap = widget.grab()

    assert not pixmap.isNull()
