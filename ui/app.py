"""Desktop shell bootstrap — the single place that constructs a QApplication.

See docs/sprint_book/sprint_1_6.md.
"""

import sys

from PySide6.QtWidgets import QApplication

from core.logging_setup import get_logger
from core.manager import CoreManager
from ui.main_window import MainWindow

logger = get_logger(__name__)


def run_app(core_manager: CoreManager) -> int:
    """Start Core, show the main window, and run the Qt event loop.

    Returns the process exit code (from QApplication.exec()).
    """
    app = QApplication(sys.argv)
    window = MainWindow(core_manager)

    core_manager.startup()
    logger.info("JARMINEI is running.")
    window.show()

    return app.exec()
