"""Unit tests for ui.jarvis.top_bar."""

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLabel

from config.schema import UIConfig
from ui.jarvis.top_bar import TopBar, _greeting_for_hour


def _core_manager(user_display_name=None):
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig(user_display_name=user_display_name)
    return manager


def _session_manager():
    return MagicMock()


def test_branding_labels_are_present(qtbot):
    bar = TopBar(_core_manager(), _session_manager())
    qtbot.addWidget(bar)

    texts = [label.text() for label in bar.findChildren(QLabel)]
    assert "JARVIS" in texts
    assert "JUST A RATHER VERY INTELLIGENT SYSTEM" in texts


def test_greeting_falls_back_to_there_when_no_display_name_configured(qtbot):
    bar = TopBar(_core_manager(user_display_name=None), _session_manager())
    qtbot.addWidget(bar)

    assert "THERE" in bar._greeting_label.text()


def test_greeting_uses_configured_display_name(qtbot):
    bar = TopBar(_core_manager(user_display_name="Sattie"), _session_manager())
    qtbot.addWidget(bar)

    assert "SATTIE" in bar._greeting_label.text()


def test_clock_and_date_labels_populate_on_construction(qtbot):
    bar = TopBar(_core_manager(), _session_manager())
    qtbot.addWidget(bar)

    assert bar._clock_label.text() != ""
    assert bar._date_label.text() != ""


def test_refresh_survives_a_failed_config_read_without_crashing(qtbot):
    manager = MagicMock()
    manager.ui_config.side_effect = RuntimeError("config exploded")

    bar = TopBar(manager, _session_manager())  # construction itself calls refresh() once
    qtbot.addWidget(bar)

    bar.refresh()  # must not raise on a later call either


def test_refresh_keeps_last_known_good_greeting_after_a_later_failure(qtbot):
    manager = _core_manager(user_display_name="Sattie")
    bar = TopBar(manager, _session_manager())
    qtbot.addWidget(bar)
    good_text = bar._greeting_label.text()

    manager.ui_config.side_effect = RuntimeError("config exploded")
    bar.refresh()

    assert bar._greeting_label.text() == good_text


def test_embeds_a_voice_visualizer(qtbot):
    from ui.jarvis.voice_visualizer import VoiceVisualizer

    bar = TopBar(_core_manager(), _session_manager())
    qtbot.addWidget(bar)

    assert bar.findChild(VoiceVisualizer) is not None


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, "Good evening"),
        (4, "Good evening"),
        (5, "Good morning"),
        (11, "Good morning"),
        (12, "Good afternoon"),
        (16, "Good afternoon"),
        (17, "Good evening"),
        (23, "Good evening"),
    ],
)
def test_greeting_for_hour_matches_time_of_day(hour, expected):
    assert _greeting_for_hour(hour) == expected
