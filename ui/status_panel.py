"""Status Panel — live view of module states and resource usage.

Read-only: never calls restart_module() or otherwise mutates Core state
(a manual restart control is a plausible future sprint, not this one).
Takes only a CoreManager — not a separate ResourceMonitor, per the
recommendation accepted after Sprint 1.6 — going through
CoreManager.module_states() / check_resources() / ui_config() keeps the
"UI layer only knows about CoreManager" boundary from Sprint 1.6 intact.
See docs/sprint_book/sprint_1_7.md.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.manager import CoreManager


class StatusPanel(QWidget):
    """Displays Core Manager's module registry and a live resource readout."""

    def __init__(self, core_manager: CoreManager) -> None:
        super().__init__()
        self._core_manager = core_manager

        self._module_label = QLabel()
        self._resource_label = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Modules</b>"))
        layout.addWidget(self._module_label)
        layout.addWidget(QLabel("<b>Resources</b>"))
        layout.addWidget(self._resource_label)

        # Interval comes from config (Sprint 1.2's UIConfig), never a
        # hardcoded literal, so it can be tuned without a code change —
        # see the "Timer interval too aggressive" risk in sprint_1_7.md.
        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self.refresh()

    def refresh(self) -> None:
        """Pull current module states and a fresh resource sample, update labels."""
        states = self._core_manager.module_states()
        if states:
            text = "\n".join(f"{name}: {state}" for name, state in states.items())
        else:
            text = "No modules registered."
        self._module_label.setText(text)

        snapshot = self._core_manager.check_resources()
        battery_text = (
            f"{snapshot.battery_percent:.0f}%" if snapshot.battery_percent is not None else "n/a"
        )
        self._resource_label.setText(
            f"CPU: {snapshot.cpu_percent:.0f}%   "
            f"RAM: {snapshot.ram_percent:.0f}%   "
            f"Disk: {snapshot.disk_percent:.0f}%   "
            f"Battery: {battery_text}"
        )
