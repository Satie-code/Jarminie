"""ActiveModulesPanel — JARVIS Holographic HUD reskin, Phase 5.

The brief's own "Active Modules" panel: "Module — STATE" rows. Sourced
from `MetricsAdapter`'s `runtime_updated` signal (ultimately
`RuntimeManager`, the same real per-service tier/lazy/state bookkeeping
`ui/runtime_diagnostics_panel.py`'s own `RuntimeDiagnosticsPanel`
already reads) — every registered service's own real name and real
`ServiceState`, the identical honesty discipline
`ui/jarvis/mission_status_panel.py` already established for the left
rail's own status list (see that module's own docstring for why the
brief's own example labels aren't used verbatim). The two panels read
the same underlying data by design — the reference image itself shows
two distinct "what's running" panels in two different locations, not
something this workstream invented.
"""

from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from core.module_registry import ServiceState
from presentation import theme
from ui.jarvis.metrics_adapter import MetricsAdapter

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
        f'<span style="color:{theme.TEXT_PRIMARY};">{name}</span>'
        f'<span style="color:{theme.TEXT_DIM};"> — </span>'
        f'<span style="color:{color}; font-weight:600;">{state.value.upper()}</span>'
    )


class ActiveModulesPanel(QWidget):
    """Constructor DI: only MetricsAdapter — see that module's own
    docstring for why this panel doesn't run its own CoreManager poll."""

    def __init__(self, metrics_adapter: MetricsAdapter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QLabel("ACTIVE MODULES")
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

        metrics_adapter.runtime_updated.connect(self._on_runtime_updated)

    def _on_runtime_updated(self, states: dict[str, ServiceState]) -> None:
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
