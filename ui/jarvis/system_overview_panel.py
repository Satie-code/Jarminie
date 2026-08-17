"""SystemOverviewPanel — JARVIS Holographic HUD reskin, Phase 5.

The brief's own "System Overview" panel: CPU/RAM/GPU/DISK donut
gauges. CPU/RAM/DISK come from `MetricsAdapter`'s
`resources_updated` signal (ultimately `core.resource_monitor.
ResourceMonitor.sample()`, the exact same probe `ui/status_panel.py`'s
`StatusPanel` already used — this panel supersedes that panel's role in
the dashboard, not its underlying data source). GPU has no real value
to show: `ResourceMonitor` never gathers one (psutil has no GPU
support, a documented limitation), so it's wired to `CircularMetric.
set_value(None)` — a permanent, honest "N/A", never fabricated.
"""

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from core.resource_monitor import ResourceSnapshot
from presentation import theme
from ui.jarvis.metrics_adapter import MetricsAdapter
from ui.jarvis.widgets.circular_metric import CircularMetric


class SystemOverviewPanel(QWidget):
    """Constructor DI: only MetricsAdapter — this panel never touches
    CoreManager directly, keeping exactly one shared poller per section
    25's own resource-conscious mandate (see that module's own
    docstring)."""

    def __init__(self, metrics_adapter: MetricsAdapter, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QLabel("SYSTEM OVERVIEW")
        header.setStyleSheet(f"color: {theme.ACCENT_CYAN}; font-weight: 600;")
        layout.addWidget(header)

        self._cpu = CircularMetric("CPU")
        self._ram = CircularMetric("RAM")
        self._gpu = CircularMetric("GPU")
        self._disk = CircularMetric("DISK")
        self._gpu.set_value(None)  # never has real data — see this module's own docstring

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.addWidget(self._cpu, 0, 0)
        grid.addWidget(self._ram, 0, 1)
        grid.addWidget(self._gpu, 1, 0)
        grid.addWidget(self._disk, 1, 1)
        layout.addLayout(grid)

        metrics_adapter.resources_updated.connect(self._on_resources_updated)

    def _on_resources_updated(self, snapshot: ResourceSnapshot) -> None:
        self._cpu.set_value(snapshot.cpu_percent)
        self._ram.set_value(snapshot.ram_percent)
        self._disk.set_value(snapshot.disk_percent)
