"""MinieMusicPanel — Minie Persona UI workstream.

The reference image's own "Minie's Vibe" music card: an artwork
placeholder, a title/subtitle pair, prev/play-pause/next controls, and a
small decorative waveform. No real music backend exists anywhere in this
codebase — no OS media-session integration, no Spotify API, nothing —
and building one is explicitly out of scope for this round.

This module instead defines the clean extension seam a real backend
would plug into later: `MusicController` (a minimal Protocol),
`MusicTrack` (the small display-only dataclass it hands back), and
`NullMusicController` — a real, concrete, always-inert implementation
mirroring `presentation/avatar_renderer_registry.py`'s own
`NullAvatarRenderer` precedent exactly: every method is a safe, logged
no-op (the three action methods) or an honest empty default
(`is_playing()` False, `current_track()` None). `MinieMusicPanel`
defaults to `NullMusicController()` when constructed with no controller,
so it can be dropped into a shell today, well before any real backend
exists, and shows an honest "Not playing" state rather than fabricated
data.

**No fabricated waveform**: the small bar graphic is a static "off" look
by default — there is no real audio signal anywhere in this codebase to
drive it — and only animates (a simple, tasteful bar-rotation, not a
fake amplitude simulation) while `controller.is_playing()` reports True.
"""

from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from presentation import minie_theme
from ui.minie.widgets.glass_panel import GlassPanel

logger = get_logger(__name__)

_ARTWORK_SIZE = 96
_WAVEFORM_TICK_MS = 220
_WAVEFORM_BAR_HEIGHTS = (0.3, 0.6, 0.4, 0.85, 0.5)
"""A small static base pattern for the decorative waveform — used as-is
while idle, and cycled through (a simple rotation, not fake amplitude
data) while playing. See this module's own docstring."""


@dataclass
class MusicTrack:
    title: str
    subtitle: str


class MusicController(Protocol):
    """A minimal contract, deliberately kept small — mirrors
    services/weather_service.py's own WeatherService Protocol precedent
    ("a single-method contract, deliberately minimal"), extended here to
    the handful of methods a music card genuinely needs. Every method's
    implied contract is to be fast/non-blocking: MinieMusicPanel calls
    the three action methods synchronously from the Qt main thread and
    immediately re-reads current_track()/is_playing() to refresh its own
    display — see MinieMusicPanel._dispatch()'s own docstring."""

    def is_playing(self) -> bool: ...

    def current_track(self) -> MusicTrack | None: ...

    def play_pause(self) -> None: ...

    def next_track(self) -> None: ...

    def previous_track(self) -> None: ...


class NullMusicController:
    """Real, concrete, always-inert MusicController — mirrors
    presentation/avatar_renderer_registry.py's own NullAvatarRenderer
    precedent exactly: every method is a safe, logged no-op. The default
    MinieMusicPanel constructs when given no real controller."""

    def is_playing(self) -> bool:
        return False

    def current_track(self) -> MusicTrack | None:
        return None

    def play_pause(self) -> None:
        logger.info("NullMusicController.play_pause() — no real music backend available.")

    def next_track(self) -> None:
        logger.info("NullMusicController.next_track() — no real music backend available.")

    def previous_track(self) -> None:
        logger.info("NullMusicController.previous_track() — no real music backend available.")


def _circular_button(glyph: str) -> QPushButton:
    button = QPushButton(glyph)
    button.setFixedSize(32, 32)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        f"QPushButton {{ border-radius: 16px; border: 1px solid {minie_theme.BORDER_DIM};"
        f" background-color: {minie_theme.BG_PANEL_RAISED};"
        f" color: {minie_theme.TEXT_PRIMARY}; padding: 0px; }}"
        f"QPushButton:hover {{ border: 1px solid {minie_theme.BORDER_ACCENT};"
        f" color: {minie_theme.BORDER_ACCENT}; }}"
    )
    return button


class _ArtworkPlaceholder(QWidget):
    """A soft gradient rounded square standing in for real album art —
    honest since no real artwork source exists anywhere in this
    codebase (see this module's own docstring); never a fabricated
    image."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_ARTWORK_SIZE, _ARTWORK_SIZE)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor(minie_theme.BG_PANEL_RAISED))
        gradient.setColorAt(1.0, QColor(minie_theme.SECONDARY_ACCENT))
        painter.setPen(QPen(QColor(minie_theme.BORDER_DIM), 1))
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 14, 14)
        painter.end()


class _Waveform(QWidget):
    """A small decorative bar row — static (an honest "off" look) unless
    the controller reports is_playing()=True, in which case a simple bar
    rotation runs. Never fabricates real amplitude data (see this
    module's own docstring)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(24)
        self._phase = 0
        self._playing = False

    def set_playing(self, playing: bool) -> None:
        if playing != self._playing:
            self._playing = playing
            self.update()

    def advance(self) -> None:
        if not self._playing:
            return
        self._phase = (self._phase + 1) % len(_WAVEFORM_BAR_HEIGHTS)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(minie_theme.BORDER_ACCENT if self._playing else minie_theme.TEXT_DIM)
        pen = QPen(color)
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        rect = self.rect()
        bar_count = len(_WAVEFORM_BAR_HEIGHTS)
        spacing = rect.width() / bar_count
        mid_y = rect.height() / 2.0
        for index in range(bar_count):
            source_index = (index + self._phase) % bar_count if self._playing else index
            factor = _WAVEFORM_BAR_HEIGHTS[source_index]
            half_height = max(2.0, (rect.height() / 2.0) * factor)
            x = spacing * (index + 0.5)
            painter.drawLine(QPointF(x, mid_y - half_height), QPointF(x, mid_y + half_height))
        painter.end()


class MinieMusicPanel(QWidget):
    """Constructor DI: (controller, parent) — controller defaults to
    NullMusicController() when None (see this module's own docstring)."""

    def __init__(
        self, controller: MusicController | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller: MusicController = (
            controller if controller is not None else NullMusicController()
        )

        self._panel = GlassPanel(self)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self._panel)

        header_label = QLabel("Minie's Vibe")
        header_label.setStyleSheet(
            f"color: {minie_theme.TEXT_PRIMARY}; font-size: 11pt; font-weight: 700; border: none;"
        )

        self._artwork = _ArtworkPlaceholder()

        self._title_label = QLabel()
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet(
            f"color: {minie_theme.TEXT_PRIMARY}; font-weight: 700; border: none;"
        )
        self._subtitle_label = QLabel()
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setStyleSheet(
            f"color: {minie_theme.TEXT_SECONDARY}; font-size: 9pt; border: none;"
        )
        track_info_layout = QVBoxLayout()
        track_info_layout.setContentsMargins(0, 0, 0, 0)
        track_info_layout.addWidget(self._title_label)
        track_info_layout.addWidget(self._subtitle_label)
        track_info_layout.addStretch(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        top_row.addWidget(self._artwork)
        top_row.addLayout(track_info_layout, 1)

        self._waveform = _Waveform()

        self._prev_button = _circular_button("⏮")
        self._play_pause_button = _circular_button("▶")
        self._next_button = _circular_button("⏭")
        self._prev_button.clicked.connect(self._on_previous_clicked)
        self._play_pause_button.clicked.connect(self._on_play_pause_clicked)
        self._next_button.clicked.connect(self._on_next_clicked)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)
        controls_row.addStretch(1)
        controls_row.addWidget(self._prev_button)
        controls_row.addWidget(self._play_pause_button)
        controls_row.addWidget(self._next_button)
        controls_row.addStretch(1)

        self._panel.layout_().addWidget(header_label)
        self._panel.layout_().addLayout(top_row)
        self._panel.layout_().addWidget(self._waveform)
        self._panel.layout_().addLayout(controls_row)

        self._timer = QTimer(self)
        self._timer.setInterval(_WAVEFORM_TICK_MS)
        self._timer.timeout.connect(self._waveform.advance)
        self._timer.start()

        self._refresh_display()

    def _on_previous_clicked(self) -> None:
        self._dispatch(self._controller.previous_track)

    def _on_play_pause_clicked(self) -> None:
        self._dispatch(self._controller.play_pause)

    def _on_next_clicked(self) -> None:
        self._dispatch(self._controller.next_track)

    def _dispatch(self, action) -> None:
        """Called synchronously on the Qt main thread, then immediately
        re-reads controller state to refresh the display — no async
        marshaling needed, since every MusicController implementation
        (real or Null) is required by this Protocol's own implied
        contract to be fast/non-blocking (see MusicController's own
        docstring)."""
        try:
            action()
        except Exception:
            logger.exception("MinieMusicPanel failed to dispatch a control action.")
        self._refresh_display()

    def _refresh_display(self) -> None:
        try:
            track = self._controller.current_track()
            playing = self._controller.is_playing()
        except Exception:
            logger.exception("MinieMusicPanel failed to read controller state.")
            track = None
            playing = False

        if track is None:
            self._title_label.setText("Not playing")
            self._subtitle_label.setText("Connect a music source to vibe together ♡")
        else:
            self._title_label.setText(track.title)
            self._subtitle_label.setText(track.subtitle)

        self._play_pause_button.setText("⏸" if playing else "▶")
        self._waveform.set_playing(playing)
