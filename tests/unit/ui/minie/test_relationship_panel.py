"""Unit tests for ui.minie.relationship_panel."""

from PySide6.QtWidgets import QLabel

from ui.minie.relationship_panel import MinieRelationshipPanel

_DIGITS = "0123456789"


def test_construction_does_not_crash(qtbot):
    panel = MinieRelationshipPanel()
    qtbot.addWidget(panel)


def test_shows_the_header(qtbot):
    panel = MinieRelationshipPanel()
    qtbot.addWidget(panel)

    texts = [label.text() for label in panel.findChildren(QLabel)]
    assert "You & Minie" in texts


def test_shows_all_three_tile_labels(qtbot):
    panel = MinieRelationshipPanel()
    qtbot.addWidget(panel)

    texts = [label.text() for label in panel.findChildren(QLabel)]
    assert "Chats" in texts
    assert "Cups Coffee Together" in texts
    assert "Songs Vibed" in texts


def test_shows_the_not_tracked_caption(qtbot):
    panel = MinieRelationshipPanel()
    qtbot.addWidget(panel)

    texts = [label.text() for label in panel.findChildren(QLabel)]
    assert "Not tracked yet ♡" in texts


def test_never_shows_a_fabricated_number(qtbot):
    """Every one of the three stat tiles shows an honest em dash — no
    digit anywhere in this panel, since nothing in this codebase backs a
    real chats/coffee/songs count (see this module's own docstring)."""
    panel = MinieRelationshipPanel()
    qtbot.addWidget(panel)

    texts = [label.text() for label in panel.findChildren(QLabel)]
    assert texts.count("—") == 3
    for text in texts:
        assert not any(digit in text for digit in _DIGITS)


def test_has_no_backend_collaborator_and_no_poll_timer(qtbot):
    """Constructor DI is deliberately just (parent) — nothing to poll,
    so no QTimer is ever started."""
    from PySide6.QtCore import QTimer

    panel = MinieRelationshipPanel()
    qtbot.addWidget(panel)

    assert panel.findChildren(QTimer) == []
