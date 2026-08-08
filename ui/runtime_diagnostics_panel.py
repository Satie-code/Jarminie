"""Runtime Diagnostics Panel — live view of RuntimeManager's own tier/lazy/
state bookkeeping for every registered module.

Runtime Phase 10 (Runtime Refactor Sprint) — the real caller
core_manager.runtime_manager()'s own docstring (core/manager.py) has named
since Runtime Phase 3: "nothing in the shipped UI reads it yet." Read-only,
same discipline as Status Panel (ui/status_panel.py) — never calls
ensure_started()/stop_service() or otherwise mutates RuntimeManager state (a
manual load/unload control is a plausible future sprint, not this one).
Opened as its own separate window via a Debug menu action, matching Debug
Console's (Sprint 1.9) own "non-persistent, occasionally-opened" precedent
rather than Status Panel's embedded-in-MainWindow one — a developer reaches
for this only when actually diagnosing lazy-load behavior, not on every
launch.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager

logger = get_logger(__name__)


class RuntimeDiagnosticsPanel(QWidget):
    """Displays RuntimeManager's own tier/lazy/state for every registered
    service, refreshed on the same QTimer cadence Status Panel already
    established (core_manager.ui_config().status_refresh_interval_ms) —
    one shared, already-tunable interval, not a second config field for
    the identical purpose."""

    def __init__(self, core_manager: CoreManager) -> None:
        super().__init__()
        self.setWindowTitle("JARMINEI Runtime Diagnostics")
        self.resize(500, 400)
        self._core_manager = core_manager

        self._services_label = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Runtime Services</b>"))
        layout.addWidget(self._services_label)

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self.refresh()

    def refresh(self) -> None:
        """Pull RuntimeManager's current tier/lazy/state for every
        registered service, update the display.

        Runs on a QTimer callback with no caller to propagate an
        exception to — a single failed read must not break the recurring
        refresh or crash the app; it's logged and the display simply
        keeps its last-known-good values until the next tick (Fail
        Gracefully Rule, the identical discipline Status Panel's own
        refresh() already established)."""
        try:
            runtime_manager = self._core_manager.runtime_manager()
            names = runtime_manager.names()
            rows = [
                f"{name}: tier={runtime_manager.tier_of(name).value} "
                f"lazy={runtime_manager.is_lazy(name)} "
                f"state={runtime_manager.state_of(name).value}"
                for name in names
            ]
        except Exception:
            logger.exception("Runtime Diagnostics Panel refresh failed; keeping last display.")
            return

        self._services_label.setText("\n".join(rows) if rows else "No services registered.")
