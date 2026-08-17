"""MinieNotesPanel — Minie Persona UI workstream.

The reference image's own "Quick Notes" panel — a small checkable list
plus an add button (e.g. "✓ Learn something new / ○ Plan next project /
○ Spend time with loved ones"). Deliberately SESSION-ONLY, in-memory
storage: this codebase has no notes/task backend anywhere (confirmed by
investigation before this workstream began), and building one is
explicitly out of scope for this round — a resolved architectural
decision for this workstream, not an oversight. State lives entirely in
this widget's own `_notes` list and resets on every app restart; this is
an honest, disclosed gap rather than a fabricated persistence layer,
matching this codebase's own "disclosed gap, not fabricated"
documentation habit. This class is a presentation-level stub, shaped so
a future sprint can swap the in-memory list for a real store without
changing how any caller constructs or uses this widget.
"""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from presentation import minie_theme
from ui.minie.widgets.glass_panel import GlassPanel

_STARTER_NOTES: list[str] = [
    "Learn something new",
    "Plan next project",
    "Spend time with loved ones",
]
"""Seeded at construction so a brand-new, never-used panel doesn't show
an empty, uninviting list — the honest, reasonable choice for a
session-only stub with no persistence (see this module's own docstring).
A module-level constant so it's easy to find/change."""


@dataclass
class NoteItem:
    text: str
    done: bool = False


class _NoteRow(QWidget):
    """One note row: a clickable checkmark/circle glyph (✓ if done else
    ○) followed by the note's own text, struck through and dimmed once
    done. Owns its own NoteItem and re-renders itself on toggle — no
    parent callback needed, since toggling a single note's done state
    never changes the panel's own list membership or ordering."""

    def __init__(self, note: NoteItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._note = note

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)

        self._check_button = QPushButton()
        self._check_button.setFixedSize(22, 22)
        self._check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check_button.clicked.connect(self._toggle)

        self._text_label = QLabel()
        self._text_label.setWordWrap(True)

        layout.addWidget(self._check_button)
        layout.addWidget(self._text_label, 1)

        self._render()

    def _toggle(self) -> None:
        self._note.done = not self._note.done
        self._render()

    def _render(self) -> None:
        self._check_button.setText("✓" if self._note.done else "○")
        glyph_color = minie_theme.STATUS_GREEN if self._note.done else minie_theme.SECONDARY_ACCENT
        self._check_button.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 0px; background: transparent;"
            f" color: {glyph_color}; font-size: 13pt; padding: 0px; }}"
        )

        text_color = minie_theme.TEXT_DIM if self._note.done else minie_theme.TEXT_PRIMARY
        decoration = "line-through" if self._note.done else "none"
        self._text_label.setStyleSheet(
            f"color: {text_color}; text-decoration: {decoration}; border: none;"
        )
        self._text_label.setText(self._note.text)


class MinieNotesPanel(QWidget):
    """Constructor DI: (parent,) only — deliberately no backend
    collaborator (see this module's own docstring)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._notes: list[NoteItem] = [NoteItem(text=text) for text in _STARTER_NOTES]

        self._panel = GlassPanel(self)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self._panel)

        header_label = QLabel("Quick Notes")
        header_label.setStyleSheet(
            f"color: {minie_theme.TEXT_PRIMARY}; font-size: 11pt; font-weight: 700; border: none;"
        )

        self._add_button = QPushButton("+")
        self._add_button.setFixedSize(24, 24)
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_button.setStyleSheet(
            f"QPushButton {{ border-radius: 12px; border: 1px solid {minie_theme.BORDER_ACCENT};"
            f" background-color: {minie_theme.BG_PANEL_RAISED};"
            f" color: {minie_theme.BORDER_ACCENT}; font-weight: 700; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {minie_theme.BG_PANEL}; }}"
        )
        self._add_button.clicked.connect(self._toggle_add_field)

        header_row = QHBoxLayout()
        header_row.addWidget(header_label)
        header_row.addStretch(1)
        header_row.addWidget(self._add_button)

        self._add_input = QLineEdit()
        self._add_input.setPlaceholderText("Add a note...")
        self._add_input.returnPressed.connect(self._commit_new_note)

        self._confirm_button = QPushButton("Add")
        self._confirm_button.clicked.connect(self._commit_new_note)

        add_row = QHBoxLayout()
        add_row.addWidget(self._add_input, 1)
        add_row.addWidget(self._confirm_button)
        self._add_container = QWidget()
        self._add_container.setLayout(add_row)
        self._add_container.setVisible(False)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(4)

        self._panel.layout_().addLayout(header_row)
        self._panel.layout_().addWidget(self._add_container)
        self._panel.layout_().addLayout(self._rows_layout)

        self._render_rows()

    def _toggle_add_field(self) -> None:
        showing = not self._add_container.isVisible()
        self._add_container.setVisible(showing)
        if showing:
            self._add_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _commit_new_note(self) -> None:
        text = self._add_input.text().strip()
        if not text:
            return
        self._notes.append(NoteItem(text=text))
        self._add_input.clear()
        self._add_container.setVisible(False)
        self._render_rows()

    def _render_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for note in self._notes:
            self._rows_layout.addWidget(_NoteRow(note))
