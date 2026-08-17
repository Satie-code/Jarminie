"""MinieRelationshipPanel — Minie Persona UI workstream.

The reference image's own "You & Minie" panel — three stat tiles: Chats,
Cups Coffee Together, Songs Vibed. Confirmed by this workstream's own
prior research: this codebase has no real per-conversation "chat count"
analytics, no "coffee" concept anywhere, and no "songs" tracking at all
(only unrelated app-focus-time analytics exist in `analytics/`, which
would misleadingly represent something else entirely if repurposed
here). Per this workstream's own resolved decision, fabricating numbers
for these three is explicitly forbidden — every tile shows an honest
em dash ("—") instead, plus a small disclosed caption ("Not tracked yet
♡"), the same "disclosed gap, not fabricated" habit
`ui/jarvis/network_panel.py`'s own docstring already establishes for
Jarvis's Network Status panel.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from presentation import minie_theme
from ui.minie.widgets.glass_panel import GlassPanel

_TILE_LABELS = ("Chats", "Cups Coffee Together", "Songs Vibed")


class MinieRelationshipPanel(QWidget):
    """No constructor collaborators — deliberately: nothing in this
    codebase backs any of the three tiles below (see this module's own
    docstring), so there is nothing to poll and no QTimer is started."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        panel = GlassPanel(self)
        outer_layout.addWidget(panel)

        header = QLabel("You & Minie")
        header.setStyleSheet(f"color: {minie_theme.PRIMARY_ACCENT_DEFAULT}; font-weight: 600;")
        panel.layout_().addWidget(header)

        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(12)
        for tile_label in _TILE_LABELS:
            tiles_row.addWidget(self._build_tile(tile_label))
        panel.layout_().addLayout(tiles_row)

        caption = QLabel("Not tracked yet ♡")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY}; font-size: 8pt;")
        panel.layout_().addWidget(caption)

    def _build_tile(self, label_text: str) -> QWidget:
        tile = QWidget()
        tile_layout = QVBoxLayout(tile)
        tile_layout.setContentsMargins(0, 0, 0, 0)
        tile_layout.setSpacing(2)

        value_label = QLabel("—")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setStyleSheet(
            f"color: {minie_theme.TEXT_PRIMARY}; font-size: 18pt; font-weight: 600;"
        )
        tile_layout.addWidget(value_label)

        caption_label = QLabel(label_text)
        caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption_label.setWordWrap(True)
        caption_label.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY};")
        tile_layout.addWidget(caption_label)

        return tile
