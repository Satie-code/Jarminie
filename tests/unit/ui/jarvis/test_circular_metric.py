"""Unit tests for ui.jarvis.widgets.circular_metric."""

from ui.jarvis.widgets.circular_metric import CircularMetric


def test_paints_without_raising_with_a_real_value(qtbot):
    widget = CircularMetric("CPU")
    qtbot.addWidget(widget)
    widget.resize(80, 90)
    widget.set_value(42.0)

    pixmap = widget.grab()  # forces a real paintEvent() call

    assert not pixmap.isNull()


def test_paints_without_raising_with_no_value(qtbot):
    widget = CircularMetric("GPU")
    qtbot.addWidget(widget)
    widget.resize(80, 90)
    widget.set_value(None)

    pixmap = widget.grab()

    assert not pixmap.isNull()


def test_defaults_to_no_value(qtbot):
    widget = CircularMetric("CPU")
    qtbot.addWidget(widget)

    assert widget._value is None


def test_set_value_stores_the_value(qtbot):
    widget = CircularMetric("RAM")
    qtbot.addWidget(widget)

    widget.set_value(55.0)

    assert widget._value == 55.0


def test_zero_size_paint_does_not_raise(qtbot):
    widget = CircularMetric("DISK")
    qtbot.addWidget(widget)
    widget.resize(0, 0)
    widget.set_value(10.0)

    widget.grab()  # must not raise


def test_out_of_range_value_does_not_raise(qtbot):
    widget = CircularMetric("CPU")
    qtbot.addWidget(widget)
    widget.resize(80, 90)
    widget.set_value(250.0)  # a real value could in principle exceed 100 briefly

    widget.grab()  # must not raise
