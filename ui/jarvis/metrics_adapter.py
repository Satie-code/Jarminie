"""MetricsAdapter — JARVIS Holographic HUD reskin, Phase 5.

One shared `QTimer` polling `CoreManager` once per tick, emitting Qt
signals the right-rail panels (`SystemOverviewPanel`/`ActiveModulesPanel`)
subscribe to, instead of each running its own independent `QTimer` +
`CoreManager` call. Both panels would otherwise poll the exact same two
`CoreManager` methods (`check_resources()`/`runtime_manager()`) on the
same cadence twice over — section 25's own "don't run duplicate
expensive work" mandate, applied for real here.

Earlier phases' panels (`MissionStatusPanel`, `RemindersPanel`,
`TopBar`, and — before this phase removed it from the dashboard —
`StatusPanel`) keep their own independent timers, deliberately not
retrofitted onto this adapter: each is already tested and working, and
unifying them carries real regression risk for a proportionally small
resource saving. A future phase could consolidate them for real if ever
measured to matter; this phase only avoids adding MORE duplication on
top of what already exists.
"""

from PySide6.QtCore import QObject, QTimer, Signal

from core.logging_setup import get_logger
from core.manager import CoreManager
from core.module_registry import ServiceState

logger = get_logger(__name__)


class MetricsAdapter(QObject):
    """Constructor DI: only CoreManager. resources_updated carries a
    real ResourceSnapshot; runtime_updated carries a plain
    dict[str, ServiceState] (already resolved — a subscriber never needs
    to call back into RuntimeManager itself)."""

    resources_updated = Signal(object)
    runtime_updated = Signal(object)

    def __init__(self, core_manager: CoreManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._core_manager = core_manager

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Fail Gracefully per source: a resource-sample failure must
        not suppress a still-working runtime-state read, and vice versa
        — each is guarded independently rather than one try/except
        covering both, matching the two-source shape of this class."""
        try:
            snapshot = self._core_manager.check_resources()
        except Exception:
            logger.exception("MetricsAdapter failed to sample resources; skipping this tick.")
        else:
            self.resources_updated.emit(snapshot)

        try:
            runtime_manager = self._core_manager.runtime_manager()
            states: dict[str, ServiceState] = {
                name: runtime_manager.state_of(name) for name in runtime_manager.names()
            }
        except Exception:
            logger.exception("MetricsAdapter failed to read runtime state; skipping this tick.")
        else:
            self.runtime_updated.emit(states)
