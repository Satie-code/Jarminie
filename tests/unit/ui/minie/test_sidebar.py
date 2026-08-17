"""Unit tests for ui.minie.sidebar."""

from unittest.mock import MagicMock

from config.schema import PresentationConfig
from presentation import minie_theme
from ui.minie.sidebar import PAGE_ITEMS, MinieSidebar, NavItem


def _core_manager(accent: str = "#B76E79") -> MagicMock:
    manager = MagicMock()
    manager.presentation_config.return_value = PresentationConfig(minie_ui_accent=accent)
    return manager


def test_home_is_the_default_active_page(qtbot):
    sidebar = MinieSidebar(_core_manager())
    qtbot.addWidget(sidebar)

    assert sidebar._buttons["home"].isChecked()


def test_clicking_a_page_button_emits_page_selected_and_updates_checked_state(qtbot):
    sidebar = MinieSidebar(_core_manager())
    qtbot.addWidget(sidebar)
    received = []
    sidebar.page_selected.connect(received.append)

    sidebar._buttons["chat"].click()

    assert received == ["chat"]
    assert sidebar._buttons["chat"].isChecked()
    assert not sidebar._buttons["home"].isChecked()


def test_page_buttons_are_mutually_exclusive(qtbot):
    sidebar = MinieSidebar(_core_manager())
    qtbot.addWidget(sidebar)

    sidebar._buttons["tasks"].click()
    sidebar._buttons["wellness"].click()

    assert sidebar._buttons["wellness"].isChecked()
    assert not sidebar._buttons["tasks"].isChecked()


def test_settings_button_emits_settings_requested_and_never_stays_checked(qtbot):
    sidebar = MinieSidebar(_core_manager())
    qtbot.addWidget(sidebar)
    received = []
    sidebar.settings_requested.connect(lambda: received.append(True))

    sidebar._settings_button.click()

    assert received == [True]
    assert not sidebar._settings_button.isChecked()


def test_set_active_page_highlights_the_row_without_emitting_page_selected(qtbot):
    sidebar = MinieSidebar(_core_manager())
    qtbot.addWidget(sidebar)
    received = []
    sidebar.page_selected.connect(received.append)

    sidebar.set_active_page("calendar")

    assert sidebar._buttons["calendar"].isChecked()
    assert not sidebar._buttons["home"].isChecked()
    assert received == []


def test_set_active_page_with_an_unknown_id_does_not_raise_or_change_state(qtbot):
    sidebar = MinieSidebar(_core_manager())
    qtbot.addWidget(sidebar)

    sidebar.set_active_page("not-a-real-page")  # must not raise

    assert sidebar._buttons["home"].isChecked()


def test_all_six_page_items_and_settings_have_buttons(qtbot):
    sidebar = MinieSidebar(_core_manager())
    qtbot.addWidget(sidebar)

    for item in PAGE_ITEMS:
        assert item.value in sidebar._buttons
    assert sidebar._settings_button is not None


def test_page_items_constant_has_exactly_six_pages():
    assert set(PAGE_ITEMS) == {
        NavItem.HOME,
        NavItem.CHAT,
        NavItem.TASKS,
        NavItem.CALENDAR,
        NavItem.WELLNESS,
        NavItem.REMINDERS,
    }


def test_accent_color_is_read_once_from_presentation_config(qtbot):
    sidebar = MinieSidebar(_core_manager(accent="#C8A8E9"))
    qtbot.addWidget(sidebar)

    assert sidebar._buttons["home"]._accent_color == "#C8A8E9"


def test_falls_back_to_the_default_accent_when_config_read_fails(qtbot):
    manager = MagicMock()
    manager.presentation_config.side_effect = RuntimeError("boom")

    sidebar = MinieSidebar(manager)  # must not raise
    qtbot.addWidget(sidebar)

    assert sidebar._buttons["home"]._accent_color == minie_theme.PRIMARY_ACCENT_DEFAULT


def test_paints_without_raising(qtbot):
    sidebar = MinieSidebar(_core_manager())
    qtbot.addWidget(sidebar)
    sidebar.resize(220, 480)

    pixmap = sidebar.grab()  # forces a real paintEvent() for every row, including checked Home

    assert not pixmap.isNull()
