"""Unit tests for ui.minie.plan_panel."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from PySide6.QtWidgets import QLabel, QPushButton

from config.schema import UIConfig
from scheduler.scheduler_model import ItemType, ScheduledItem
from ui.minie.plan_panel import MinieTodaysPlanPanel


def _core_manager(interval_ms: int = 3000) -> MagicMock:
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    return manager


def _item(
    item_id: str,
    title: str,
    scheduled_at: datetime,
    *,
    is_completed: bool = False,
    item_type: ItemType = ItemType.EVENT,
) -> ScheduledItem:
    return ScheduledItem(
        item_id=item_id,
        item_type=item_type,
        title=title,
        scheduled_at=scheduled_at,
        created_at=datetime.now(UTC),
        is_completed=is_completed,
    )


def _start_of_today() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _row_texts(panel: MinieTodaysPlanPanel) -> list[str]:
    """Every row is either a plain QLabel (empty/failure message rows,
    via _add_message_row()) or a composite row widget with its own child
    QLabels (title + time, via _build_row()) — collect all label text
    either way."""
    texts = []
    for index in range(panel._rows_layout.count()):
        widget = panel._rows_layout.itemAt(index).widget()
        if widget is None:
            continue
        if isinstance(widget, QLabel):
            texts.append(widget.text())
        else:
            texts.append(" ".join(label.text() for label in widget.findChildren(QLabel)))
    return texts


def test_only_todays_items_are_shown(qtbot):
    start_of_today = _start_of_today()
    yesterday_item = _item("y", "Yesterday Task", start_of_today - timedelta(hours=1))
    today_item = _item("t", "Today Task", start_of_today + timedelta(hours=9))
    tomorrow_item = _item("tm", "Tomorrow Task", start_of_today + timedelta(days=1, hours=1))
    store = MagicMock()
    store.list_due_within.return_value = [yesterday_item, today_item, tomorrow_item]

    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)

    texts = _row_texts(panel)
    assert any("Today Task" in text for text in texts)
    assert not any("Yesterday Task" in text for text in texts)
    assert not any("Tomorrow Task" in text for text in texts)


def test_item_exactly_at_start_of_today_is_included(qtbot):
    start_of_today = _start_of_today()
    boundary_item = _item("b", "Midnight Task", start_of_today)
    store = MagicMock()
    store.list_due_within.return_value = [boundary_item]

    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)

    assert any("Midnight Task" in text for text in _row_texts(panel))


def test_item_exactly_at_start_of_tomorrow_is_excluded(qtbot):
    start_of_today = _start_of_today()
    boundary_item = _item("b", "Next Midnight Task", start_of_today + timedelta(days=1))
    store = MagicMock()
    store.list_due_within.return_value = [boundary_item]

    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)

    assert not any("Next Midnight Task" in text for text in _row_texts(panel))
    assert any("Nothing scheduled for today" in text for text in _row_texts(panel))


def test_queries_the_calendar_store_with_include_completed(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = []

    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)

    store.list_due_within.assert_called_once()
    _args, kwargs = store.list_due_within.call_args
    assert kwargs.get("include_completed") is True


def test_shows_message_when_nothing_scheduled_today(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = []

    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)

    text = panel._rows_layout.itemAt(0).widget().text()
    assert "Nothing scheduled for today" in text


def test_refresh_survives_a_raising_calendar_store(qtbot):
    store = MagicMock()
    store.list_due_within.side_effect = RuntimeError("boom")

    panel = MinieTodaysPlanPanel(store, _core_manager())  # construction calls refresh() once
    qtbot.addWidget(panel)

    panel.refresh()  # must not raise on a later call either
    text = panel._rows_layout.itemAt(0).widget().text()
    assert "unavailable" in text.lower()


def test_completed_item_shows_a_disabled_checkmark(qtbot):
    start_of_today = _start_of_today()
    item = _item("1", "Finished Task", start_of_today + timedelta(hours=10), is_completed=True)
    store = MagicMock()
    store.list_due_within.return_value = [item]

    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)

    row = panel._rows_layout.itemAt(0).widget()
    button = row.findChild(QPushButton)
    assert button.text() == "✓"
    assert not button.isEnabled()


def test_incomplete_item_shows_an_enabled_circle_glyph(qtbot):
    start_of_today = _start_of_today()
    item = _item("1", "Pending Task", start_of_today + timedelta(hours=10), is_completed=False)
    store = MagicMock()
    store.list_due_within.return_value = [item]

    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)

    row = panel._rows_layout.itemAt(0).widget()
    button = row.findChild(QPushButton)
    assert button.text() == "○"
    assert button.isEnabled()


def test_clicking_an_incomplete_items_glyph_marks_it_done_and_refreshes(qtbot):
    start_of_today = _start_of_today()
    item = _item("1", "Pending Task", start_of_today + timedelta(hours=10), is_completed=False)
    store = MagicMock()
    store.list_due_within.return_value = [item]

    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)
    row = panel._rows_layout.itemAt(0).widget()
    button = row.findChild(QPushButton)

    button.click()

    store.mark_completed.assert_called_once_with("1")
    # refresh() was called again as part of _mark_done() — list_due_within
    # is invoked a second time.
    assert store.list_due_within.call_count == 2


def test_mark_done_survives_a_raising_calendar_store(qtbot):
    start_of_today = _start_of_today()
    item = _item("1", "Pending Task", start_of_today + timedelta(hours=10), is_completed=False)
    store = MagicMock()
    store.list_due_within.return_value = [item]
    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)
    store.mark_completed.side_effect = RuntimeError("boom")

    panel._mark_done("1")  # must not raise


def test_view_calendar_requested_emitted_on_click(qtbot):
    store = MagicMock()
    store.list_due_within.return_value = []
    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)
    button = next(b for b in panel.findChildren(QPushButton) if b.text() == "View Calendar")

    with qtbot.waitSignal(panel.view_calendar_requested, timeout=1000):
        button.click()


def test_no_priority_badge_is_ever_shown(qtbot):
    """ScheduledItem has no priority field at all (see this module's own
    docstring) — every row's text is exactly glyph/title/time, nothing
    resembling a priority badge."""
    start_of_today = _start_of_today()
    item = _item("1", "Some Task", start_of_today + timedelta(hours=10))
    store = MagicMock()
    store.list_due_within.return_value = [item]

    panel = MinieTodaysPlanPanel(store, _core_manager())
    qtbot.addWidget(panel)

    row = panel._rows_layout.itemAt(0).widget()
    for label in row.findChildren(QLabel):
        assert "priority" not in label.text().lower()
