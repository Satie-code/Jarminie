"""Unit tests for ui.jarvis.temperature_panel."""

from PySide6.QtWidgets import QLabel

from ui.jarvis.temperature_panel import TemperaturePanel


def test_shows_na_for_every_row(qtbot):
    panel = TemperaturePanel()
    qtbot.addWidget(panel)

    texts = [label.text() for label in panel.findChildren(QLabel)]
    na_count = sum(1 for text in texts if text == "N/A")

    assert na_count == 3  # CPU, GPU, Motherboard


def test_paints_without_raising(qtbot):
    panel = TemperaturePanel()
    qtbot.addWidget(panel)
    panel.resize(200, 150)

    pixmap = panel.grab()

    assert not pixmap.isNull()
