"""NetworkPanel — JARVIS Holographic HUD reskin, Phase 5.

The brief's own "Network Status" panel — Download/Upload/connection
status. Confirmed by this workstream's own research: no network probe
(`psutil.net_io_counters()` or otherwise) exists anywhere in this
codebase — `core.resource_monitor.ResourceMonitor` samples CPU/RAM/
Disk/Battery only. Per the brief's own explicit instruction ("If
metrics are unavailable, gracefully display: Unavailable. Do not
fabricate data."), this panel is static and honest rather than wired to
invented numbers or a live graph with nothing behind it.
"""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from presentation import theme


class NetworkPanel(QWidget):
    """No constructor collaborators — nothing in this codebase to poll."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QLabel("NETWORK STATUS")
        header.setStyleSheet(f"color: {theme.ACCENT_CYAN}; font-weight: 600;")
        layout.addWidget(header)

        body = QLabel("Unavailable")
        body.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        layout.addWidget(body)
        layout.addStretch(1)
