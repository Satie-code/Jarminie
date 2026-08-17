"""WeatherService — Minie Persona UI workstream.

Powers ui/minie/weather_panel.py's weather card. No other subsystem in
this codebase reads current weather; this is genuinely new capability,
not a duplicate of anything existing (confirmed by investigation before
this workstream began — no WeatherProvider/weather integration existed
anywhere in the repo).

**Provider choice**: Open-Meteo (https://open-meteo.com) — a free,
keyless weather API, chosen specifically so this feature never requires
a paid API or a committed secret, per the brief's own "do NOT introduce
an unnecessary paid API" instruction.

**Privacy/egress discipline**: create_weather_service() (below) is
gated by BOTH weather_config.enabled AND internet_config.enabled — the
project-wide outbound-request boundary Sprint 6.21's Privacy
Verification pass established for other outbound calls (search). No
location is ever guessed from IP/OS/network — WeatherConfig.latitude/
longitude default to None, and an unconfigured location degrades to
NullWeatherService, never a fabricated reading.

**Mirrors presentation/avatar_renderer_registry.py's own registry
pattern** exactly: a WeatherService Protocol, one real implementation
(OpenMeteoWeatherService), a NullWeatherService always-inert fallback,
and a small function-based registry (create_weather_service()) mapping
WeatherConfig.provider to a concrete class — adding a second provider
later takes exactly the two steps that module's own docstring
describes for a new avatar backend.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import requests

from config.schema import InternetConfig, WeatherConfig
from core.logging_setup import get_logger

logger = get_logger(__name__)

_OPEN_METEO_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
_FORECAST_DAYS = 5
"""Today (index 0, used for the current/high/low reading) plus four
more days — matches the reference UI's own four-day forecast row."""

# Open-Meteo's own WMO weather-code table, collapsed to the small set of
# human-readable condition labels weather_panel.py actually displays.
# See https://open-meteo.com/en/docs (WMO Weather interpretation codes).
_CONDITION_TEXT_BY_CODE: dict[int, str] = {
    0: "Clear sky",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}


def _condition_text(weather_code: int | None) -> str:
    if weather_code is None:
        return "Unknown"
    return _CONDITION_TEXT_BY_CODE.get(weather_code, "Unknown")


def _day_label(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%a")
    except ValueError:
        return iso_date


@dataclass
class DayForecast:
    day_label: str
    high_c: float
    low_c: float
    condition_text: str


@dataclass
class WeatherSnapshot:
    temperature_c: float
    condition_text: str
    high_c: float
    low_c: float
    location_name: str
    forecast: list[DayForecast]
    fetched_at: datetime


class WeatherService(Protocol):
    """A single-method contract, deliberately minimal — mirrors
    presentation/avatar_renderer.py's/internet/search_provider.py's own
    "kept deliberately minimal" precedent. current() is a synchronous,
    potentially slow call (a real HTTP request) — callers on the Qt
    main thread must run it on a background thread and marshal the
    result back, the same threading.Thread(daemon=True) +
    QTimer.singleShot(0, ...) idiom ui/jarvis/command_bar.py's
    CommandBar already established."""

    def current(self) -> WeatherSnapshot | None: ...


class NullWeatherService:
    """Real, concrete, always-inert WeatherService — mirrors
    presentation/avatar_renderer_registry.py's own NullAvatarRenderer
    precedent exactly. Returned by create_weather_service() whenever
    weather is disabled, internet access is disabled, or no location is
    configured (see that function's own docstring). current() always
    returns None (an honest "no data"), never raises."""

    def current(self) -> WeatherSnapshot | None:
        return None


class UnknownWeatherProviderError(Exception):
    """Raised when WeatherConfig.provider names a provider with no
    registered implementation — mirrors avatar_renderer_registry.py's
    UnknownAvatarBackendError exactly: a construction-time
    configuration error, deliberately loud, never caught/degraded."""


class OpenMeteoWeatherService:
    """WeatherService implementation against Open-Meteo. Holds no
    persistent connection — each real fetch is a single, independent
    HTTP request, the same "thin per-call HTTP wrapper" shape
    internet/brave_search_provider.py's BraveSearchProvider already
    established.

    A small in-memory cache (weather_config.cache_ttl_seconds, default
    30 minutes) avoids re-fetching every time the panel's own UI timer
    ticks — weather genuinely doesn't change minute to minute, so a
    reading up to cache_ttl_seconds stale is an acceptable, disclosed
    tradeoff, not a bug.

    Deliberately never raises — unlike BraveSearchProvider's own
    raise-on-failure contract, this class's only real consumer
    (ui/minie/weather_panel.py) needs exactly one thing: "do I have a
    snapshot right now, or not." current() degrades any failure
    (network, timeout, malformed payload) to None, logged, so the
    panel's own "Weather unavailable" state is the natural default
    rather than a special case every caller must remember to handle.
    """

    def __init__(self, weather_config: WeatherConfig) -> None:
        self._config = weather_config
        self._cached_snapshot: WeatherSnapshot | None = None
        self._cached_at: float | None = None

    def current(self) -> WeatherSnapshot | None:
        if self._config.latitude is None or self._config.longitude is None:
            return None

        if self._cached_snapshot is not None and self._cached_at is not None:
            age_seconds = time.monotonic() - self._cached_at
            if age_seconds < self._config.cache_ttl_seconds:
                return self._cached_snapshot

        snapshot = self._fetch()
        if snapshot is not None:
            self._cached_snapshot = snapshot
            self._cached_at = time.monotonic()
        return snapshot

    def _fetch(self) -> WeatherSnapshot | None:
        try:
            response = requests.get(
                _OPEN_METEO_ENDPOINT,
                params={
                    "latitude": self._config.latitude,
                    "longitude": self._config.longitude,
                    "current": "temperature_2m,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                    "timezone": "auto",
                    "forecast_days": _FORECAST_DAYS,
                },
                timeout=self._config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()

            current = payload.get("current") or {}
            daily = payload.get("daily") or {}
            days: list[str] = daily.get("time") or []
            highs: list[float] = daily.get("temperature_2m_max") or []
            lows: list[float] = daily.get("temperature_2m_min") or []
            codes: list[int] = daily.get("weather_code") or []

            forecast: list[DayForecast] = [
                DayForecast(
                    day_label=_day_label(days[index]),
                    high_c=highs[index],
                    low_c=lows[index],
                    condition_text=_condition_text(codes[index] if index < len(codes) else None),
                )
                for index in range(1, min(len(days), _FORECAST_DAYS))
            ]

            return WeatherSnapshot(
                temperature_c=current["temperature_2m"],
                condition_text=_condition_text(current.get("weather_code")),
                high_c=highs[0] if highs else current["temperature_2m"],
                low_c=lows[0] if lows else current["temperature_2m"],
                location_name=self._config.location_name or "Current location",
                forecast=forecast,
                fetched_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception("OpenMeteoWeatherService failed to fetch current weather.")
            return None


_BACKENDS: dict[str, Callable[[WeatherConfig], WeatherService]] = {
    "open_meteo": OpenMeteoWeatherService,
}


def create_weather_service(
    weather_config: WeatherConfig, internet_config: InternetConfig
) -> WeatherService:
    """Resolves WeatherConfig.provider into a real WeatherService —
    mirrors presentation/avatar_renderer_registry.py's
    create_avatar_renderer() exactly: the one place a config-driven
    backend name maps to a real class.

    Returns NullWeatherService (never raises) for two ordinary, expected
    cases, per WeatherConfig's own docstring:
    - internet_config.enabled is False, or weather_config.enabled is
      False — the project-wide outbound-request boundary Sprint 6.21's
      Privacy Verification pass established, respected here exactly
      like every other outbound call in this codebase.
    - weather_config.latitude/longitude is None (the shipped default,
      until a user configures a real location) — no location is ever
      guessed on the user's behalf.

    Raises UnknownWeatherProviderError (never a raw KeyError) only for a
    genuine configuration typo — weather_config.provider naming a
    provider with no registered implementation — naming every real,
    available option so it's immediately actionable.
    """
    if not internet_config.enabled or not weather_config.enabled:
        return NullWeatherService()
    if weather_config.latitude is None or weather_config.longitude is None:
        return NullWeatherService()

    try:
        backend_cls = _BACKENDS[weather_config.provider]
    except KeyError:
        raise UnknownWeatherProviderError(
            f"Unknown weather provider {weather_config.provider!r}. "
            f"Registered providers: {sorted(_BACKENDS)}."
        ) from None
    return backend_cls(weather_config)
