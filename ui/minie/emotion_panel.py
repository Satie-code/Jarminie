"""MinieEmotionPanel — Minie Persona UI workstream.

The reference image's own "♡ Minie's Emotion" panel — four labeled,
animated bars (Happiness, Calmness, Trust, Affection) driven entirely by
`MinieUiStateAdapter.emotion_updated`
(`presentation.minie_emotion_adapter.MinieDisplayEmotions`). This file
holds no emotion-derivation logic of its own — that already lives in
minie_emotion_adapter.py, per this workstream's "the only new emotion
code is a presentation adapter, never a second emotion engine" decision
(see that module's own docstring); this panel is purely a display.

Bars start at 0.0 (EmotionBar's own construction-time default) and stay
there until the first real emotion_updated signal arrives — an honest
"no read yet" starting point, not a fabricated neutral guess. Unlike
EmotionalState's own documented neutral-midpoint-at-construction
philosophy (emotion/state_manager.py), these are pure UI display bars
with no state of their own to default meaningfully, so 0 is simpler and
equally honest here.
"""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation import minie_theme
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from ui.minie.widgets.emotion_bar import EmotionBar
from ui.minie.widgets.glass_panel import GlassPanel

logger = get_logger(__name__)


class MinieEmotionPanel(QWidget):
    """Constructor DI: (ui_state_adapter, core_manager, parent).
    core_manager is read exactly once, at construction, for
    presentation_config().minie_ui_accent — the identity-locked accent
    color used for both the header label and all four EmotionBar
    instances, matching minie_theme.py's own "one-time construction-time
    read, not a polled value" precedent for this config field."""

    def __init__(
        self,
        ui_state_adapter: MinieUiStateAdapter,
        core_manager: CoreManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        try:
            accent_color = core_manager.presentation_config().minie_ui_accent
        except Exception:
            logger.exception(
                "MinieEmotionPanel failed to read minie_ui_accent; using the default accent."
            )
            accent_color = minie_theme.PRIMARY_ACCENT_DEFAULT

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self._panel = GlassPanel(self)
        outer_layout.addWidget(self._panel)

        header = QLabel("♡ Minie's Emotion")
        header.setStyleSheet(f"color: {accent_color}; font-weight: 600;")
        self._panel.layout_().addWidget(header)

        self._happiness_bar = EmotionBar("Happiness", accent_color, self._panel)
        self._calmness_bar = EmotionBar("Calmness", accent_color, self._panel)
        self._trust_bar = EmotionBar("Trust", accent_color, self._panel)
        self._affection_bar = EmotionBar("Affection", accent_color, self._panel)
        for bar in (
            self._happiness_bar,
            self._calmness_bar,
            self._trust_bar,
            self._affection_bar,
        ):
            self._panel.layout_().addWidget(bar)

        ui_state_adapter.emotion_updated.connect(self._on_emotion_updated)

    def _on_emotion_updated(self, display_emotions: object) -> None:
        """Fail Gracefully: an unrecognized display_emotions shape
        (never expected in practice — MinieUiStateAdapter only ever
        emits a real MinieDisplayEmotions — but defensive regardless)
        leaves every bar at its last-known-good value rather than
        crashing the signal handler."""
        try:
            happiness = display_emotions.happiness
            calmness = display_emotions.calmness
            trust = display_emotions.trust
            affection = display_emotions.affection
        except Exception:
            logger.exception("MinieEmotionPanel received an unreadable emotion update.")
            return

        self._happiness_bar.set_value(happiness)
        self._calmness_bar.set_value(calmness)
        self._trust_bar.set_value(trust)
        self._affection_bar.set_value(affection)
