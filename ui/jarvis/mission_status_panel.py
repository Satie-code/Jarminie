"""MissionStatusPanel — JARVIS Holographic HUD reskin, Phase 4.

The brief's own "Mission Status" panel: real per-service status rows
sourced from `CoreManager.runtime_manager()` — every registered
service, not a curated subset resembling the brief's own example labels
("AI Core", "Internet Connection", "Sensors"). Those don't map onto this
codebase's real registered module names ("memory_store",
"task_scheduler", "voice_session_manager", ...) without inventing a
translation table that could misrepresent what's actually running —
"These values MUST come from the actual runtime/service state. Never
fake them" (the brief's own Mission Status section) is taken literally
here: real names, real `ServiceState`. Same data source
`ui/runtime_diagnostics_panel.py`'s `RuntimeDiagnosticsPanel` already
uses, formatted as a colored-dot status list instead of that panel's
plain text — status is never color-only (section 28): each row also
carries the state's own text label.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from core.module_registry import ServiceState
from presentation import theme

logger = get_logger(__name__)

_STATE_COLOR: dict[ServiceState, str] = {
    ServiceState.READY: theme.STATUS_GREEN,
    ServiceState.ACTIVE: theme.STATUS_GREEN,
    ServiceState.LOADING: theme.STATUS_AMBER,
    ServiceState.IDLE: theme.STATUS_GRAY,
    ServiceState.SUSPENDED: theme.STATUS_GRAY,
    ServiceState.NOT_LOADED: theme.STATUS_GRAY,
    ServiceState.UNLOADED: theme.STATUS_GRAY,
}


def _row_html(name: str, state: ServiceState) -> str:
    color = _STATE_COLOR.get(state, theme.STATUS_GRAY)
    return (
        f'<span style="color:{color};">&#9679;</span> '
        f'<span style="color:{theme.TEXT_PRIMARY};">{name}</span> '
        f'<span style="color:{theme.TEXT_SECONDARY};">{state.value}</span>'
    )


class MissionStatusPanel(QWidget):
    """Constructor DI: only CoreManager, the same single-collaborator
    discipline every other CoreManager-backed panel in this workstream
    already follows. Rows are built once per name and updated in place
    on refresh (never rebuilt from scratch) — the same "reuse, don't
    reallocate" discipline section 25 asks of every HUD widget."""

    def __init__(self, core_manager: CoreManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._core_manager = core_manager
        self._row_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QLabel("MISSION STATUS")
        header.setStyleSheet(f"color: {theme.ACCENT_CYAN}; font-weight: 600;")
        layout.addWidget(header)

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 4, 0, 4)
        self._rows_layout.setSpacing(4)
        self._rows_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self._rows_container)
        layout.addWidget(scroll, 1)

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Fail Gracefully, matching every other panel in this
        workstream: a transient RuntimeManager read failure keeps
        whatever rows were last displayed rather than clearing the
        panel or crashing the recurring QTimer callback."""
        try:
            runtime_manager = self._core_manager.runtime_manager()
            names = runtime_manager.names()
            states = {name: runtime_manager.state_of(name) for name in names}
        except Exception:
            logger.exception("Mission status panel refresh failed; keeping last displayed values.")
            return

        for stale_name in list(self._row_labels):
            if stale_name not in states:
                label = self._row_labels.pop(stale_name)
                self._rows_layout.removeWidget(label)
                label.deleteLater()

        for name, state in states.items():
            html = _row_html(name, state)
            if name in self._row_labels:
                self._row_labels[name].setText(html)
            else:
                label = QLabel(html)
                self._rows_layout.insertWidget(self._rows_layout.count() - 1, label)
                self._row_labels[name] = label
