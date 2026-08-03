"""PresentationHostWidget (Sprint 5.14 — Level 5 Part A).

The real UI-layer home for Level 5 Part A's whole graph — embedded into
`ui/main_window.py`'s `MainWindow` above the existing `StatusPanel`
(unchanged, not removed, not repurposed; see this sprint's own Engineering
Rationale). Asks `PresentationController` which persona's renderer is
currently mounted and shows the matching widget:

- Jarvis mounted -> embeds `JarvisRenderer.widget()` directly (the real
  holographic-core widget hierarchy, Sprint 5.7).
- Minie mounted -> embeds `MinieRenderer.status_widget()` (Sprint 5.14) —
  a small, honest connection-status readout, never a fake in-app avatar
  standing in for the real one, which renders inside the separately-
  running VTube Studio window per Sprint 5.8's own architecture.

This asymmetry is a direct, disclosed consequence of Sprint 5.8's own
architecture, not an oversight — see this sprint's own Engineering
Rationale for the full reasoning.

No signal/callback exists on `PresentationController` for "the mounted
renderer changed" (mount_renderer() is a plain, synchronous method with
no observer hook) — this widget polls `mounted_persona_name` on a
`QTimer`, the same cadence (`UIConfig.status_refresh_interval_ms`)
`StatusPanel`/`_SystemStatusPanel` already use, only swapping its
displayed child widget when the mounted persona actually changes (never
tearing down and rebuilding on every tick).
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation.jarvis_renderer import JarvisRenderer
from presentation.minie_renderer import MinieRenderer
from presentation.presentation_controller import PresentationController

logger = get_logger(__name__)


class PresentationHostWidget(QWidget):
    """Constructor DI: receives presentation_controller (5.6),
    jarvis_renderer (5.7), minie_renderer (5.8), and core_manager (its
    own refresh-cadence source)."""

    def __init__(
        self,
        presentation_controller: PresentationController,
        jarvis_renderer: JarvisRenderer,
        minie_renderer: MinieRenderer,
        core_manager: CoreManager,
    ) -> None:
        super().__init__()
        self._presentation_controller = presentation_controller
        self._jarvis_renderer = jarvis_renderer
        self._minie_renderer = minie_renderer
        self._displayed_persona_name: str | None = None
        self._displayed_widget: QWidget | None = None

        self._layout = QVBoxLayout(self)

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Fail Gracefully: a transient PresentationController read
        failure keeps whatever was last displayed, matching StatusPanel/
        _SystemStatusPanel's own established refresh() shape."""
        try:
            mounted_name = self._presentation_controller.mounted_persona_name
        except Exception:
            logger.exception("Presentation host refresh failed; keeping last displayed widget.")
            return
        if mounted_name == self._displayed_persona_name:
            return
        self._swap_displayed_widget(mounted_name)

    def _swap_displayed_widget(self, mounted_name: str | None) -> None:
        if self._displayed_widget is not None:
            self._layout.removeWidget(self._displayed_widget)
            self._displayed_widget.setParent(None)
            self._displayed_widget = None
        self._displayed_persona_name = mounted_name

        if mounted_name == "jarvis":
            self._displayed_widget = self._jarvis_renderer.widget()
        elif mounted_name == "minie":
            self._displayed_widget = self._minie_renderer.status_widget()
        else:
            return

        self._layout.addWidget(self._displayed_widget)
        self._displayed_widget.show()
