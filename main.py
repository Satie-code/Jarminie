"""JARMINEI application entrypoint — the sole composition root.

Constructs concrete subsystem instances and wires them together via
dependency injection; no other file in the codebase should construct
these directly. See docs/sprint_book/sprint_1_5.md and sprint_1_6.md.

Startup happens inside ui.app.run_app(); shutdown happens inside
MainWindow.closeEvent() when the user closes the window — the Qt event
loop (app.exec()) is what keeps the process alive between the two.
"""

import sys

from config import ConfigLoader
from core import configure_logging
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
from ui.app import run_app


def main() -> int:
    config_loader = ConfigLoader()
    config = config_loader.load()
    configure_logging(config.logging)

    resource_monitor = ResourceMonitor(config.resources)
    core_manager = CoreManager(config, resource_monitor, config_loader)

    return run_app(core_manager)


if __name__ == "__main__":
    sys.exit(main())
