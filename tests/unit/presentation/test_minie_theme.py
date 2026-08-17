"""Unit tests for presentation.minie_theme."""

from presentation import minie_theme


def test_build_minie_stylesheet_includes_the_given_accent_color():
    stylesheet = minie_theme.build_minie_stylesheet("#FF00AA")

    assert "#FF00AA" in stylesheet


def test_build_minie_stylesheet_defaults_to_the_documented_default_accent():
    stylesheet = minie_theme.build_minie_stylesheet()

    assert minie_theme.PRIMARY_ACCENT_DEFAULT in stylesheet


def test_build_minie_stylesheet_includes_background_and_text_tokens():
    stylesheet = minie_theme.build_minie_stylesheet()

    assert minie_theme.BG_VOID in stylesheet
    assert minie_theme.TEXT_PRIMARY in stylesheet


def test_accent_qcolor_parses_the_given_hex_string(qtbot):
    color = minie_theme.accent_qcolor("#B76E79")

    assert color.isValid()
    assert color.name().lower() == "#b76e79"


def test_default_tokens_are_valid_hex_colors(qtbot):
    from PySide6.QtGui import QColor

    for token in (
        minie_theme.BG_VOID,
        minie_theme.BG_PANEL,
        minie_theme.BG_PANEL_RAISED,
        minie_theme.BORDER_DIM,
        minie_theme.BORDER_ACCENT,
        minie_theme.SECONDARY_ACCENT,
        minie_theme.TEXT_PRIMARY,
        minie_theme.TEXT_SECONDARY,
        minie_theme.TEXT_DIM,
        minie_theme.STATUS_GREEN,
        minie_theme.STATUS_AMBER,
        minie_theme.STATUS_RED,
        minie_theme.STATUS_GRAY,
        minie_theme.PRIMARY_ACCENT_DEFAULT,
        minie_theme.GLOW_DEFAULT,
    ):
        assert QColor(token).isValid(), f"{token!r} is not a valid color"
