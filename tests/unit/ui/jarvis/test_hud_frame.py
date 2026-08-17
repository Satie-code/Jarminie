"""Unit tests for ui.jarvis.hud_frame."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from presentation import theme
from ui.jarvis.hud_frame import HudFrame


def test_paints_without_raising(qtbot):
    parent = QWidget()
    parent.resize(400, 300)
    qtbot.addWidget(parent)

    frame = HudFrame(parent)

    frame.grab()  # forces a real paintEvent


def test_sync_geometry_matches_parent_rect_after_a_resize(qtbot):
    parent = QWidget()
    parent.resize(500, 260)
    qtbot.addWidget(parent)
    frame = HudFrame(parent)

    parent.resize(640, 400)
    frame.sync_geometry()

    assert frame.rect().width() == parent.rect().width()
    assert frame.rect().height() == parent.rect().height()


def test_is_transparent_for_mouse_events(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    frame = HudFrame(parent)

    assert frame.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_paint_event_on_zero_sized_widget_does_not_raise(qtbot):
    parent = QWidget()
    parent.resize(0, 0)
    qtbot.addWidget(parent)
    frame = HudFrame(parent)
    frame.resize(0, 0)

    frame.repaint()


def test_default_accent_color_is_the_theme_default(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    frame = HudFrame(parent)

    assert frame._accent_color == theme.BORDER_ACCENT


def test_set_accent_color_updates_the_stored_color(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    frame = HudFrame(parent)

    frame.set_accent_color("#22D3EE")

    assert frame._accent_color == "#22D3EE"


def test_paints_without_raising_after_a_custom_accent_color(qtbot):
    parent = QWidget()
    parent.resize(400, 300)
    qtbot.addWidget(parent)
    frame = HudFrame(parent)
    frame.set_accent_color("#22D3EE")

    pixmap = frame.grab()

    assert not pixmap.isNull()
