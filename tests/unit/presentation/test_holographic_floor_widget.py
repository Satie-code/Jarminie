"""Unit tests for presentation.widgets.holographic_floor_widget."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from presentation.widgets.holographic_floor_widget import HolographicFloorWidget


def test_paints_without_raising(qtbot):
    widget = HolographicFloorWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 160)

    pixmap = widget.grab()  # forces a real paintEvent() call

    assert not pixmap.isNull()


def test_set_color_updates_the_stored_color_and_triggers_a_repaint(qtbot):
    widget = HolographicFloorWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 160)

    widget.set_color(QColor("#C8A8E9"))

    assert widget._color.name() == "#c8a8e9"


def test_zero_size_paint_does_not_raise(qtbot):
    widget = HolographicFloorWidget()
    qtbot.addWidget(widget)
    widget.resize(0, 0)

    widget.grab()  # must not raise


def test_is_transparent_for_mouse_events(qtbot):
    widget = HolographicFloorWidget()
    qtbot.addWidget(widget)

    assert widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
