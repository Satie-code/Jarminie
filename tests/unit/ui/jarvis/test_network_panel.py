"""Unit tests for ui.jarvis.network_panel."""

from PySide6.QtWidgets import QLabel

from ui.jarvis.network_panel import NetworkPanel


def test_shows_unavailable(qtbot):
    panel = NetworkPanel()
    qtbot.addWidget(panel)

    texts = [label.text() for label in panel.findChildren(QLabel)]

    assert "Unavailable" in texts


def test_paints_without_raising(qtbot):
    panel = NetworkPanel()
    qtbot.addWidget(panel)
    panel.resize(200, 100)

    pixmap = panel.grab()

    assert not pixmap.isNull()
