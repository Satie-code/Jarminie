"""Unit tests for ui.jarvis.reminders_panel."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from config.schema import UIConfig
from scheduler.scheduler_model import ItemType, ScheduledItem
from ui.jarvis.reminders_panel import RemindersDialog, RemindersPanel


def _core_manager(interval_ms: int = 3000) -> MagicMock:
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    return manager


def _item(item_id: str = "1", title: str = "Robotics Meeting") -> ScheduledItem:
    return ScheduledItem(
        item_id=item_id,
        item_type=ItemType.EVENT,
        title=title,
        scheduled_at=datetime(2026, 8, 17, 11, 0, tzinfo=UTC),
        created_at=datetime.now(UTC),
    )


def test_shows_a_row_per_upcoming_item(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = [_item("1", "Robotics Meeting"), _item("2", "Gym Session")]
    panel = RemindersPanel(store, _core_manager())
    qtbot.addWidget(panel)

    row_count = panel._rows_layout.count()
    texts = [panel._rows_layout.itemAt(i).widget().text() for i in range(row_count)]
    assert any("Robotics Meeting" in t for t in texts)
    assert any("Gym Session" in t for t in texts)


def test_shows_a_message_when_nothing_scheduled(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = []
    panel = RemindersPanel(store, _core_manager())
    qtbot.addWidget(panel)

    text = panel._rows_layout.itemAt(0).widget().text()
    assert "Nothing scheduled" in text


def test_refresh_survives_a_raising_calendar_store(qtbot):
    store = MagicMock()
    store.list_due_within.side_effect = RuntimeError("boom")

    panel = RemindersPanel(store, _core_manager())  # construction calls refresh() once
    qtbot.addWidget(panel)

    panel.refresh()  # must not raise on a later call either
    text = panel._rows_layout.itemAt(0).widget().text()
    assert "unavailable" in text.lower()


def test_refresh_does_not_accumulate_rows_across_calls(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = [_item()]
    panel = RemindersPanel(store, _core_manager())
    qtbot.addWidget(panel)

    panel.refresh()
    panel.refresh()

    assert panel._rows_layout.count() == 1


def test_view_all_button_opens_a_reminders_dialog(qtbot, monkeypatch):
    import ui.jarvis.reminders_panel as module

    store = MagicMock()
    store.list_due_within.return_value = []
    panel = RemindersPanel(store, _core_manager())
    qtbot.addWidget(panel)

    opened = []

    class _FakeDialog:
        def __init__(self, calendar_store, parent):
            opened.append(calendar_store)

        def exec(self):
            return None

    monkeypatch.setattr(module, "RemindersDialog", _FakeDialog)

    panel._open_view_all()

    assert opened == [store]


# --- RemindersDialog -----------------------------------------------------


def test_dialog_lists_every_non_completed_item(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = [_item("1", "Robotics Meeting"), _item("2", "Gym Session")]

    dialog = RemindersDialog(store, None)
    qtbot.addWidget(dialog)

    assert dialog._rows_layout.count() == 3  # 2 rows + the trailing stretch


def test_dialog_shows_a_message_when_empty(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = []

    dialog = RemindersDialog(store, None)
    qtbot.addWidget(dialog)

    empty_label = dialog._rows_layout.itemAt(0).widget()
    assert "Nothing scheduled" in empty_label.text()


def test_mark_done_calls_calendar_store_and_reloads(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = [_item("1", "Robotics Meeting")]

    dialog = RemindersDialog(store, None)
    qtbot.addWidget(dialog)
    store.list_due_within.return_value = []  # simulate it now being done

    dialog._mark_done("1")

    store.mark_completed.assert_called_once_with("1")
    # Reloaded down to just the empty-state message (plus the layout's own
    # permanent trailing stretch item — see RemindersDialog.__init__()).
    empty_label = dialog._rows_layout.itemAt(0).widget()
    assert "Nothing scheduled" in empty_label.text()


def test_mark_done_survives_a_raising_calendar_store(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = [_item("1", "Robotics Meeting")]
    dialog = RemindersDialog(store, None)
    qtbot.addWidget(dialog)
    store.mark_completed.side_effect = RuntimeError("boom")

    dialog._mark_done("1")  # must not raise
