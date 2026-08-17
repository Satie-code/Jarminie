"""MinieAvatarStage — Minie Persona UI workstream.

The central "where Minie lives" region of the reference UI. This is the
single most architecturally sensitive widget in this workstream, so it
was written directly (not delegated) — see the workstream's own
resolved decision below.

**JARMINEI never embeds VTube Studio's live render in-app** — a
disclosed licensing/architecture boundary since Sprint 5.8
(presentation/vtube_studio_renderer.py's own docstring: "JARMINEI
neither embeds nor redistributes Live2D's own SDK, and does not itself
render Minie's avatar"). This workstream's own resolved decision (an
explicit AskUserQuestion answer, not an assumption) keeps that boundary
intact: this widget shows atmospheric glow/particles + an honest,
richer connection-status readout than presentation/minie_renderer.py's
existing plain-text `_MinieStatusWidget`, never a fake embedded avatar.
The user keeps VTube Studio's own real window open separately to see
Minie's live model.

**Avatar connection stays lazy** (brief section 26/7): this widget does
NOT call `avatar_renderer.mount()` on construction or on any timer —
the real connect-on-first-activation already happens through the
existing, untouched path (persona switch -> TransitionEngine ->
PresentationController.mount_renderer("minie") ->
presentation/minie_renderer.py's MinieRenderer.mount(), which itself
spawns a daemon thread so the ~4s VTube Studio handshake never blocks a
conversation turn). This widget only reads `is_connected()` (via
MinieUiStateAdapter's own polling) and offers a manual "Retry
connection" button for when the automatic attempt failed — clicking it
calls `avatar_renderer.mount()` again, on its OWN daemon thread (never
the Qt main thread — mount() genuinely blocks for several seconds on a
real connection attempt, the identical reason MinieRenderer.mount()
itself is thread-wrapped).

**Reads the raw AvatarRenderer directly, not through MinieRenderer**:
MinieRenderer (presentation/minie_renderer.py) holds its own
AvatarRenderer privately with no public accessor — by design, it only
exposes the narrow Renderer contract (mount/unmount/render_state/
trigger_gesture) plus its own status_widget(). Rather than widen that
class's own contract (out of scope, and unnecessary), main.py threads
the SAME AvatarRenderer instance it already constructs (before wrapping
it in MinieRenderer) to this widget as a separate constructor
parameter — the identical "one already-constructed collaborator handed
to two consumers" shape jarvis_renderer already has (both
PresentationHostWidget and, separately, HudShell's own AnimationManager
wiring).
"""

import math
import random
import threading
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QRadialGradient
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation import minie_theme
from presentation.avatar_renderer import AvatarRenderer
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from voice.session_manager import SessionState

logger = get_logger(__name__)

_TICK_MS = 50
_MAX_PARTICLES = 14
"""A small, bounded, pre-allocated particle pool — section 25's own
"no unbounded particle lists" mandate, the same discipline
presentation/widgets/particle_field_widget.py's own ParticleFieldWidget
already established for Jarvis. Only how many of them are currently
visible (driven by PresentationState.particle_density) changes."""

_UNAVAILABLE_TEXT = "Minie avatar unavailable — open VTube Studio to see her live."


@dataclass
class _Particle:
    """A single floating "heart/light" particle — drifts slowly upward
    (unlike Jarvis's own orbiting ParticleFieldWidget particles), the
    warmer/softer motion the brief's own "floating hearts occasionally"
    language calls for. x_fraction/y_fraction are 0.0-1.0 positions
    within this widget's own rect, not pixels — keeps motion correct
    across a resize without this widget needing to recompute anything."""

    x_fraction: float
    y_fraction: float
    speed: float
    size: float
    phase_offset: float

    def advance(self) -> None:
        self.y_fraction -= 0.0022 * self.speed
        if self.y_fraction < -0.05:
            self.y_fraction = 1.05


class MinieAvatarStage(QWidget):
    """Constructor DI: avatar_renderer (see this module's own docstring
    for why this is threaded in separately from MinieRenderer),
    ui_state_adapter (the shared poller — see that module's own
    docstring), core_manager (a one-time read of
    presentation_config().minie_lighting_color at construction, mirroring
    the "persona-identity-locked, one-time read" precedent the Jarvis
    reskin's own Phase 9 established)."""

    def __init__(
        self,
        avatar_renderer: AvatarRenderer,
        ui_state_adapter: MinieUiStateAdapter,
        core_manager: CoreManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._avatar_renderer = avatar_renderer
        self.setMinimumSize(280, 320)

        self._connected = False
        self._particle_density = 0.3
        self._glow_intensity = 1.0
        self._retry_cooldown_ms = 5000

        self._glow_color = QColor(minie_theme.GLOW_DEFAULT)
        try:
            self._glow_color = QColor(core_manager.presentation_config().minie_lighting_color)
            self._retry_cooldown_ms = core_manager.ui_config().status_refresh_interval_ms + 2000
        except Exception:
            logger.exception(
                "MinieAvatarStage failed to read presentation/UI config at construction; "
                "using defaults."
            )

        rng = random.Random(7331)
        self._particles = [
            _Particle(
                x_fraction=rng.uniform(0.15, 0.85),
                y_fraction=rng.uniform(0.0, 1.0),
                speed=rng.uniform(0.5, 1.4),
                size=rng.uniform(3.0, 7.0),
                phase_offset=rng.uniform(0.0, 2 * math.pi),
            )
            for _ in range(_MAX_PARTICLES)
        ]

        self._status_label = QLabel(_UNAVAILABLE_TEXT)
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            f"color: {minie_theme.TEXT_SECONDARY}; background: transparent;"
        )
        self._retry_button = QPushButton("Retry connection")
        self._retry_button.clicked.connect(self._on_retry_clicked)

        overlay_layout = QVBoxLayout(self)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addStretch(2)
        overlay_layout.addWidget(self._status_label)
        overlay_layout.addWidget(self._retry_button, 0, Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addStretch(1)
        self._status_label.setVisible(False)
        self._retry_button.setVisible(False)

        ui_state_adapter.avatar_status_updated.connect(self._on_avatar_status_updated)
        ui_state_adapter.presentation_state_updated.connect(self._on_presentation_state_updated)
        ui_state_adapter.session_state_updated.connect(self._on_session_state_updated)

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _on_avatar_status_updated(self, connected: bool) -> None:
        self._connected = connected
        self._status_label.setVisible(not connected)
        self._retry_button.setVisible(not connected)
        self.update()

    def _on_presentation_state_updated(self, state: object) -> None:
        """state is a presentation.presentation_state.PresentationState
        or None (see MinieUiStateAdapter's own docstring) — untyped here
        to avoid this widget importing a class only used for two
        attribute reads."""
        if state is None:
            return
        try:
            self._particle_density = max(0.0, min(1.0, state.particle_density))
            if state.lighting_color:
                self._glow_color = QColor(state.lighting_color)
        except Exception:
            logger.exception("MinieAvatarStage failed to apply a presentation state update.")

    def _on_session_state_updated(self, session_state: object) -> None:
        """A subtle glow-intensity bump per section 9's own per-state
        language ("speaking: increase glow intensity slightly... small
        animated indicator... listening: gentle pulse") — never a
        dramatic change, this stays a soft multiplier on the same
        radial gradient already drawn every frame."""
        if session_state is SessionState.SPEAKING:
            self._glow_intensity = 1.35
        elif session_state is SessionState.LISTENING:
            self._glow_intensity = 1.2
        elif session_state in (SessionState.PROCESSING, SessionState.AWAITING_NEXT_TURN):
            self._glow_intensity = 1.1
        else:
            self._glow_intensity = 1.0

    def _on_retry_clicked(self) -> None:
        self._retry_button.setEnabled(False)
        thread = threading.Thread(
            target=self._retry_mount, name="minie-avatar-stage-retry", daemon=True
        )
        thread.start()
        # The 3-arg form (msec, receiver, slot) ties this one-shot timer to
        # `self`'s own lifetime -- Qt silently skips the callback if `self`
        # is destroyed first, the identical safety net
        # ui/jarvis/command_bar.py's own QTimer.singleShot(0, self, ...)
        # marshal already relies on. The 2-arg form (no receiver) has no
        # such guard and was found, via a real test failure, to crash with
        # "C++ object already deleted" when this widget is torn down
        # before the cooldown elapses.
        QTimer.singleShot(
            self._retry_cooldown_ms, self, lambda: self._retry_button.setEnabled(True)
        )

    def _retry_mount(self) -> None:
        """Runs on a background thread — avatar_renderer.mount() already
        never raises (every AvatarRenderer implementation's own
        contract), but this is still wrapped defensively per this
        codebase's own "an uncaught exception on a bare thread vanishes
        silently otherwise" precedent (ui/jarvis/command_bar.py's
        _run_submit_text() docstring)."""
        try:
            self._avatar_renderer.mount()
        except Exception:
            logger.exception("MinieAvatarStage retry connection attempt failed unexpectedly.")

    def _on_tick(self) -> None:
        """Per-tick exception guarding — the same discipline
        presentation/widgets/particle_field_widget.py's own _on_tick()
        already established: a single bad tick is caught and logged,
        the last-painted frame is retained rather than crashing the
        recurring QTimer callback."""
        try:
            visible_count = round(self._particle_density * _MAX_PARTICLES)
            for particle in self._particles[:visible_count]:
                particle.advance()
            self.update()
        except Exception:
            logger.exception("MinieAvatarStage tick failed; retaining last-painted frame.")

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        center = QPointF(rect.center())
        radius = min(rect.width(), rect.height()) * 0.42 * self._glow_intensity
        if radius <= 0:
            painter.end()
            return

        gradient = QRadialGradient(center, radius)
        glow = QColor(self._glow_color)
        glow.setAlphaF(0.55)
        edge = QColor(self._glow_color)
        edge.setAlphaF(0.0)
        gradient.setColorAt(0.0, glow)
        gradient.setColorAt(1.0, edge)
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius, radius)

        # An honest, abstract placeholder for "Minie is here" — never a
        # literal rectangular photo/portrait (this module's own docstring
        # explains why no real in-app render exists at all).
        silhouette_radius = radius * 0.55
        silhouette_color = QColor(minie_theme.BG_PANEL_RAISED)
        silhouette_color.setAlphaF(0.75 if self._connected else 0.4)
        painter.setBrush(silhouette_color)
        painter.drawEllipse(center, silhouette_radius, silhouette_radius)

        glyph_font = QFont(minie_theme.FONT_FAMILY)
        glyph_font.setPointSize(26)
        painter.setFont(glyph_font)
        painter.setPen(QColor(self._glow_color))
        glyph_rect = QRectF(
            center.x() - silhouette_radius,
            center.y() - silhouette_radius,
            silhouette_radius * 2,
            silhouette_radius * 2,
        )
        glyph_text = "♡" if self._connected else "…"
        painter.drawText(glyph_rect, int(Qt.AlignmentFlag.AlignCenter), glyph_text)

        visible_count = round(self._particle_density * _MAX_PARTICLES)
        painter.setPen(Qt.PenStyle.NoPen)
        for particle in self._particles[:visible_count]:
            twinkle = 0.4 + 0.6 * (
                0.5 + 0.5 * math.sin(particle.y_fraction * 6.0 + particle.phase_offset)
            )
            fade_near_edges = 1.0 - min(1.0, abs(particle.y_fraction - 0.5) * 1.4)
            color = QColor(self._glow_color)
            color.setAlphaF(max(0.0, min(1.0, twinkle * fade_near_edges)))
            painter.setBrush(color)
            x = rect.width() * particle.x_fraction
            y = rect.height() * particle.y_fraction
            painter.drawEllipse(QPointF(x, y), particle.size / 2.0, particle.size / 2.0)

        painter.end()
