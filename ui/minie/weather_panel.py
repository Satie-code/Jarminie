"""MinieWeatherPanel — Minie Persona UI workstream.

The reference image's own weather card: a big current temperature,
condition text, the configured location name, and a row of small
day-chips (e.g. "Sat 29°") drawn from `services/weather_service.py`'s
`WeatherService`. No other panel in this workstream reads weather.

**Own dedicated refresh cadence, deliberately NOT the shared
`status_refresh_interval_ms`** (see `_WEATHER_REFRESH_INTERVAL_MS`
below): weather changes slowly — polling it every few seconds like
`MinieUiStateAdapter`'s cheap in-memory reads would be wasted background-
thread churn for no visible benefit, especially since `WeatherService.
current()` is a genuinely slow, real blocking HTTP call on a cache miss
(`OpenMeteoWeatherService`'s own docstring — up to
`request_timeout_seconds`, default 5s) that this panel must never run on
the Qt main thread. `WeatherService` already caches internally
(`cache_ttl_seconds`, default 30 minutes), so a 5-minute UI-side poll is
itself mostly cache hits — cheap, but still dispatched to a background
thread every time per the same "never call `.current()` from a Qt slot
directly" discipline that module's own Protocol docstring requires of
every caller.

**"Weather unavailable" is the ordinary default state, not an error**:
`WeatherService.current()` returns None whenever weather is disabled,
internet access is disabled, or no location has been configured yet
(`create_weather_service()`'s own docstring) — none of those are
failures this panel should alarm the user about.
"""

import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation import minie_theme
from services.weather_service import DayForecast, WeatherService, WeatherSnapshot
from ui.minie.widgets.glass_panel import GlassPanel

logger = get_logger(__name__)

_WEATHER_REFRESH_INTERVAL_MS = 300_000
"""5 minutes — deliberately NOT the shared `status_refresh_interval_ms`
(default 3000ms). Weather changes slowly and `.current()` can be a
genuinely slow blocking call, so polling it on that fast a cadence would
be wasted background-thread churn for no benefit, given `WeatherService`
already caches internally (see this module's own docstring)."""

_MAX_FORECAST_CHIPS = 4


class _ForecastChip(QWidget):
    """One compact "day / high temperature" pair in the forecast row —
    e.g. "Sat" over a small rounded "29°" pill. Purely presentational,
    rebuilt fresh on every refresh (see
    MinieWeatherPanel._apply_snapshot()) rather than updated in place —
    a real weather refresh is rare (see _WEATHER_REFRESH_INTERVAL_MS
    above), so recreating a handful of small QLabel widgets each time is
    cheap and keeps the update logic simple."""

    def __init__(self, day: DayForecast, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        day_label = QLabel(day.day_label)
        day_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        day_label.setStyleSheet(
            f"color: {minie_theme.TEXT_SECONDARY}; font-size: 8pt; border: none;"
        )

        temp_label = QLabel(f"{day.high_c:.0f}°")
        temp_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        # WA_StyledBackground is required for a plain QWidget's own QSS
        # background/border-radius rules to actually paint — the same
        # gotcha GlassPanel's own docstring documents finding via a real
        # screenshot; applied defensively here too since QLabel's default
        # background handling shouldn't be relied on for a rounded pill.
        temp_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        object_name = f"minie_weather_chip_pill_{id(temp_label)}"
        temp_label.setObjectName(object_name)
        temp_label.setStyleSheet(
            f"#{object_name} {{"
            f" background-color: {minie_theme.BG_PANEL_RAISED};"
            f" color: {minie_theme.TEXT_PRIMARY};"
            f" border-radius: 10px;"
            f" padding: 3px 8px;"
            f" font-size: 9pt;"
            f" }}"
        )

        layout.addWidget(day_label)
        layout.addWidget(temp_label)


class MinieWeatherPanel(QWidget):
    """Constructor DI: (weather_service, core_manager, parent).
    core_manager is accepted for constructor-signature consistency with
    every other ui/minie panel that polls backend state, but is NOT
    consulted for this panel's own refresh cadence (see
    _WEATHER_REFRESH_INTERVAL_MS's own docstring) — kept so a future
    config-driven weather-refresh knob doesn't need a signature change."""

    def __init__(
        self,
        weather_service: WeatherService,
        core_manager: CoreManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._weather_service = weather_service
        self._core_manager = core_manager

        self._panel = GlassPanel(self)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self._panel)

        self._unavailable_label = QLabel("Weather unavailable")
        self._unavailable_label.setStyleSheet(
            f"color: {minie_theme.TEXT_SECONDARY}; border: none;"
        )

        self._temperature_label = QLabel("")
        self._temperature_label.setStyleSheet(
            f"color: {minie_theme.TEXT_PRIMARY}; font-size: 28pt; font-weight: 700; border: none;"
        )
        self._condition_label = QLabel("")
        self._condition_label.setStyleSheet(
            f"color: {minie_theme.TEXT_SECONDARY}; font-size: 10pt; border: none;"
        )
        self._location_label = QLabel("")
        self._location_label.setStyleSheet(
            f"color: {minie_theme.TEXT_DIM}; font-size: 8pt; border: none;"
        )

        self._forecast_row = QHBoxLayout()
        self._forecast_row.setSpacing(6)
        self._forecast_row.setContentsMargins(0, 6, 0, 0)
        forecast_container = QWidget()
        forecast_container.setLayout(self._forecast_row)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)
        content_layout.addWidget(self._temperature_label)
        content_layout.addWidget(self._condition_label)
        content_layout.addWidget(self._location_label)
        content_layout.addWidget(forecast_container)
        self._content.setVisible(False)

        self._panel.layout_().addWidget(self._unavailable_label)
        self._panel.layout_().addWidget(self._content)

        self._timer = QTimer(self)
        self._timer.setInterval(_WEATHER_REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Spawns a background thread per refresh — `.current()` is a
        real, potentially slow blocking HTTP call (see this module's own
        docstring) and must never run on the Qt main thread, the same
        threading.Thread(daemon=True) + QTimer.singleShot(0, ...) idiom
        ui/jarvis/command_bar.py's CommandBar already established."""
        thread = threading.Thread(
            target=self._run_fetch, name="minie-weather-panel-fetch", daemon=True
        )
        thread.start()

    def _run_fetch(self) -> None:
        """Runs on a background thread — weather_service.current() is
        documented to never raise, but this is still wrapped defensively
        since an uncaught exception on a bare threading.Thread would
        otherwise vanish silently rather than reaching this widget's own
        display update."""
        try:
            snapshot = self._weather_service.current()
        except Exception:
            logger.exception("MinieWeatherPanel failed to fetch weather unexpectedly.")
            snapshot = None
        QTimer.singleShot(0, self, lambda snapshot=snapshot: self._apply_snapshot(snapshot))

    def _apply_snapshot(self, snapshot: WeatherSnapshot | None) -> None:
        """Fail Gracefully: on a None snapshot the panel keeps showing
        "Weather unavailable" — the ordinary default state, not an error
        (see this module's own docstring) — rather than clearing
        whatever was last shown."""
        if snapshot is None:
            self._unavailable_label.setVisible(True)
            self._content.setVisible(False)
            return

        self._unavailable_label.setVisible(False)
        self._content.setVisible(True)
        self._temperature_label.setText(f"{snapshot.temperature_c:.0f}°C")
        self._condition_label.setText(snapshot.condition_text)
        self._location_label.setText(snapshot.location_name)

        while self._forecast_row.count():
            item = self._forecast_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for day in snapshot.forecast[:_MAX_FORECAST_CHIPS]:
            self._forecast_row.addWidget(_ForecastChip(day))
        self._forecast_row.addStretch(1)
