"""TopBar — JARVIS Holographic HUD reskin, Phase 2.

Combines the brief's "Top-Left Branding" and "Top Information Bar"
sections into one widget, since both live inside HudShell's
top_bar_zone: branding ("JARVIS" + subtitle) on the left, a live
clock/date block and a time-of-day greeting block on the right — every
value real and live, never a hardcoded example (section 7's own
explicit requirement: "The actual values must come from the system. Do
NOT hard-code example values.").

**Phase 6** adds the brief's own top-right Voice Interaction Indicator
(`VoiceVisualizer`) as a fourth column, after the greeting block.
"""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation import theme
from ui.jarvis.voice_visualizer import VoiceVisualizer
from voice.session_manager import VoiceSessionManager

logger = get_logger(__name__)

_CLOCK_INTERVAL_MS = 1000
"""A plain QLabel text update, not a repaint-heavy widget — a 1Hz
interval is cheap enough to need no config field of its own, the same
"a short literal is fine for genuinely cheap work" judgment this
project's own status-refresh timers already exercise for costlier reads."""


def _greeting_for_hour(hour: int) -> str:
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    return "Good evening"


class TopBar(QWidget):
    """Constructor DI: only CoreManager — ui_config().user_display_name
    is this widget's one real data need, read through the same narrow
    ui_config() accessor (not the broader config()) StatusPanel/
    RuntimeDiagnosticsPanel already use, preserving the documented "UI
    layer only needs CoreManager's UI-relevant slice" boundary
    core_manager.py's own ui_config() docstring establishes."""

    def __init__(
        self,
        core_manager: CoreManager,
        session_manager: VoiceSessionManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._core_manager = core_manager

        title = QLabel("JARVIS")
        title_font = QFont(theme.FONT_FAMILY)
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {theme.ACCENT_CYAN};")

        subtitle = QLabel("JUST A RATHER VERY INTELLIGENT SYSTEM")
        subtitle_font = QFont(theme.FONT_FAMILY)
        subtitle_font.setPointSize(8)
        subtitle_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        subtitle.setFont(subtitle_font)
        subtitle.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")

        branding = QVBoxLayout()
        branding.setSpacing(0)
        branding.addWidget(title)
        branding.addWidget(subtitle)

        self._clock_label = QLabel()
        clock_font = QFont(theme.FONT_FAMILY_MONO)
        clock_font.setPointSize(16)
        self._clock_label.setFont(clock_font)
        self._clock_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        self._clock_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._date_label = QLabel()
        self._date_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        clock_column = QVBoxLayout()
        clock_column.setSpacing(0)
        clock_column.addWidget(self._clock_label)
        clock_column.addWidget(self._date_label)

        self._greeting_label = QLabel()
        greeting_font = QFont(theme.FONT_FAMILY)
        greeting_font.setPointSize(11)
        greeting_font.setBold(True)
        self._greeting_label.setFont(greeting_font)
        self._greeting_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        self._greeting_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._subgreeting_label = QLabel("How can I assist you today?")
        self._subgreeting_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        self._subgreeting_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        greeting_column = QVBoxLayout()
        greeting_column.setSpacing(0)
        greeting_column.addWidget(self._greeting_label)
        greeting_column.addWidget(self._subgreeting_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(branding)
        layout.addStretch(1)
        layout.addLayout(clock_column)
        layout.addSpacing(28)
        layout.addLayout(greeting_column)
        layout.addSpacing(20)
        layout.addWidget(VoiceVisualizer(session_manager))

        self._timer = QTimer(self)
        self._timer.setInterval(_CLOCK_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Fail Gracefully, matching StatusPanel's own established shape:
        a transient CoreManager.ui_config() read failure keeps the last
        good greeting text (the clock/date themselves have no external
        dependency and always update) rather than crashing the recurring
        QTimer callback."""
        now = datetime.now()
        self._clock_label.setText(now.strftime("%I:%M:%S %p"))
        self._date_label.setText(now.strftime("%A, %d %B %Y").upper())

        try:
            display_name = self._core_manager.ui_config().user_display_name
        except Exception:
            logger.exception("Top bar greeting refresh failed to read config; keeping last name.")
            return
        name = (display_name or "there").upper()
        self._greeting_label.setText(f"{_greeting_for_hour(now.hour).upper()}, {name}")
