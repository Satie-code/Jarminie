"""Unit tests for ui.minie.top_bar.

Named test_minie_top_bar.py rather than test_top_bar.py: this repo has
no __init__.py anywhere under tests/ (by convention since Sprint 1.1),
so pytest imports test modules by their bare basename — a second
"test_top_bar.py" would collide with tests/unit/ui/jarvis/test_top_bar.py
(ui/jarvis/top_bar.py's own, pre-existing test file) when both are
collected in the same run. Disambiguated by prefixing the persona name,
the minimal fix that doesn't touch the pre-existing Jarvis file or the
project's own established no-__init__.py test-tree convention.
"""

from datetime import datetime
from unittest.mock import MagicMock

from config.schema import UIConfig
from core.resource_monitor import ResourceSnapshot
from ui.minie.top_bar import _CLOCK_INTERVAL_MS, MinieTopBar


def _snapshot(battery_percent: float | None) -> ResourceSnapshot:
    return ResourceSnapshot(
        cpu_percent=10.0,
        ram_percent=20.0,
        disk_percent=30.0,
        battery_percent=battery_percent,
        timestamp=datetime.now(),
    )


def _core_manager(battery_percent: float | None = None, interval_ms: int = 3000) -> MagicMock:
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    manager.check_resources.return_value = _snapshot(battery_percent)
    return manager


def test_clock_label_populates_on_construction(qtbot):
    bar = MinieTopBar(_core_manager())
    qtbot.addWidget(bar)

    assert bar._datetime_label.text() != ""


def test_network_and_volume_are_honest_static_na(qtbot):
    bar = MinieTopBar(_core_manager())
    qtbot.addWidget(bar)

    assert bar._network_label.text() == "Network: N/A"
    assert bar._volume_label.text() == "Volume: N/A"


def test_battery_shows_na_when_no_battery_is_reported(qtbot):
    bar = MinieTopBar(_core_manager(battery_percent=None))
    qtbot.addWidget(bar)

    assert "N/A" in bar._battery_label.text()


def test_battery_shows_a_real_percent_when_reported(qtbot):
    bar = MinieTopBar(_core_manager(battery_percent=78.0))
    qtbot.addWidget(bar)

    assert "78%" in bar._battery_label.text()


def test_refresh_survives_a_failed_resource_read_without_crashing(qtbot):
    manager = _core_manager(battery_percent=55.0)
    bar = MinieTopBar(manager)  # construction itself calls refresh() once
    qtbot.addWidget(bar)

    manager.check_resources.side_effect = RuntimeError("resource monitor exploded")
    bar.refresh()  # must not raise


def test_refresh_keeps_last_known_good_battery_reading_after_a_later_failure(qtbot):
    manager = _core_manager(battery_percent=42.0)
    bar = MinieTopBar(manager)
    qtbot.addWidget(bar)
    good_text = bar._battery_label.text()

    manager.check_resources.side_effect = RuntimeError("resource monitor exploded")
    bar.refresh()

    assert bar._battery_label.text() == good_text


def test_minimize_button_emits_minimize_requested(qtbot):
    bar = MinieTopBar(_core_manager())
    qtbot.addWidget(bar)
    received = []
    bar.minimize_requested.connect(lambda: received.append(True))

    bar._minimize_button.click()

    assert received == [True]


def test_maximize_button_emits_maximize_requested(qtbot):
    bar = MinieTopBar(_core_manager())
    qtbot.addWidget(bar)
    received = []
    bar.maximize_requested.connect(lambda: received.append(True))

    bar._maximize_button.click()

    assert received == [True]


def test_close_button_emits_close_requested(qtbot):
    bar = MinieTopBar(_core_manager())
    qtbot.addWidget(bar)
    received = []
    bar.close_requested.connect(lambda: received.append(True))

    bar._close_button.click()

    assert received == [True]


def test_status_timer_interval_comes_from_config(qtbot):
    bar = MinieTopBar(_core_manager(interval_ms=1234))
    qtbot.addWidget(bar)

    assert bar._status_timer.interval() == 1234


def test_clock_timer_runs_at_the_fixed_one_second_interval(qtbot):
    bar = MinieTopBar(_core_manager())
    qtbot.addWidget(bar)

    assert bar._clock_timer.interval() == _CLOCK_INTERVAL_MS == 1000
