"""Unit tests for ui.minie.widgets.glass_panel."""

from presentation import minie_theme
from ui.minie.widgets.glass_panel import GlassPanel


def test_layout_accepts_child_widgets(qtbot):
    from PySide6.QtWidgets import QLabel

    panel = GlassPanel()
    qtbot.addWidget(panel)
    label = QLabel("hello")
    panel.layout_().addWidget(label)

    assert panel.layout_().count() == 1


def test_each_instance_gets_a_unique_object_name(qtbot):
    first = GlassPanel()
    second = GlassPanel()
    qtbot.addWidget(first)
    qtbot.addWidget(second)

    assert first.objectName() != second.objectName()


def test_glow_true_uses_the_given_accent_color(qtbot):
    panel = GlassPanel(glow=True, accent_color="#FF00AA")
    qtbot.addWidget(panel)

    assert "#FF00AA" in panel.styleSheet()


def test_glow_false_uses_the_dim_border(qtbot):
    panel = GlassPanel(glow=False)
    qtbot.addWidget(panel)

    assert minie_theme.BORDER_DIM in panel.styleSheet()


def test_paints_without_raising(qtbot):
    panel = GlassPanel()
    qtbot.addWidget(panel)
    panel.resize(200, 150)

    pixmap = panel.grab()

    assert not pixmap.isNull()
