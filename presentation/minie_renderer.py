"""MinieRenderer (Sprint 5.8 — Level 5 Part A).

The `Renderer` (Sprint 5.6) `PresentationController` actually holds for
Minie — a thin adapter translating a `PresentationState` into
`AvatarRenderer` (this sprint's own narrower interface) calls, so
`PresentationController` never needs to know avatars exist as a
distinct concept from Jarvis's dashboard; it only ever calls the
three-method `Renderer` contract.

    PresentationController --(Renderer)--> MinieRenderer
        --(AvatarRenderer)--> VTubeStudioAvatarRenderer

`render_state()` does two things: (1) delegates straight to
`AvatarRenderer.render_state()` (the `PresentationConfig.
vtube_studio_parameter_mapping`-driven parameter-injection path,
handled entirely inside the held `AvatarRenderer`); (2) derives a
coarse `expression_id` from `state.smile_intensity`/`.voice_warmth` via
`_derive_expression_id()`'s own config-driven threshold table
(`PresentationConfig.minie_expression_thresholds`), calling
`AvatarRenderer.set_expression()` only when that derived id actually
changes from the last one sent — never every tick, avoiding flooding
the avatar backend with redundant identical calls.

`set_mouth_open()`/`set_eye_target()` have no real caller yet from this
class — lip-sync (Sprint 5.11, driven by real TTS audio timing) and
eye-tracking are later sprints' own jobs, not built here.
`trigger_gesture()` (Sprint 5.9) forwards its gesture_id verbatim to
the held AvatarRenderer — MinieRenderer itself makes no attempt to
interpret or remap it, matching this class's own "thin adapter"
contract; the real per-id meaning lives entirely inside whatever the
user's own loaded Live2D model defines.

**`status_widget()` (Sprint 5.14)**: Minie's real avatar renders inside
the separately-running VTube Studio window, per this module's own
"JARMINEI never renders Live2D itself" boundary — `PresentationHostWidget`
(Sprint 5.14) therefore cannot embed a live Minie visual the way it
embeds `JarvisRenderer.widget()`. `status_widget()` is the disclosed,
honest alternative: a small, live "Connected to VTube Studio" / "VTube
Studio not detected" widget, polling the held `AvatarRenderer.
is_connected()` — never a fake in-app avatar standing in for the real
one. `core_manager` (required, this sprint) is this widget's own
refresh-cadence source (`UIConfig.status_refresh_interval_ms`), the
identical `QTimer` pattern `ui/status_panel.py`'s `StatusPanel`/
`presentation/jarvis_renderer.py`'s `_SystemStatusPanel` already
established — added here as a real constructor parameter beyond this
class's own original Sprint 5.8 signature, the same "found a real gap,
resolved it directly, disclosed it here" precedent `JarvisRenderer`'s
own Sprint 5.12 `core_manager` addition already used.
"""

import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from config.schema import PresentationConfig
from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation.avatar_renderer import AvatarRenderer
from presentation.presentation_state import PresentationState

logger = get_logger(__name__)

_CONNECTED_TEXT = "Connected to VTube Studio"
_DISCONNECTED_TEXT = "VTube Studio not detected"


class _MinieStatusWidget(QWidget):
    """A small, honest, live connection-status readout — see this
    module's own docstring for why this exists instead of an in-app
    avatar render. Fail Gracefully: a transient is_connected() failure
    keeps the widget's last-known-good text rather than crashing the
    recurring QTimer callback, the same shape StatusPanel.refresh()/
    _SystemStatusPanel.refresh() already established."""

    def __init__(self, avatar_renderer: AvatarRenderer, core_manager: CoreManager) -> None:
        super().__init__()
        self._avatar = avatar_renderer
        self._label = QLabel()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Minie</b>"))
        layout.addWidget(self._label)

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        try:
            connected = self._avatar.is_connected()
        except Exception:
            logger.exception("Minie status widget refresh failed; keeping last displayed value.")
            return
        self._label.setText(_CONNECTED_TEXT if connected else _DISCONNECTED_TEXT)


def _derive_expression_id(state: PresentationState, thresholds: dict[str, float]) -> str:
    """A small, config-driven threshold lookup — never a hardcoded
    vocabulary (03_Engineering_Standards.md's own "no hardcoded...
    thresholds" rule, the same discipline personas/jarvis.py's/
    personas/minie.py's own _select_tone_variant() already established
    at Sprint 5.4). expressiveness blends both named signals
    (this sprint's own Expected Functions: "derives... from
    state.smile_intensity/voice_warmth") since neither alone is named
    as the sole driver. The highest-threshold entry the current reading
    meets wins; PresentationConfig._validate_presentation() guarantees
    a 0.0-threshold entry always exists as a reachable floor."""
    expressiveness = (state.smile_intensity + state.voice_warmth) / 2.0
    for expression_id, threshold in sorted(
        thresholds.items(), key=lambda item: item[1], reverse=True
    ):
        if expressiveness >= threshold:
            return expression_id
    return "neutral"  # unreachable given a validated config; an honest fallback, not a crash


class MinieRenderer:
    """Constructor DI per 03_Engineering_Standards.md: receives an
    AvatarRenderer instance (via presentation/avatar_renderer_registry.py's
    create_avatar_renderer(), not constructed internally), PresentationConfig,
    and core_manager (Sprint 5.14, required — status_widget()'s own real
    data source, see this module's own docstring). Implements Renderer
    (presentation/renderer.py) structurally (Protocol, no explicit
    inheritance needed)."""

    def __init__(
        self,
        avatar_renderer: AvatarRenderer,
        presentation_config: PresentationConfig,
        core_manager: CoreManager,
    ) -> None:
        self._avatar = avatar_renderer
        self._config = presentation_config
        self._core_manager = core_manager
        self._last_expression_id: str | None = None

    def status_widget(self) -> QWidget:
        """A fresh live connection-status widget — see this module's own
        docstring. Unlike JarvisRenderer.widget(), this is not cached:
        PresentationHostWidget (Sprint 5.14) calls this once when Minie
        becomes the mounted persona, embedding the returned widget for
        as long as it stays mounted."""
        return _MinieStatusWidget(self._avatar, self._core_manager)

    def mount(self) -> None:
        """Spawns a background daemon thread to call the held
        AvatarRenderer's own mount() and returns immediately — the
        identical "spawn and return immediately" precedent
        presentation/lip_sync.py's LipSyncDriver.drive_from_audio()
        already established (Sprint 5.11), applied here for the same
        underlying reason: a real, measured gap found during Sprint
        5.14's own integration testing. VTubeStudioAvatarRenderer.
        mount()'s own connect-and-authenticate attempt genuinely blocks
        for up to vtube_studio_connection_timeout_seconds (measured
        directly: ~4.1s against this project's own default when no
        VTube Studio instance is listening) — calling it synchronously
        from PresentationController.mount_renderer() (itself called
        synchronously from TransitionEngine._finish(), itself called
        from CommunicationPipeline's own live conversation-turn thread,
        Sprint 5.14's real new caller) would stall an entire spoken
        reply by that same amount on every persona switch to Minie
        whenever VTube Studio isn't running — the common, undriven case
        this project's own test suite runs under by default. Never
        raises (a daemon thread's own uncaught exception would only
        crash that thread, but VTubeStudioAvatarRenderer.mount() never
        raises to begin with — its own "disconnected, never crash"
        contract, Sprint 5.8)."""
        thread = threading.Thread(
            target=self._avatar.mount, name="minie-renderer-mount", daemon=True
        )
        thread.start()

    def unmount(self) -> None:
        self._avatar.unmount()
        # The avatar's own actual displayed expression is no longer
        # known to be current once unmounted — forget it so the first
        # render_state() after a remount always re-sends a fresh
        # set_expression() rather than potentially skipping it.
        self._last_expression_id = None

    def render_state(self, state: PresentationState) -> None:
        self._avatar.render_state(state)
        self._maybe_set_expression(state)

    def trigger_gesture(self, gesture_id: str) -> None:
        self._avatar.trigger_gesture(gesture_id)

    def _maybe_set_expression(self, state: PresentationState) -> None:
        expression_id = _derive_expression_id(state, self._config.minie_expression_thresholds)
        if expression_id == self._last_expression_id:
            return
        self._avatar.set_expression(expression_id)
        self._last_expression_id = expression_id
