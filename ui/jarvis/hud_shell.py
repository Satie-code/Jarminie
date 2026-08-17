"""HudShell — JARVIS Holographic HUD reskin.

Replaces MainWindow's previous plain `QSplitter` body (PresentationHostWidget
stacked above StatusPanel, unchanged since Sprint 5.14) with a responsive
five-zone HUD grid matching the reference image's composition: a top bar
spanning the full width, a left rail, a center stage, a right rail, and a
bottom command bar. Built with QGridLayout stretch factors (2:5:2 columns,
a fixed-height top/bottom bar around a stretching middle row) rather than
fixed pixel positions, so the layout stays proportionally correct across
resolutions (16:9, 16:10, 1920x1080, 2560x1440, laptop displays) per the
brief's own Window Design section.

**Phase 1** established the theme and zone geometry: `PresentationHostWidget`
(the real Jarvis/Minie renderer host, unchanged) in the center zone,
`StatusPanel` (also unchanged) temporarily relocated into the right zone
until Phase 5's own System Overview/Temperature/Network/Active Modules
panels supersede its content there.

**Phase 2** adds the brief's Global HUD Frame (`HudFrame`, corner
brackets), Top Information Bar (`TopBar`, branding + live clock/date/
greeting), and Left Navigation Rail (`NavigationRail`). The rail's four
"page" items (Dashboard/Conversation/Memory/Tasks) swap the center
zone's content; per this workstream's own confirmed scope decision, only
Dashboard shows real content (the existing hologram) — Conversation/
Memory/Tasks each show an honest "Coming soon" placeholder, the same
pattern `presentation/jarvis_renderer.py`'s own per-workspace-profile
panels already established, built once and cached rather than rebuilt on
every click. The rail's three "action" items (System/Code/Settings) are
exposed as public signals (`navigation_rail.system_requested`/
`code_requested`/`settings_requested`) rather than handled here —
MainWindow already owns `_open_runtime_diagnostics()`/`_open_settings()`,
so it connects those two directly; `code_requested` stays unconnected
(and its button disabled) until Phase 4 gives MainWindow an
ActionRegistry to dispatch "Open VS Code" through.

**Phase 4** fills the left rail below `NavigationRail` with the brief's
own Mission Status / Upcoming Reminders / Quick Commands panels, and
gives `HudShell` two new constructor collaborators — `CalendarStore`
(reminders) and `ActionRegistry` (quick commands) — mirroring the exact
DI pattern `core_manager`/`presentation_host_widget`/`status_panel`
already established. `QuickCommandsPanel.system_stats_requested` bubbles
up through this class's own identically-named signal (rather than
MainWindow reaching into HudShell's own children directly) so MainWindow
can connect it to `_open_runtime_diagnostics()` exactly like
`navigation_rail.system_requested` already is.

**Phase 5** fills the right rail with the brief's own System Overview /
System Temperature / Network Status / Active Modules panels, all reading
through one shared `MetricsAdapter` (a single `QTimer` polling
`CoreManager` once per tick, rather than each of the two data-driven
panels running its own — see that module's own docstring). This
supersedes `StatusPanel`'s role in the dashboard entirely — `status_panel`
is no longer a constructor parameter here (or on `MainWindow`); the
class itself (`ui/status_panel.py`) is untouched and still real/tested,
just no longer embedded anywhere in this app.

**Phase 6** adds the brief's own Voice Interaction Indicator (embedded
inside `TopBar`, see that module's own docstring) and bottom Command Bar
(`CommandBar`, in `command_bar_zone`). Two new constructor collaborators
— `VoiceSessionManager` (threaded into `TopBar`) and
`CommunicationPipeline` (`CommandBar`'s own `submit_text()` target) —
mirror the exact same DI pattern every earlier phase's own new
collaborator already established.

**Phase 7** wires `presentation/animation_manager.py`'s own
`AnimationManager` to `MetricsAdapter.resources_updated` (no new
polling — see that module's own docstring) and to
`jarvis_renderer.apply_resource_degradation()`. `jarvis_renderer` is a
new constructor parameter here — `MainWindow` already receives it (to
build `PresentationHostWidget`), just wasn't forwarding it to `HudShell`
separately until this phase needed it for this one additional wire-up.

**Phase 9** sources `navigation_rail`'s active-item accent and
`_hud_frame`'s corner-bracket color from `core_manager.presentation_config()
.jarvis_ui_accent` (a one-time read at construction — that value is
persona-identity-locked, not mood-driven, per Level 5's own tested
contract) instead of a separately-hardcoded theme constant that only
coincidentally matched it before this phase.

**Phase 10** (final regression pass): the left column's own natural
content height (`NavigationRail`'s seven fixed-height rows plus three
panels) turned out to exceed a real smaller-laptop screen's available
height — confirmed directly (~885px minimum vs. a real 768px-tall
display), not assumed. `navigation_rail`/`MissionStatusPanel`/
`RemindersPanel`/`quick_commands_panel` now live inside an inner
`left_content` widget wrapped in a `QScrollArea`, so the left column
scrolls on a short screen rather than forcing the whole window taller —
the same pattern `MissionStatusPanel`/`ActiveModulesPanel` already use
internally, applied one level up.

Each zone exposes its own QVBoxLayout via `layout_()` so a later phase
can `addWidget()`/`addLayout()` into it without this module rebuilding
the shell's own grid geometry.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from core.manager import CoreManager
from device_control.action_engine import ActionRegistry
from presentation import theme
from presentation.animation_manager import AnimationManager
from presentation.jarvis_renderer import JarvisRenderer
from scheduler.calendar_store import CalendarStore
from ui.jarvis.active_modules_panel import ActiveModulesPanel
from ui.jarvis.command_bar import CommandBar
from ui.jarvis.hud_frame import HudFrame
from ui.jarvis.metrics_adapter import MetricsAdapter
from ui.jarvis.mission_status_panel import MissionStatusPanel
from ui.jarvis.navigation_rail import NavigationRail, NavItem
from ui.jarvis.network_panel import NetworkPanel
from ui.jarvis.quick_commands_panel import QuickCommandsPanel
from ui.jarvis.reminders_panel import RemindersPanel
from ui.jarvis.system_overview_panel import SystemOverviewPanel
from ui.jarvis.temperature_panel import TemperaturePanel
from ui.jarvis.top_bar import TopBar
from voice.pipeline import CommunicationPipeline
from voice.session_manager import VoiceSessionManager

_TOP_BAR_HEIGHT = 92
_COMMAND_BAR_HEIGHT = 84

_PLACEHOLDER_PAGE_TITLES: dict[NavItem, str] = {
    NavItem.CONVERSATION: "Conversation",
    NavItem.MEMORY: "Memory",
    NavItem.TASKS: "Tasks",
}
"""Dashboard deliberately has no entry — it is the one page with real
content (the existing PresentationHostWidget), never a placeholder. See
this module's own docstring for the confirmed scope decision behind the
other three."""


def _build_placeholder_page(title: str) -> QWidget:
    """An honest, minimal "not built yet" page — same shape as
    presentation/jarvis_renderer.py's own _build_placeholder_panel()."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    heading = QLabel(title.upper())
    heading_font = QFont(theme.FONT_FAMILY)
    heading_font.setPointSize(18)
    heading_font.setBold(True)
    heading.setFont(heading_font)
    heading.setStyleSheet(f"color: {theme.ACCENT_CYAN};")
    heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

    body = QLabel("Coming soon.")
    body.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
    body.setAlignment(Qt.AlignmentFlag.AlignCenter)

    layout.addWidget(heading)
    layout.addWidget(body)
    return page


class _Zone(QWidget):
    """A themed HUD panel-region container: a translucent-feeling dark
    panel with a thin technical border (the brief's own "thin luminous
    borders" / "fine technical lines" language) and its own vertical
    layout for whichever widgets a given phase adds to it."""

    def __init__(self, object_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        # A plain QWidget subclass paints nothing of its own — without
        # WA_StyledBackground, its "background-color"/"border" QSS rules
        # are silently ignored and whatever's beneath (here: MainWindow's
        # own palette-filled background) just shows through instead. Easy
        # to miss since the app still "looks themed" (uniformly dark)
        # without it — confirmed by an actual rendered screenshot during
        # Phase 1's own verification, not assumed from the docs alone.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#{object_name} {{"
            f" background-color: {theme.BG_PANEL};"
            f" border: 1px solid {theme.BORDER_DIM};"
            f" border-radius: 8px;"
            f" }}"
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(8)

    def layout_(self) -> QVBoxLayout:
        """Named layout_() rather than overriding QWidget.layout() (which
        already exists, returns the same object, but has an incompatible
        no-argument C++ signature not worth shadowing)."""
        return self._layout


class HudShell(QWidget):
    """Composes the JARVIS HUD's five zones around the real, already-
    constructed collaborators this phase receives via constructor DI —
    core_manager, presentation_host_widget, calendar_store, and
    action_registry — the same "only main.py/MainWindow construct
    concrete instances the rest of the app depends on" DI pattern this
    project already follows for JarvisRenderer/PresentationController
    etc. Everything else this class needs (TopBar/NavigationRail/
    HudFrame/MetricsAdapter and every panel built from them) has no
    collaborators beyond what HudShell itself already has, so it
    constructs all of them directly rather than pushing that detail
    back onto MainWindow."""

    system_stats_requested = Signal()

    def __init__(
        self,
        core_manager: CoreManager,
        presentation_host_widget: QWidget,
        calendar_store: CalendarStore,
        action_registry: ActionRegistry,
        voice_session_manager: VoiceSessionManager,
        pipeline: CommunicationPipeline,
        jarvis_renderer: JarvisRenderer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("hud_shell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#hud_shell {{ background-color: {theme.BG_VOID}; }}")

        self._presentation_host_widget = presentation_host_widget
        self._placeholder_pages: dict[NavItem, QWidget] = {}

        self.top_bar_zone = _Zone("hud_top_bar")
        self.left_zone = _Zone("hud_left_rail")
        self.center_zone = _Zone("hud_center")
        self.right_zone = _Zone("hud_right_rail")
        self.command_bar_zone = _Zone("hud_command_bar")

        self.top_bar_zone.setFixedHeight(_TOP_BAR_HEIGHT)
        self.command_bar_zone.setFixedHeight(_COMMAND_BAR_HEIGHT)

        self.top_bar_zone.layout_().setContentsMargins(10, 4, 10, 4)
        self.top_bar_zone.layout_().addWidget(TopBar(core_manager, voice_session_manager))

        # The left column's own natural content height (nav rail's seven
        # fixed-height rows + three panels) exceeds a smaller laptop
        # screen's own available height (confirmed directly: ~885px
        # minimum vs. a real 768px-tall display) — wrapped in a
        # QScrollArea, the same "let the region scroll rather than force
        # the whole window taller" pattern MissionStatusPanel/
        # ActiveModulesPanel already use internally, one level up.
        left_content = QWidget()
        left_content_layout = QVBoxLayout(left_content)
        left_content_layout.setContentsMargins(0, 0, 0, 0)
        left_content_layout.setSpacing(8)

        self.navigation_rail = NavigationRail()
        self.navigation_rail.page_selected.connect(self._on_page_selected)
        left_content_layout.addWidget(self.navigation_rail)

        left_content_layout.addSpacing(6)
        left_content_layout.addWidget(MissionStatusPanel(core_manager), 2)
        left_content_layout.addWidget(RemindersPanel(calendar_store, core_manager), 1)
        self.quick_commands_panel = QuickCommandsPanel(action_registry)
        self.quick_commands_panel.system_stats_requested.connect(self.system_stats_requested.emit)
        left_content_layout.addWidget(self.quick_commands_panel, 1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left_scroll.setWidget(left_content)
        self.left_zone.layout_().addWidget(left_scroll)

        # Now that ActionRegistry is real (this phase), the nav rail's
        # own "Code" item can fire the same "Open VS Code" action
        # QuickCommandsPanel's own button does — Phase 2 left it
        # disabled specifically until this collaborator existed.
        self.navigation_rail.code_requested.connect(self.quick_commands_panel.open_vscode)
        self.navigation_rail.set_code_action_enabled(True)

        self.center_zone.layout_().addWidget(presentation_host_widget)

        metrics_adapter = MetricsAdapter(core_manager, self)
        self.right_zone.layout_().addWidget(SystemOverviewPanel(metrics_adapter), 2)
        self.right_zone.layout_().addWidget(TemperaturePanel(), 1)
        self.right_zone.layout_().addWidget(NetworkPanel(), 1)
        self.right_zone.layout_().addWidget(ActiveModulesPanel(metrics_adapter), 2)
        # MetricsAdapter.__init__() already ran refresh() once (its own
        # constructor-time convention, matching every other panel's own
        # "populate immediately, don't wait for the first tick" habit)
        # — but at that moment neither panel above had subscribed yet,
        # so that first emission reached nobody. Found by an actual
        # screenshot during this phase's own verification: both panels
        # sat on N/A/empty until the first real timer tick, up to
        # status_refresh_interval_ms (3s by default) after launch.
        # Refreshing again now, after both are wired up, closes that gap.
        metrics_adapter.refresh()

        self._animation_manager = AnimationManager(core_manager.resource_thresholds(), self)
        metrics_adapter.resources_updated.connect(self._animation_manager.on_resources_updated)
        self._animation_manager.level_changed.connect(jarvis_renderer.apply_resource_degradation)

        self.command_bar_zone.layout_().setContentsMargins(10, 2, 10, 2)
        self.command_bar_zone.layout_().addWidget(CommandBar(pipeline))

        grid = QGridLayout(self)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(10)
        grid.addWidget(self.top_bar_zone, 0, 0, 1, 3)
        grid.addWidget(self.left_zone, 1, 0)
        grid.addWidget(self.center_zone, 1, 1)
        grid.addWidget(self.right_zone, 1, 2)
        grid.addWidget(self.command_bar_zone, 2, 0, 1, 3)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 5)
        grid.setColumnStretch(2, 2)
        grid.setRowStretch(0, 0)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 0)

        self._hud_frame = HudFrame(self)

        # JARVIS Holographic HUD reskin, Phase 9: a one-time read of the
        # mounted persona's own locked accent, so the nav rail's active
        # bar and the HUD frame's corner brackets are genuinely SOURCED
        # from the same config the hologram itself reads (config/schema.py's
        # PresentationConfig.jarvis_ui_accent) rather than a separately-
        # hardcoded theme constant that only coincidentally matched it
        # before this phase. jarvis_ui_accent is persona-identity-locked,
        # not mood-driven (Level 5's own tested contract — see
        # presentation/jarvis_state_computer.py) — a one-time read at
        # construction is therefore honest, not a simplification of a
        # value that would otherwise change live.
        accent_color = core_manager.presentation_config().jarvis_ui_accent
        self.navigation_rail.set_accent_color(accent_color)
        self._hud_frame.set_accent_color(accent_color)

    def _on_page_selected(self, item: NavItem) -> None:
        layout = self.center_zone.layout_()
        while layout.count():
            taken = layout.takeAt(0)
            widget = taken.widget()
            if widget is not None:
                widget.setParent(None)

        if item is NavItem.DASHBOARD:
            page = self._presentation_host_widget
        else:
            page = self._placeholder_pages.get(item)
            if page is None:
                page = _build_placeholder_page(_PLACEHOLDER_PAGE_TITLES[item])
                self._placeholder_pages[item] = page
        layout.addWidget(page)
        page.show()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        super().resizeEvent(event)
        self._hud_frame.sync_geometry()
