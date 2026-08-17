"""Main window — the JARMINEI desktop shell.

Deliberately "dumb": owns no business logic, only knows about CoreManager
(never config, logging, or resource-monitor internals directly), and
delegates lifecycle decisions to it. See docs/sprint_book/sprint_1_6.md,
sprint_1_7.md, sprint_1_8.md, sprint_1_9.md for this window's original
Level 1 shape; Settings (1.8) and Debug Console (1.9) are still each
opened as their own window via a menu action, which suits their
non-persistent, occasionally-opened nature.

Sprint 5.14 (Presentation Layer Integration) added `PresentationHostWidget`
(`presentation/presentation_host_widget.py`) and `QtTransitionOverlay`
(`presentation/qt_transition_overlay.py`, parented to `PresentationHostWidget`
and wired into `TransitionEngine` via `set_overlay()` — the real `QWidget`
can't exist before a `QApplication` does, which is why this composition
step happens here rather than at `main.py`'s own composition-root time;
see `TransitionEngine.set_overlay()`'s own docstring for the full
reasoning).

**JARVIS Holographic HUD reskin, Phase 1**: the central widget used to be
a plain `QVBoxLayout` container holding a `QSplitter` (`PresentationHostWidget`
stacked above `StatusPanel`). It is now `ui/jarvis/hud_shell.py`'s
`HudShell` — a five-zone cinematic HUD grid (top bar / left rail / center
stage / right rail / command bar) that this class still constructs
`PresentationHostWidget` for exactly as before and simply hands to
`HudShell` rather than a `QSplitter`. This workstream is tracked in code
docstrings only (not docs/STATUS.md/sprint_book), the same out-of-band
precedent the earlier Runtime Refactor Sprint established, since it
reskins the already-frozen Level 6 Master Sprint Book rather than
extending it.

**Phase 2**: `HudShell` also builds a left `NavigationRail` internally.
Its "page" items are handled entirely inside `HudShell` (center-zone
content swapping); its "action" items surface as public signals this
class connects to real, already-existing behavior — System to
`_open_runtime_diagnostics()`, Settings to `_open_settings()`, both
below. Code stays unconnected (and its rail button disabled) until
Phase 4 gives this class an ActionRegistry to dispatch "Open VS Code"
through.

**Phase 4**: this class gains two new constructor collaborators —
`CalendarStore` and `ActionRegistry` — threaded straight through to
`HudShell` (which builds the real Mission Status/Reminders/Quick
Commands panels from them; see that module's own docstring). Both are
already constructed in `main.py` today, for `CommunicationPipeline`
alone — this is the identical "thread an existing collaborator into
MainWindow via constructor DI" pattern `presentation_controller`/
`jarvis_renderer` etc. already established, not a new architectural
seam. `hud_shell.system_stats_requested` (bubbled up from
`QuickCommandsPanel`'s own "Show System Stats" button) connects to
`_open_runtime_diagnostics()` exactly like the nav rail's own System
item already does.

**Phase 5**: `HudShell` no longer takes (or embeds) `StatusPanel` — its
role in the dashboard is fully superseded by the right rail's real
System Overview/Temperature/Network/Active Modules panels. This class
therefore no longer constructs a `StatusPanel` either; `ui/status_panel.py`
itself is untouched and still real/tested, simply no longer embedded
anywhere in this app.

**Phase 6**: two more constructor collaborators — `VoiceSessionManager`
and `CommunicationPipeline` — thread straight through to `HudShell` for
its own Voice Interaction Indicator and Command Bar (see that module's
own docstring).

**Phase 7**: `jarvis_renderer` (already received above, for
`PresentationHostWidget`) is now ALSO forwarded to `HudShell`, which
wires it to a resource-aware `AnimationManager` — no new constructor
parameter here, just one already-held object reaching one more place.
"""

from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMenu

from core.logging_setup import get_logger
from core.manager import CoreManager
from device_control.action_engine import ActionRegistry
from presentation.jarvis_renderer import JarvisRenderer
from presentation.minie_renderer import MinieRenderer
from presentation.presentation_controller import PresentationController
from presentation.presentation_host_widget import PresentationHostWidget
from presentation.qt_transition_overlay import QtTransitionOverlay
from presentation.transition_engine import TransitionEngine
from scheduler.calendar_store import CalendarStore
from ui.debug_console import DebugConsole
from ui.jarvis.hud_shell import HudShell
from ui.runtime_diagnostics_panel import RuntimeDiagnosticsPanel
from ui.settings_window import SettingsWindow
from voice.pipeline import CommunicationPipeline
from voice.session_manager import VoiceSessionManager

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """The application's single top-level window.

    Receives a CoreManager via constructor DI — it never constructs one
    itself. closeEvent() calls core_manager.shutdown() before accepting
    the close, so closing the window is always a clean shutdown.

    Sprint 5.14: also receives presentation_controller/jarvis_renderer/
    minie_renderer/transition_engine — all already constructed at
    main.py's own composition-root time, per this project's "only
    main.py constructs concrete subsystem instances" rule; MainWindow
    only assembles the Qt-layer widgets that depend on them.
    """

    def __init__(
        self,
        core_manager: CoreManager,
        presentation_controller: PresentationController,
        jarvis_renderer: JarvisRenderer,
        minie_renderer: MinieRenderer,
        transition_engine: TransitionEngine,
        calendar_store: CalendarStore,
        action_registry: ActionRegistry,
        voice_session_manager: VoiceSessionManager,
        pipeline: CommunicationPipeline,
    ) -> None:
        super().__init__()
        self._core_manager = core_manager
        self._debug_console: DebugConsole | None = None
        self._runtime_diagnostics_panel: RuntimeDiagnosticsPanel | None = None
        self.setWindowTitle("JARMINEI")
        # The reference HUD is wide/cinematic — 800x600 (Level 1's own
        # original default) reads as a cramped normal-desktop window
        # against it. A large default with real resizing (not a forced
        # exclusive fullscreen — friendlier for development/multi-monitor
        # use) suits the brief's "fullscreen-oriented" intent without
        # taking over the whole screen unasked.
        self.resize(1600, 950)

        self._presentation_host = PresentationHostWidget(
            presentation_controller, jarvis_renderer, minie_renderer, core_manager
        )

        self._hud_shell = HudShell(
            core_manager,
            self._presentation_host,
            calendar_store,
            action_registry,
            voice_session_manager,
            pipeline,
            jarvis_renderer,
        )
        self.setCentralWidget(self._hud_shell)

        self._transition_overlay = QtTransitionOverlay(self._presentation_host)
        transition_engine.set_overlay(self._transition_overlay)

        self._build_menu()
        self._hud_shell.navigation_rail.settings_requested.connect(self._open_settings)
        self._hud_shell.navigation_rail.system_requested.connect(self._open_runtime_diagnostics)
        self._hud_shell.system_stats_requested.connect(self._open_runtime_diagnostics)

    def refresh_presentation_host(self) -> None:
        """Sprint 5.14: PresentationController.start() (which mounts the
        default-active persona's renderer) runs inside
        core_manager.startup(), which itself runs AFTER MainWindow's own
        constructor already ran PresentationHostWidget's first refresh()
        — without this, the presentation pane would sit empty until its
        own QTimer's first tick. ui/app.py's run_app() calls this once,
        right after core_manager.startup(), closing that cosmetic gap."""
        self._presentation_host.refresh()

    def _build_menu(self) -> None:
        # QMenu constructed explicitly with `self` as its C++ parent, then
        # inserted via the QMenu-object overload of addMenu() — the
        # string-convenience overload (menuBar().addMenu("title")) has a
        # known PySide6 ownership-tracking gotcha where the returned QMenu
        # can report its C++ object as already deleted even with a live
        # Python reference held. Caught by a test actually touching the
        # menu after construction, not assumed safe.
        self._settings_menu = QMenu("&Settings", self)
        self.menuBar().addMenu(self._settings_menu)
        self._open_settings_action = QAction("Open Settings...", self)
        self._open_settings_action.triggered.connect(self._open_settings)
        self._settings_menu.addAction(self._open_settings_action)

        self._debug_menu = QMenu("&Debug", self)
        self.menuBar().addMenu(self._debug_menu)
        self._open_debug_console_action = QAction("Open Debug Console", self)
        self._open_debug_console_action.triggered.connect(self._open_debug_console)
        self._debug_menu.addAction(self._open_debug_console_action)

        self._open_runtime_diagnostics_action = QAction("Open Runtime Diagnostics", self)
        self._open_runtime_diagnostics_action.triggered.connect(self._open_runtime_diagnostics)
        self._debug_menu.addAction(self._open_runtime_diagnostics_action)

    def _open_settings(self) -> None:
        """Open the Settings dialog, seeded from Core Manager's current
        config. Edits take effect on next launch — no live hot-reload."""
        dialog = SettingsWindow(self._core_manager.config(), self._core_manager.config_loader())
        dialog.exec()

    def _open_debug_console(self) -> None:
        """Open (or re-open) the Debug Console as a separate, non-modal
        window. A fresh instance is created each time — the previous one
        (if any) already detached its own log handler in its closeEvent()
        when it was closed, so this can't leak or duplicate handlers.
        Stored on self so PySide6 doesn't garbage-collect it while shown
        (non-modal .show() returns immediately, unlike .exec())."""
        self._debug_console = DebugConsole()
        self._debug_console.show()

    def _open_runtime_diagnostics(self) -> None:
        """Open (or re-open) the Runtime Diagnostics Panel as a separate,
        non-modal window — the identical "fresh instance each time" shape
        _open_debug_console() already established (nothing here needs
        detaching on close, unlike Debug Console's log handler, but the
        window-lifecycle shape is otherwise the same)."""
        self._runtime_diagnostics_panel = RuntimeDiagnosticsPanel(self._core_manager)
        self._runtime_diagnostics_panel.show()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override, not our naming convention)
        # Debug Console and Runtime Diagnostics Panel are both separate
        # top-level windows (not child dialogs closed automatically with
        # this one) — without explicitly closing them here, Qt's
        # app.exec() keeps running as long as either is still visible,
        # leaving the process alive with no visible main window. Caught
        # by actually running the app with Debug Console open, not by any
        # mocked test (see debug_console's own precedent this follows).
        if self._debug_console is not None:
            self._debug_console.close()
        if self._runtime_diagnostics_panel is not None:
            self._runtime_diagnostics_panel.close()
        logger.info("Main window closing - shutting down Core.")
        self._core_manager.shutdown()
        event.accept()
