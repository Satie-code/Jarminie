"""Unit tests for ui.minie.notes_panel."""

from ui.minie.notes_panel import _STARTER_NOTES, MinieNotesPanel, NoteItem


def test_construction_does_not_crash(qtbot):
    panel = MinieNotesPanel()
    qtbot.addWidget(panel)


def test_seeds_starter_notes_on_construction(qtbot):
    panel = MinieNotesPanel()
    qtbot.addWidget(panel)

    assert [note.text for note in panel._notes] == _STARTER_NOTES
    assert all(not note.done for note in panel._notes)
    assert panel._rows_layout.count() == len(_STARTER_NOTES)


def test_add_field_is_hidden_until_the_plus_button_is_clicked(qtbot):
    panel = MinieNotesPanel()
    qtbot.addWidget(panel)
    panel.show()  # .isVisible() reflects real paint-visibility, which needs
    # the whole ancestor chain (incl. this top-level widget) shown --
    # qtbot.addWidget() alone only registers the widget for cleanup.

    assert not panel._add_container.isVisible()

    panel._add_button.click()

    assert panel._add_container.isVisible()


def test_committing_a_new_note_appends_it_and_clears_the_field(qtbot):
    panel = MinieNotesPanel()
    qtbot.addWidget(panel)
    starting_count = len(panel._notes)
    panel._add_input.setText("Water the plants")

    panel._commit_new_note()

    assert len(panel._notes) == starting_count + 1
    assert panel._notes[-1] == NoteItem(text="Water the plants", done=False)
    assert panel._add_input.text() == ""
    assert not panel._add_container.isVisible()
    assert panel._rows_layout.count() == starting_count + 1


def test_committing_blank_text_does_not_add_a_note(qtbot):
    panel = MinieNotesPanel()
    qtbot.addWidget(panel)
    starting_count = len(panel._notes)
    panel._add_input.setText("   ")

    panel._commit_new_note()

    assert len(panel._notes) == starting_count


def test_enter_key_commits_a_new_note(qtbot):
    panel = MinieNotesPanel()
    qtbot.addWidget(panel)
    starting_count = len(panel._notes)
    panel._add_input.setText("Call mom")

    panel._add_input.returnPressed.emit()

    assert len(panel._notes) == starting_count + 1


def test_clicking_a_notes_checkmark_toggles_done_and_updates_the_glyph(qtbot):
    panel = MinieNotesPanel()
    qtbot.addWidget(panel)
    row = panel._rows_layout.itemAt(0).widget()
    assert row._check_button.text() == "○"

    row._check_button.click()

    assert row._note.done is True
    assert row._check_button.text() == "✓"

    row._check_button.click()

    assert row._note.done is False
    assert row._check_button.text() == "○"


def test_done_note_text_gets_a_strike_through_style(qtbot):
    panel = MinieNotesPanel()
    qtbot.addWidget(panel)
    row = panel._rows_layout.itemAt(0).widget()

    row._check_button.click()

    assert "line-through" in row._text_label.styleSheet()
