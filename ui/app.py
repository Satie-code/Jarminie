"""Desktop shell bootstrap — the single place that constructs a QApplication.

See docs/sprint_book/sprint_1_6.md.

Sprint 5.14: run_app() gains four Level 5 handles (presentation_controller/
jarvis_renderer/minie_renderer/transition_engine) — all already
constructed at main.py's own composition-root time, threaded through
here only because MainWindow's own Qt-layer assembly (PresentationHostWidget,
QtTransitionOverlay) cannot happen before this function's own QApplication
exists (see ui/main_window.py's own docstring).
"""

import sys

from PySide6.QtWidgets import QApplication

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation.jarvis_renderer import JarvisRenderer
from presentation.minie_renderer import MinieRenderer
from presentation.presentation_controller import PresentationController
from presentation.transition_engine import TransitionEngine
from ui.main_window import MainWindow

logger = get_logger(__name__)


def run_app(
    core_manager: CoreManager,
    presentation_controller: PresentationController,
    jarvis_renderer: JarvisRenderer,
    minie_renderer: MinieRenderer,
    transition_engine: TransitionEngine,
) -> int:
    """Start Core, show the main window, and run the Qt event loop.

    Returns the process exit code (from QApplication.exec()).
    """
    app = QApplication(sys.argv)
    window = MainWindow(
        core_manager, presentation_controller, jarvis_renderer, minie_renderer, transition_engine
    )

    core_manager.startup()
    window.refresh_presentation_host()
    logger.info("JARMINEI is running.")
    window.show()

    return app.exec()
