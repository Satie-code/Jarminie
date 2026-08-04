"""Unit tests for presentation.qt_transition_overlay (Sprint 5.14; the
per-tick exception guard is a Sprint 5.16 Post-Sprint Fix, found during
that sprint's own adversarial re-read — no dedicated test file existed
for this class before now).
"""

from presentation.qt_transition_overlay import QtTransitionOverlay
from presentation.transition_engine import TransitionPhase


def _overlay(qtbot):
    from PySide6.QtWidgets import QWidget

    host_widget = QWidget()
    qtbot.addWidget(host_widget)
    overlay = QtTransitionOverlay(host_widget)
    qtbot.addWidget(overlay)
    return overlay


def test_starts_hidden(qtbot):
    overlay = _overlay(qtbot)
    assert overlay.isVisible() is False


def test_show_set_phase_hide_do_not_raise(qtbot):
    overlay = _overlay(qtbot)
    overlay.show()
    overlay.set_phase(TransitionPhase.SHOWING_CORE)
    overlay.hide()  # must not raise


# --- _on_tick() exception guarding (Sprint 5.16 Post-Sprint Fix) -------------
#
# A corrupted _pulse_phase (a str, not a float) forces a real TypeError
# from _on_tick()'s own arithmetic — the same portable technique
# tests/unit/presentation/test_jarvis_renderer.py's own widget _on_tick()
# tests already established.


def test_on_tick_survives_a_raising_tick(qtbot, caplog):
    overlay = _overlay(qtbot)
    overlay._pulse_phase = "not-a-number"
    last_good = overlay._pulse_phase

    with caplog.at_level("ERROR"):
        overlay._on_tick()  # must not raise

    assert any("_on_tick" in r.message for r in caplog.records)
    assert overlay._pulse_phase == last_good  # last-good frame retained


def test_on_tick_logs_a_repeated_failure_only_once(qtbot, caplog):
    overlay = _overlay(qtbot)
    overlay._pulse_phase = "not-a-number"

    with caplog.at_level("ERROR"):
        overlay._on_tick()
        overlay._on_tick()
        overlay._on_tick()

    failures = [r for r in caplog.records if "_on_tick" in r.message]
    assert len(failures) == 1


def test_on_tick_recovers_after_a_transient_failure(qtbot, caplog):
    overlay = _overlay(qtbot)

    with caplog.at_level("ERROR"):
        overlay._pulse_phase = "not-a-number"
        overlay._on_tick()  # fails, logs once
        overlay._pulse_phase = 0.0
        overlay._on_tick()  # recovers
        overlay._pulse_phase = "not-a-number"
        overlay._on_tick()  # fails again — logs again, since the flag reset on recovery

    failures = [r for r in caplog.records if "_on_tick" in r.message]
    assert len(failures) == 2
