"""MinieUiStateAdapter — Minie Persona UI workstream.

One shared QTimer polling every backend source the Minie shell's panels
need, emitting Qt signals they subscribe to — mirrors
ui/jarvis/metrics_adapter.py's MetricsAdapter exactly, for the identical
reason that module's own docstring gives: several panels would
otherwise each poll the same handful of cheap backend reads on the same
cadence independently. There is no project-wide event bus (confirmed by
investigation before this workstream began) — polling is this
codebase's own established pattern for "backend state a UI needs to
observe," so this class follows it rather than inventing something new.

Four independent sources, each guarded separately (Fail Gracefully,
matching MetricsAdapter's own "each source guarded independently"
precedent — a failure reading one must never suppress the others):
- PresentationController.last_state_for("minie") — the most recently
  computed PresentationState for Minie (smile_intensity, particle_
  density, etc.), None until PresentationController.refresh() has run
  at least once for Minie (an honest gap, not an error — see that
  method's own docstring).
- EmotionalStateManager.current_state(), reshaped through
  presentation/minie_emotion_adapter.py's derive_display_emotions()
  into the four labeled bars ui/minie/emotion_panel.py shows.
- VoiceSessionManager.current_session_state() — the same SessionState
  enum ui/jarvis/voice_visualizer.py's VoiceVisualizer already polls.
- avatar_renderer.is_connected() — the real VTube Studio connection
  status. avatar_renderer is the same AvatarRenderer instance
  presentation/minie_renderer.py's MinieRenderer holds internally
  (main.py constructs it once and threads it to both) — reading
  is_connected() here needs no change to MinieRenderer itself, which
  exposes no public accessor for its own held AvatarRenderer.
"""

from PySide6.QtCore import QObject, QTimer, Signal

from core.logging_setup import get_logger
from core.manager import CoreManager
from emotion.state_manager import EmotionalStateManager
from presentation.avatar_renderer import AvatarRenderer
from presentation.minie_emotion_adapter import derive_display_emotions
from presentation.presentation_controller import PresentationController
from voice.session_manager import VoiceSessionManager

logger = get_logger(__name__)


class MinieUiStateAdapter(QObject):
    """Constructor DI: presentation_controller, emotional_state_manager,
    voice_session_manager, avatar_renderer, core_manager (only for its
    own ui_config().status_refresh_interval_ms — the same shared,
    already-tunable cadence every other polling widget in this codebase
    uses)."""

    presentation_state_updated = Signal(object)
    """Carries a PresentationState, or None (last_state_for() hasn't
    produced one for Minie yet)."""

    emotion_updated = Signal(object)
    """Carries a presentation.minie_emotion_adapter.MinieDisplayEmotions."""

    session_state_updated = Signal(object)
    """Carries a voice.session_manager.SessionState."""

    avatar_status_updated = Signal(bool)
    """True if the held AvatarRenderer reports a live VTube Studio
    connection."""

    def __init__(
        self,
        presentation_controller: PresentationController,
        emotional_state_manager: EmotionalStateManager,
        voice_session_manager: VoiceSessionManager,
        avatar_renderer: AvatarRenderer,
        core_manager: CoreManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._presentation_controller = presentation_controller
        self._emotional_state_manager = emotional_state_manager
        self._voice_session_manager = voice_session_manager
        self._avatar_renderer = avatar_renderer

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Fail Gracefully per source — a failure reading one must not
        suppress the others, the same shape MetricsAdapter.refresh()
        already established for its own two independent sources."""
        try:
            state = self._presentation_controller.last_state_for("minie")
        except Exception:
            logger.exception("MinieUiStateAdapter failed to read presentation state.")
        else:
            self.presentation_state_updated.emit(state)

        try:
            emotional_state = self._emotional_state_manager.current_state()
            display_emotions = derive_display_emotions(emotional_state)
        except Exception:
            logger.exception("MinieUiStateAdapter failed to read/derive emotion state.")
        else:
            self.emotion_updated.emit(display_emotions)

        try:
            session_state = self._voice_session_manager.current_session_state()
        except Exception:
            logger.exception("MinieUiStateAdapter failed to read voice session state.")
        else:
            self.session_state_updated.emit(session_state)

        try:
            connected = self._avatar_renderer.is_connected()
        except Exception:
            logger.exception("MinieUiStateAdapter failed to read avatar connection status.")
        else:
            self.avatar_status_updated.emit(connected)
