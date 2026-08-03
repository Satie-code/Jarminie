"""Main window — the JARMINEI desktop shell.

Deliberately "dumb": owns no business logic, only knows about CoreManager
(never config, logging, or resource-monitor internals directly), and
delegates lifecycle decisions to it. The central widget is a QVBoxLayout
container (decided at the start of Sprint 1.7, per the recommendation
accepted after Sprint 1.6). In practice only Status Panel (1.7) ended up
embedded in it — Settings (1.8) and Debug Console (1.9) are each opened
as their own window via a menu action instead, which turned out to suit
their non-persistent, occasionally-opened nature better. See
docs/sprint_book/sprint_1_6.md, sprint_1_7.md, sprint_1_8.md, sprint_1_9.md.

Sprint 5.14 (Presentation Layer Integration) adds a `QSplitter` above the
existing central layout: a new top pane, `PresentationHostWidget`
(`presentation/presentation_host_widget.py`), sits above `StatusPanel` —
unchanged, not removed, not repurposed, per this sprint's own Engineering
Rationale. `QtTransitionOverlay` (`presentation/qt_transition_overlay.py`)
is constructed here too, parented to `PresentationHostWidget`, and wired
into the already-constructed `TransitionEngine` via `set_overlay()` — the
real `QWidget` neither can exist before a `QApplication` does, which is
why this composition step happens here rather than at `main.py`'s own
composition-root time (see `TransitionEngine.set_overlay()`'s own
docstring for the full reasoning).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMenu, QSplitter, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation.jarvis_renderer import JarvisRenderer
from presentation.minie_renderer import MinieRenderer
from presentation.presentation_controller import PresentationController
from presentation.presentation_host_widget import PresentationHostWidget
from presentation.qt_transition_overlay import QtTransitionOverlay
from presentation.transition_engine import TransitionEngine
from ui.debug_console import DebugConsole
from ui.settings_window import SettingsWindow
from ui.status_panel import StatusPanel

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
    ) -> None:
        super().__init__()
        self._core_manager = core_manager
        self._debug_console: DebugConsole | None = None
        self.setWindowTitle("JARMINEI")
        self.resize(800, 600)

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self.setCentralWidget(container)

        self._presentation_host = PresentationHostWidget(
            presentation_controller, jarvis_renderer, minie_renderer, core_manager
        )
        self._status_panel = StatusPanel(core_manager)

        self._splitter = QSplitter()
        self._splitter.setOrientation(Qt.Orientation.Vertical)
        self._splitter.addWidget(self._presentation_host)
        self._splitter.addWidget(self._status_panel)
        self._layout.addWidget(self._splitter)

        self._transition_overlay = QtTransitionOverlay(self._presentation_host)
        transition_engine.set_overlay(self._transition_overlay)

        self._build_menu()

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

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override, not our naming convention)
        # Debug Console is a separate top-level window (not a child dialog
        # closed automatically with this one) — without explicitly closing
        # it here, Qt's app.exec() keeps running as long as it's still
        # visible, leaving the process alive with no visible main window.
        # Caught by actually running the app with Debug Console open, not
        # by any mocked test.
        if self._debug_console is not None:
            self._debug_console.close()
        logger.info("Main window closing - shutting down Core.")
        self._core_manager.shutdown()
        event.accept()
