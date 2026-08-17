"""Unit tests for presentation.animation_manager."""

from datetime import UTC, datetime

from config.schema import ResourceThresholds
from core.resource_monitor import ResourceSnapshot
from presentation.animation_manager import AnimationManager, DegradationLevel


def _thresholds() -> ResourceThresholds:
    return ResourceThresholds(
        cpu_warning_percent=70.0,
        cpu_critical_percent=90.0,
        ram_warning_percent=75.0,
        ram_critical_percent=90.0,
        disk_warning_percent=85.0,
        disk_critical_percent=95.0,
        battery_warning_percent=20.0,
        battery_critical_percent=10.0,
    )


def _snapshot(**overrides) -> ResourceSnapshot:
    defaults = dict(
        cpu_percent=10.0, ram_percent=10.0, disk_percent=10.0, battery_percent=80.0,
        timestamp=datetime.now(UTC),
    )
    defaults.update(overrides)
    return ResourceSnapshot(**defaults)


def test_defaults_to_normal():
    manager = AnimationManager(_thresholds())

    assert manager.current_level() is DegradationLevel.NORMAL


def test_stays_normal_under_low_usage(qtbot):
    manager = AnimationManager(_thresholds())

    manager.on_resources_updated(_snapshot(cpu_percent=10.0))

    assert manager.current_level() is DegradationLevel.NORMAL


def test_becomes_reduced_at_warning_threshold(qtbot):
    manager = AnimationManager(_thresholds())

    manager.on_resources_updated(_snapshot(cpu_percent=75.0))

    assert manager.current_level() is DegradationLevel.REDUCED


def test_becomes_minimal_at_critical_threshold(qtbot):
    manager = AnimationManager(_thresholds())

    manager.on_resources_updated(_snapshot(cpu_percent=95.0))

    assert manager.current_level() is DegradationLevel.MINIMAL


def test_recovers_to_normal_once_pressure_clears(qtbot):
    manager = AnimationManager(_thresholds())
    manager.on_resources_updated(_snapshot(cpu_percent=95.0))

    manager.on_resources_updated(_snapshot(cpu_percent=10.0))

    assert manager.current_level() is DegradationLevel.NORMAL


def test_level_changed_only_emits_on_an_actual_change(qtbot):
    manager = AnimationManager(_thresholds())
    received = []
    manager.level_changed.connect(received.append)

    manager.on_resources_updated(_snapshot(cpu_percent=10.0))  # already NORMAL — no change
    manager.on_resources_updated(_snapshot(cpu_percent=75.0))  # NORMAL -> REDUCED
    manager.on_resources_updated(_snapshot(cpu_percent=76.0))  # still REDUCED — no change

    assert received == [DegradationLevel.REDUCED]


def test_ram_pressure_alone_also_triggers_reduced(qtbot):
    manager = AnimationManager(_thresholds())

    manager.on_resources_updated(_snapshot(cpu_percent=10.0, ram_percent=80.0))

    assert manager.current_level() is DegradationLevel.REDUCED


def test_survives_a_classification_failure(qtbot):
    manager = AnimationManager(_thresholds())

    manager.on_resources_updated(object())  # not a real ResourceSnapshot — must not raise

    assert manager.current_level() is DegradationLevel.NORMAL


def test_keeps_last_known_good_level_after_a_later_classification_failure(qtbot):
    manager = AnimationManager(_thresholds())
    manager.on_resources_updated(_snapshot(cpu_percent=95.0))

    manager.on_resources_updated(object())

    assert manager.current_level() is DegradationLevel.MINIMAL
