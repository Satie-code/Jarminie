"""Unit tests for ui.minie.weather_panel."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from config.schema import UIConfig
from services.weather_service import DayForecast, WeatherSnapshot
from ui.minie.weather_panel import MinieWeatherPanel


def _core_manager() -> MagicMock:
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig()
    return manager


def _snapshot(forecast_count: int = 4) -> WeatherSnapshot:
    forecast = [
        DayForecast(day_label=label, high_c=29.0 + index, low_c=18.0, condition_text="Sunny")
        for index, label in enumerate(["Sat", "Sun", "Mon", "Tue", "Wed"][:forecast_count])
    ]
    return WeatherSnapshot(
        temperature_c=28.0,
        condition_text="Partly cloudy",
        high_c=29.0,
        low_c=19.0,
        location_name="Chennai",
        forecast=forecast,
        fetched_at=datetime.now(UTC),
    )


def test_construction_does_not_crash(qtbot):
    service = MagicMock()
    service.current.return_value = None
    panel = MinieWeatherPanel(service, _core_manager())
    qtbot.addWidget(panel)


def test_shows_unavailable_before_the_background_fetch_resolves_but_settles(qtbot):
    service = MagicMock()
    service.current.return_value = None

    panel = MinieWeatherPanel(service, _core_manager())
    qtbot.addWidget(panel)
    panel.show()  # .isVisible() below reflects real paint-visibility, which
    # requires the whole ancestor chain (incl. this top-level widget itself)
    # to be shown — qtbot.addWidget() alone registers for cleanup, it does
    # not show() the widget.

    qtbot.waitUntil(lambda: service.current.called, timeout=2000)
    qtbot.waitUntil(lambda: panel._unavailable_label.isVisible(), timeout=2000)
    assert not panel._content.isVisible()
    assert panel._unavailable_label.text() == "Weather unavailable"


def test_shows_real_data_once_a_snapshot_arrives(qtbot):
    service = MagicMock()
    service.current.return_value = _snapshot()

    panel = MinieWeatherPanel(service, _core_manager())
    qtbot.addWidget(panel)
    panel.show()

    qtbot.waitUntil(lambda: panel._content.isVisible(), timeout=2000)
    assert panel._temperature_label.text() == "28°C"
    assert panel._condition_label.text() == "Partly cloudy"
    assert panel._location_label.text() == "Chennai"
    assert not panel._unavailable_label.isVisible()


def test_forecast_row_is_capped_at_four_chips(qtbot):
    service = MagicMock()
    service.current.return_value = _snapshot(forecast_count=5)

    panel = MinieWeatherPanel(service, _core_manager())
    qtbot.addWidget(panel)
    panel.show()

    qtbot.waitUntil(lambda: panel._content.isVisible(), timeout=2000)
    # 4 chips + one addStretch() item = 5 layout items.
    assert panel._forecast_row.count() == 5


def test_refresh_survives_a_raising_weather_service(qtbot):
    service = MagicMock()
    service.current.side_effect = RuntimeError("boom")

    panel = MinieWeatherPanel(service, _core_manager())  # construction calls refresh() once
    qtbot.addWidget(panel)
    panel.show()

    qtbot.waitUntil(lambda: service.current.called, timeout=2000)
    panel.refresh()  # must not raise on a later call either
    qtbot.waitUntil(lambda: panel._unavailable_label.isVisible(), timeout=2000)


def test_dedicated_refresh_timer_uses_the_five_minute_interval_not_the_shared_cadence(qtbot):
    core_manager = _core_manager()
    service = MagicMock()
    service.current.return_value = None

    panel = MinieWeatherPanel(service, core_manager)
    qtbot.addWidget(panel)

    assert panel._timer.interval() == 300_000
    core_manager.ui_config.assert_not_called()
