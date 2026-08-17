"""Unit tests for ui.jarvis.navigation_rail."""

from ui.jarvis.navigation_rail import PAGE_ITEMS, NavigationRail, NavItem


def test_dashboard_is_checked_by_default(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)

    assert rail._buttons[NavItem.DASHBOARD].isChecked()


def test_clicking_a_page_button_emits_page_selected_and_updates_checked_state(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)
    received = []
    rail.page_selected.connect(received.append)

    rail._buttons[NavItem.MEMORY].click()

    assert received == [NavItem.MEMORY]
    assert rail._buttons[NavItem.MEMORY].isChecked()
    assert not rail._buttons[NavItem.DASHBOARD].isChecked()


def test_page_buttons_are_mutually_exclusive(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)

    rail._buttons[NavItem.TASKS].click()
    rail._buttons[NavItem.CONVERSATION].click()

    assert rail._buttons[NavItem.CONVERSATION].isChecked()
    assert not rail._buttons[NavItem.TASKS].isChecked()


def test_settings_button_emits_settings_requested(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)
    received = []
    rail.settings_requested.connect(lambda: received.append(True))

    rail._buttons[NavItem.SETTINGS].click()

    assert received == [True]


def test_system_button_emits_system_requested(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)
    received = []
    rail.system_requested.connect(lambda: received.append(True))

    rail._buttons[NavItem.SYSTEM].click()

    assert received == [True]


def test_action_buttons_never_stay_checked_after_clicking(qtbot):
    """System/Code/Settings are momentary actions, not pages — they must
    never retain a persistent "checked" highlight the way Dashboard/
    Conversation/Memory/Tasks do."""
    rail = NavigationRail()
    qtbot.addWidget(rail)

    rail._buttons[NavItem.SETTINGS].click()

    assert not rail._buttons[NavItem.SETTINGS].isChecked()


def test_code_button_starts_disabled_with_a_tooltip(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)

    assert not rail._buttons[NavItem.CODE].isEnabled()
    assert rail._buttons[NavItem.CODE].toolTip() != ""


def test_set_code_action_enabled_enables_the_button_and_clears_tooltip(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)

    rail.set_code_action_enabled(True)

    assert rail._buttons[NavItem.CODE].isEnabled()
    assert rail._buttons[NavItem.CODE].toolTip() == ""


def test_set_code_action_enabled_false_restores_the_tooltip(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)
    rail.set_code_action_enabled(True)

    rail.set_code_action_enabled(False)

    assert not rail._buttons[NavItem.CODE].isEnabled()
    assert rail._buttons[NavItem.CODE].toolTip() != ""


def test_select_dashboard_rechecks_the_dashboard_row(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)
    rail._buttons[NavItem.MEMORY].click()

    rail.select_dashboard()

    assert rail._buttons[NavItem.DASHBOARD].isChecked()


def test_all_seven_nav_items_have_a_button(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)

    for item in NavItem:
        assert item in rail._buttons


def test_page_items_constant_excludes_action_items():
    assert set(PAGE_ITEMS) == {
        NavItem.DASHBOARD,
        NavItem.CONVERSATION,
        NavItem.MEMORY,
        NavItem.TASKS,
    }


def test_set_accent_color_propagates_to_every_button(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)

    rail.set_accent_color("#C8A8E9")

    for button in rail._buttons.values():
        assert button._accent_color == "#C8A8E9"


def test_default_accent_color_is_the_theme_default(qtbot):
    from presentation import theme

    rail = NavigationRail()
    qtbot.addWidget(rail)

    assert rail._buttons[NavItem.DASHBOARD]._accent_color == theme.ACCENT_CYAN


def test_paints_without_raising_after_a_custom_accent_color(qtbot):
    rail = NavigationRail()
    qtbot.addWidget(rail)
    rail.resize(220, 320)
    rail.set_accent_color("#C8A8E9")

    pixmap = rail.grab()  # forces a real paintEvent() call, including the checked Dashboard row

    assert not pixmap.isNull()
