"""Unit tests for ui.minie.widgets.emotion_bar."""

from ui.minie.widgets.emotion_bar import EmotionBar


def test_defaults_to_zero(qtbot):
    bar = EmotionBar("Happiness")
    qtbot.addWidget(bar)

    assert bar.value == 0.0


def test_set_value_animates_toward_the_target(qtbot):
    bar = EmotionBar("Trust")
    qtbot.addWidget(bar)

    bar.set_value(80.0)

    assert bar._animation.endValue() == 80.0


def test_set_value_clamps_above_100(qtbot):
    bar = EmotionBar("Affection")
    qtbot.addWidget(bar)

    bar.set_value(150.0)

    assert bar._animation.endValue() == 100.0


def test_set_value_clamps_below_zero(qtbot):
    bar = EmotionBar("Calmness")
    qtbot.addWidget(bar)

    bar.set_value(-20.0)

    assert bar._animation.endValue() == 0.0


def test_value_updates_immediately_once_animation_completes(qtbot):
    bar = EmotionBar("Happiness")
    qtbot.addWidget(bar)

    bar.set_value(60.0)
    qtbot.waitUntil(lambda: bar.value == 60.0, timeout=2000)


def test_paints_without_raising(qtbot):
    bar = EmotionBar("Trust")
    qtbot.addWidget(bar)
    bar.resize(220, 40)
    bar.set_value(45.0)

    pixmap = bar.grab()

    assert not pixmap.isNull()
