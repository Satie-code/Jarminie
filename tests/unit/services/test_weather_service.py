"""Unit tests for services.weather_service.

requests.get is mocked in every test — matching this project's own
established "mock the external library call at the boundary" precedent
(tests/unit/internet/test_brave_search_provider.py's identical shape).
No opt-in real-network test exists here (unlike Brave's own
opt-in/real section) since Open-Meteo needs no API key at all — a real
verification would always run, which is not this test file's call to
make unilaterally; the mocked coverage below is sufficient to prove the
parsing/caching/gating logic is correct.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from config.schema import InternetConfig, WeatherConfig
from services.weather_service import (
    NullWeatherService,
    OpenMeteoWeatherService,
    UnknownWeatherProviderError,
    create_weather_service,
)


def _fake_response(json_payload: dict, status_ok: bool = True) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_payload
    if status_ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return response


_OPEN_METEO_PAYLOAD = {
    "current": {"temperature_2m": 28.0, "weather_code": 2},
    "daily": {
        "time": ["2026-08-08", "2026-08-09", "2026-08-10", "2026-08-11", "2026-08-12"],
        "temperature_2m_max": [29.0, 30.0, 29.0, 28.0, 27.0],
        "temperature_2m_min": [21.0, 22.0, 21.0, 20.0, 19.0],
        "weather_code": [2, 1, 3, 3, 61],
    },
}


# --- create_weather_service() gating -----------------------------------------------------


def test_create_returns_null_service_when_internet_disabled():
    weather_config = WeatherConfig(latitude=28.4, longitude=77.0)
    internet_config = InternetConfig(enabled=False)

    service = create_weather_service(weather_config, internet_config)

    assert isinstance(service, NullWeatherService)


def test_create_returns_null_service_when_weather_disabled():
    weather_config = WeatherConfig(enabled=False, latitude=28.4, longitude=77.0)
    internet_config = InternetConfig(enabled=True)

    service = create_weather_service(weather_config, internet_config)

    assert isinstance(service, NullWeatherService)


def test_create_returns_null_service_when_location_unconfigured():
    weather_config = WeatherConfig(latitude=None, longitude=None)
    internet_config = InternetConfig(enabled=True)

    service = create_weather_service(weather_config, internet_config)

    assert isinstance(service, NullWeatherService)


def test_create_returns_open_meteo_service_when_fully_configured():
    weather_config = WeatherConfig(latitude=28.4, longitude=77.0, provider="open_meteo")
    internet_config = InternetConfig(enabled=True)

    service = create_weather_service(weather_config, internet_config)

    assert isinstance(service, OpenMeteoWeatherService)


def test_create_raises_for_unknown_provider():
    weather_config = WeatherConfig(latitude=28.4, longitude=77.0, provider="not-a-real-provider")
    internet_config = InternetConfig(enabled=True)

    with pytest.raises(UnknownWeatherProviderError, match="not-a-real-provider"):
        create_weather_service(weather_config, internet_config)


def test_null_weather_service_current_is_always_none():
    assert NullWeatherService().current() is None


# --- OpenMeteoWeatherService.current() happy path ----------------------------------------


def test_current_parses_a_real_shaped_response():
    service = OpenMeteoWeatherService(WeatherConfig(latitude=28.4, longitude=77.0))

    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_OPEN_METEO_PAYLOAD)
        snapshot = service.current()

    assert snapshot is not None
    assert snapshot.temperature_c == 28.0
    assert snapshot.condition_text == "Partly cloudy"
    assert snapshot.high_c == 29.0
    assert snapshot.low_c == 21.0
    assert [day.day_label for day in snapshot.forecast] == ["Sun", "Mon", "Tue", "Wed"]
    assert snapshot.forecast[0].high_c == 30.0
    assert snapshot.forecast[0].condition_text == "Mostly clear"


def test_current_sends_the_correct_request_shape():
    service = OpenMeteoWeatherService(
        WeatherConfig(latitude=28.4, longitude=77.0, request_timeout_seconds=7.0)
    )

    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_OPEN_METEO_PAYLOAD)
        service.current()

    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.open-meteo.com/v1/forecast"
    assert kwargs["params"]["latitude"] == 28.4
    assert kwargs["params"]["longitude"] == 77.0
    assert kwargs["timeout"] == 7.0


def test_current_returns_none_without_configured_coordinates():
    service = OpenMeteoWeatherService(WeatherConfig(latitude=None, longitude=None))

    with patch("requests.get") as mock_get:
        result = service.current()

    mock_get.assert_not_called()
    assert result is None


# --- OpenMeteoWeatherService.current() failure handling -----------------------------------


def test_current_returns_none_on_connection_error():
    service = OpenMeteoWeatherService(WeatherConfig(latitude=28.4, longitude=77.0))
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("no route")):
        assert service.current() is None


def test_current_returns_none_on_timeout():
    service = OpenMeteoWeatherService(WeatherConfig(latitude=28.4, longitude=77.0))
    with patch("requests.get", side_effect=requests.exceptions.Timeout("too slow")):
        assert service.current() is None


def test_current_returns_none_on_non_2xx_response():
    service = OpenMeteoWeatherService(WeatherConfig(latitude=28.4, longitude=77.0))
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response({}, status_ok=False)
        assert service.current() is None


def test_current_returns_none_on_malformed_payload():
    service = OpenMeteoWeatherService(WeatherConfig(latitude=28.4, longitude=77.0))
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response({"unexpected": "shape"})
        assert service.current() is None


# --- caching ------------------------------------------------------------------------------


def test_current_uses_cache_within_ttl():
    service = OpenMeteoWeatherService(
        WeatherConfig(latitude=28.4, longitude=77.0, cache_ttl_seconds=1800.0)
    )
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_OPEN_METEO_PAYLOAD)
        first = service.current()
        second = service.current()

    assert mock_get.call_count == 1
    assert first is second


def test_current_refetches_after_cache_expires():
    service = OpenMeteoWeatherService(
        WeatherConfig(latitude=28.4, longitude=77.0, cache_ttl_seconds=1800.0)
    )
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_OPEN_METEO_PAYLOAD)
        service.current()
        service._cached_at -= 2000.0  # force the cached reading to look stale
        service.current()

    assert mock_get.call_count == 2


def test_unknown_weather_code_degrades_to_unknown_condition_text():
    payload = {
        "current": {"temperature_2m": 28.0, "weather_code": 9999},
        "daily": {
            "time": ["2026-08-08"],
            "temperature_2m_max": [29.0],
            "temperature_2m_min": [21.0],
            "weather_code": [9999],
        },
    }
    service = OpenMeteoWeatherService(WeatherConfig(latitude=28.4, longitude=77.0))
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(payload)
        snapshot = service.current()

    assert snapshot.condition_text == "Unknown"
