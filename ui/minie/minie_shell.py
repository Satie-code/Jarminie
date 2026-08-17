"""MinieShell — Minie Persona UI workstream.

The composition root for Minie's warm, companion-style desktop shell —
the sibling to `ui/jarvis/hud_shell.py`'s own cold/technical `HudShell`.
Assembles every widget built across this workstream around the real,
already-constructed collaborators it receives via constructor DI, the
same "only main.py/MainWindow construct concrete instances" pattern
`HudShell` already established.

**Layout**: a two-column outer grid (a narrow `MinieSidebar` rail on the
left, everything else in a wide content column to its right) with a top
row for `MinieTopBar` (spanning both columns) and a bottom row pairing
`MinieStatusCard` (under the sidebar) with `MinieMessageBar` (under the
content column) — mirroring the reference image's own composition. The
content column itself is an inner three-way split (left/center/right,
stretch 3:5:2) rather than a third top-level grid column, since only the
"Home" page uses all three at once — every other nav item swaps the
WHOLE content column for a single "Coming soon" placeholder, the same
scope decision `ui/jarvis/hud_shell.py`'s own docstring documents for
Jarvis's Conversation/Memory/Tasks pages (only Dashboard is real there
too). Left/right columns are each wrapped in a borderless `QScrollArea`
— the identical Phase 10 fix `HudShell`'s own docstring documents
finding for a real smaller-laptop screen (~768px tall), applied
proactively here rather than waiting to rediscover the same overflow.

**Theming**: `self.setStyleSheet(minie_theme.build_minie_stylesheet(...))`
is called ONCE, on this widget itself, never on `QApplication` — see
`presentation/minie_theme.py`'s own docstring for why a second
app-wide theme call would clobber Jarvis's. `accent_color` is a
one-time read of `core_manager.presentation_config().minie_ui_accent`,
the same "persona-identity-locked, read once" precedent
`ui/jarvis/hud_shell.py`'s own Phase 9 established for
`jarvis_ui_accent`.

**Does NOT use `PresentationHostWidget`**: unlike `HudShell` (which
embeds it to host `JarvisRenderer.widget()`/`MinieRenderer.
status_widget()`), this shell drives its own `MinieAvatarStage` directly
off the same `AvatarRenderer` instance `main.py` already constructs
before wrapping it in `MinieRenderer` — a resolved architectural
decision from this workstream's own plan, kept so `presentation/
presentation_host_widget.py`'s existing Jarvis/Minie branch needs no
change and its own tests stay untouched.

**No heavy AI subsystem is touched by constructing this shell**: every
collaborator below (`CoreManager`, `AvatarRenderer`,
`PresentationController`, `EmotionalStateManager`, `VoiceSessionManager`,
`CalendarStore`, `CommunicationPipeline`, `WeatherService`) is either a
cheap in-memory reader or something `main.py` already constructed —
nothing here calls `AvatarRenderer.mount()`, loads a model, or opens a
network connection merely by being built (see
`ui/minie/avatar_stage.py`'s own docstring for the one genuinely lazy
piece, VTube Studio's connection).

One extra housekeeping step every constructor here needs, mirroring
`ui/jarvis/hud_shell.py`'s own documented fix for the identical gap:
`MinieUiStateAdapter.__init__()` already runs `refresh()` once, before
any of the widgets below exist to subscribe to its signals — that first
emission reaches nobody. `self._ui_state_adapter.refresh()` is called
again at the very end of `__init__`, after every subscriber is wired,
closing that gap for real (found and fixed the same way during this
workstream's own testing, not assumed from Jarvis's precedent alone).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.logging_setup import get_logger
from core.manager import CoreManager
from emotion.state_manager import EmotionalStateManager
from presentation import minie_theme
from presentation.avatar_renderer import AvatarRenderer
from presentation.presentation_controller import PresentationController
from scheduler.calendar_store import CalendarStore
from services.weather_service import WeatherService
from ui.minie.avatar_stage import MinieAvatarStage
from ui.minie.emotion_panel import MinieEmotionPanel
from ui.minie.greeting_card import MinieGreetingCard
from ui.minie.message_bar import MinieMessageBar
from ui.minie.music_panel import MinieMusicPanel
from ui.minie.notes_panel import MinieNotesPanel
from ui.minie.plan_panel import MinieTodaysPlanPanel
from ui.minie.relationship_panel import MinieRelationshipPanel
from ui.minie.sidebar import MinieSidebar
from ui.minie.speech_bubble import MinieSpeechBubble
from ui.minie.status_card import MinieStatusCard
from ui.minie.top_bar import MinieTopBar
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from ui.minie.weather_panel import MinieWeatherPanel
from voice.pipeline import CommunicationPipeline
from voice.session_manager import VoiceSessionManager

logger = get_logger(__name__)

_PLACEHOLDER_PAGE_TITLES: dict[str, str] = {
    "chat": "Chat",
    "tasks": "Tasks",
    "calendar": "Calendar",
    "wellness": "Wellness",
    "reminders": "Reminders",
}
""""home" deliberately has no entry — it is the one page with real
content. See this module's own docstring for the scope decision behind
the other five, mirroring HudShell's own _PLACEHOLDER_PAGE_TITLES."""


def _build_placeholder_page(title: str) -> QWidget:
    """An honest, minimal "not built yet" page — reskinned copy of
    ui/jarvis/hud_shell.py's own _build_placeholder_page(), warmer
    wording/colors to match Minie's own identity."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    heading = QLabel(title)
    heading_font = QFont(minie_theme.FONT_FAMILY)
    heading_font.setPointSize(18)
    heading_font.setBold(True)
    heading.setFont(heading_font)
    heading.setStyleSheet(f"color: {minie_theme.PRIMARY_ACCENT_DEFAULT};")
    heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

    body = QLabel("Coming soon ♡")
    body.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY};")
    body.setAlignment(Qt.AlignmentFlag.AlignCenter)

    layout.addWidget(heading)
    layout.addWidget(body)
    return page


class MinieShell(QWidget):
    """Constructor DI: core_manager, avatar_renderer,
    presentation_controller, emotional_state_manager,
    voice_session_manager, calendar_store, pipeline, weather_service —
    every one of them already constructed at main.py's own
    composition-root time. Builds every ui/minie/ widget itself rather
    than pushing that detail back onto MainWindow, the identical
    division of responsibility HudShell's own docstring establishes."""

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    settings_requested = Signal()

    def __init__(
        self,
        core_manager: CoreManager,
        avatar_renderer: AvatarRenderer,
        presentation_controller: PresentationController,
        emotional_state_manager: EmotionalStateManager,
        voice_session_manager: VoiceSessionManager,
        calendar_store: CalendarStore,
        pipeline: CommunicationPipeline,
        weather_service: WeatherService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("minie_shell")

        try:
            accent_color = core_manager.presentation_config().minie_ui_accent
        except Exception:
            logger.exception(
                "MinieShell failed to read the persona accent color; using the default."
            )
            accent_color = minie_theme.PRIMARY_ACCENT_DEFAULT
        self.setStyleSheet(minie_theme.build_minie_stylesheet(accent_color))

        self._ui_state_adapter = MinieUiStateAdapter(
            presentation_controller,
            emotional_state_manager,
            voice_session_manager,
            avatar_renderer,
            core_manager,
            self,
        )

        self._top_bar = MinieTopBar(core_manager)
        self._top_bar.minimize_requested.connect(self.minimize_requested.emit)
        self._top_bar.maximize_requested.connect(self.maximize_requested.emit)
        self._top_bar.close_requested.connect(self.close_requested.emit)

        self._sidebar = MinieSidebar(core_manager)
        self._sidebar.page_selected.connect(self._on_page_selected)
        self._sidebar.settings_requested.connect(self.settings_requested.emit)

        self._status_card = MinieStatusCard(self._ui_state_adapter)

        self._greeting_card = MinieGreetingCard(self._ui_state_adapter, core_manager)
        self._plan_panel = MinieTodaysPlanPanel(calendar_store, core_manager)
        self._plan_panel.view_calendar_requested.connect(lambda: self._on_page_selected("calendar"))
        self._relationship_panel = MinieRelationshipPanel()

        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(14)
        left_layout.addWidget(self._greeting_card)
        left_layout.addWidget(self._plan_panel)
        left_layout.addWidget(self._relationship_panel)
        left_layout.addStretch(1)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left_scroll.setWidget(left_content)

        self._speech_bubble = MinieSpeechBubble(self._ui_state_adapter)
        self._avatar_stage = MinieAvatarStage(avatar_renderer, self._ui_state_adapter, core_manager)

        center_content = QWidget()
        center_layout = QVBoxLayout(center_content)
        center_layout.setContentsMargins(4, 0, 4, 0)
        center_layout.setSpacing(12)
        center_layout.addWidget(self._speech_bubble)
        center_layout.addWidget(self._avatar_stage, 1)

        self._emotion_panel = MinieEmotionPanel(self._ui_state_adapter, core_manager)
        self._weather_panel = MinieWeatherPanel(weather_service, core_manager)
        self._notes_panel = MinieNotesPanel()
        self._music_panel = MinieMusicPanel()

        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(14)
        right_layout.addWidget(self._emotion_panel)
        right_layout.addWidget(self._weather_panel)
        right_layout.addWidget(self._notes_panel)
        right_layout.addWidget(self._music_panel)
        right_layout.addStretch(1)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        right_scroll.setWidget(right_content)

        self._home_page = QWidget()
        home_layout = QHBoxLayout(self._home_page)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(14)
        home_layout.addWidget(left_scroll, 3)
        home_layout.addWidget(center_content, 5)
        home_layout.addWidget(right_scroll, 2)

        self._content_container = QWidget()
        self._content_layout = QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.addWidget(self._home_page)
        self._placeholder_pages: dict[str, QWidget] = {}
        self._current_page_id = "home"

        self._message_bar = MinieMessageBar(pipeline, self._ui_state_adapter)
        self._message_bar.reply_received.connect(self._speech_bubble.show_reply)
        self._message_bar.home_requested.connect(lambda: self._on_page_selected("home"))
        self._message_bar.relationship_shortcut_requested.connect(
            lambda: self._on_page_selected("home")
        )
        self._message_bar.companion_shortcut_requested.connect(
            lambda: self._on_page_selected("home")
        )

        grid = QGridLayout(self)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setSpacing(14)
        grid.addWidget(self._top_bar, 0, 0, 1, 2)
        grid.addWidget(self._sidebar, 1, 0)
        grid.addWidget(self._content_container, 1, 1)
        grid.addWidget(self._status_card, 2, 0)
        grid.addWidget(self._message_bar, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 6)
        grid.setRowStretch(0, 0)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 0)

        # See this module's own docstring — closes the "adapter already
        # refreshed once before any subscriber existed" gap.
        self._ui_state_adapter.refresh()

    def _on_page_selected(self, page_id: str) -> None:
        self._sidebar.set_active_page(page_id)
        if page_id == self._current_page_id:
            return
        self._current_page_id = page_id

        while self._content_layout.count():
            taken = self._content_layout.takeAt(0)
            widget = taken.widget()
            if widget is not None:
                widget.setParent(None)

        if page_id == "home":
            page = self._home_page
        else:
            page = self._placeholder_pages.get(page_id)
            if page is None:
                title = _PLACEHOLDER_PAGE_TITLES.get(page_id, page_id.title())
                page = _build_placeholder_page(title)
                self._placeholder_pages[page_id] = page
        self._content_layout.addWidget(page)
        page.show()
