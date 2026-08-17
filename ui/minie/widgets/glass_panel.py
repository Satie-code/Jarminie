"""GlassPanel — Minie Persona UI workstream.

The one reusable "translucent glass panel" container every ui/minie/
panel builds on — the brief's own "translucent glass panels, rounded
corners, soft pink borders, subtle neon glow" visual language, factored
out once rather than each panel file re-deriving it. Generalizes
ui/jarvis/hud_shell.py's own private `_Zone` helper (a per-zone-only,
module-private container) into a real, public, reusable widget, since
Minie's UI is composed of many more distinct panel types than Jarvis's
five fixed zones.

Each instance gets its own unique object name (a plain incrementing
counter) so its own scoped `#name { ... }` stylesheet rule doesn't
collide with any other GlassPanel instance — the same per-widget
`setObjectName()` + ID-selector-stylesheet shape `_Zone` already used,
generalized to many instances rather than five fixed ones.
"""

import itertools

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from presentation import minie_theme

_instance_counter = itertools.count()


class GlassPanel(QWidget):
    """glow=True gives the panel a bright accent-colored border instead
    of the default dim lavender one — used for a panel that should read
    as emotionally "warmer"/more prominent (e.g. the avatar stage's own
    surrounding chrome), never for routine panels."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        glow: bool = False,
        accent_color: str = minie_theme.PRIMARY_ACCENT_DEFAULT,
        border_radius: int = 18,
    ) -> None:
        super().__init__(parent)
        object_name = f"minie_glass_panel_{next(_instance_counter)}"
        self.setObjectName(object_name)
        # A plain QWidget subclass paints nothing of its own — without
        # WA_StyledBackground, "background-color"/"border" QSS rules are
        # silently ignored and whatever's beneath shows through instead.
        # The identical gotcha ui/jarvis/hud_shell.py's own _Zone
        # docstring already documents finding via a real screenshot.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        border_color = accent_color if glow else minie_theme.BORDER_DIM
        self.setStyleSheet(
            f"#{object_name} {{"
            f" background-color: {minie_theme.BG_PANEL};"
            f" border: 1px solid {border_color};"
            f" border-radius: {border_radius}px;"
            f" }}"
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(8)

    def layout_(self) -> QVBoxLayout:
        """Named layout_() rather than overriding QWidget.layout()
        (already exists, incompatible no-argument C++ signature) — the
        same naming precedent ui/jarvis/hud_shell.py's own _Zone.layout_()
        already established."""
        return self._layout
