"""JARVIS HUD visual identity — palette, typography, and the app-wide
Qt stylesheet (Phase 1 of the JARVIS Holographic HUD reskin workstream).

Tracked in code docstrings only, not docs/STATUS.md/sprint_book — this
workstream reskins the desktop shell on top of the already-frozen Master
Sprint Book (Level 6), the same out-of-band-tracking precedent the
earlier Runtime Refactor Sprint established. See the workstream's own
plan for full phase history.

Deliberately predominantly BLACK + CYAN + BLUE + WHITE, per the
reference brief's own Global Color System: a near-black/blue-black
background, electric-cyan primary accent, cool-blue secondary accent,
pale-blue-white text, and a small fixed set of status colors (green/
amber/red/gray) — never an arbitrary or expanding palette. Every
JARVIS-chrome file (presentation/ widgets and ui/jarvis/ panels alike)
imports its colors from here rather than hardcoding a hex literal, so
the whole HUD can be retinted from one place.

Colors are plain module-level constants (not a dataclass/enum) so both
`QColor(theme.ACCENT_CYAN)` (procedural QPainter widgets) and plain
f-string interpolation into a Qt stylesheet (ordinary QWidget chrome)
read them identically without a wrapper.
"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# --- Palette -------------------------------------------------------------

BG_VOID = "#02040A"
"""The window's own outermost background — near-black, per the brief's
own "near-black background" / "very dark blue-black surfaces" wording."""

BG_PANEL = "#0B1520"
BG_PANEL_RAISED = "#132436"
"""Two panel fill shades, deliberately given real contrast against
BG_VOID (not just a few RGB points apart) — the reference image's own
panels read as clearly separate surfaces floating over the void, not a
uniformly-dark screen with text on it. BG_PANEL for a resting HUD panel,
BG_PANEL_RAISED for a panel/control that should read as slightly
"closer" (buttons, an active nav item, a hovered row)."""

BORDER_DIM = "#1E4258"
BORDER_ACCENT = "#3FC4E8"
"""A dim-but-visible cyan-tinted technical-line border most of the time
(BORDER_DIM); a bright, near-ACCENT_CYAN glow on hover/active/focus
(BORDER_ACCENT) — "thin luminous borders" per the brief. BORDER_DIM is
deliberately brighter than a barely-there border would suggest: at the
near-black BG_VOID/BG_PANEL end of the palette, a truly subtle border
disappears entirely rather than reading as "subtle" once rendered."""

ACCENT_CYAN = "#22D3EE"
ACCENT_BLUE = "#0A84FF"
"""The brief's own two named accents — electric cyan primary, cool blue
secondary. Matches presentation/jarvis_state_computer.py's already-locked
Jarvis identity palette (jarvis_ui_accent/jarvis_lighting_color in
config/schema.py's PresentationConfig) exactly, on purpose: the new HUD
chrome and the existing hologram must read as one coherent system, not
two independently-tinted halves of the screen."""

TEXT_PRIMARY = "#E6F1FF"
TEXT_SECONDARY = "#7C93AD"
TEXT_DIM = "#3E5062"
"""Pale blue-white primary text, a dimmer blue-gray for secondary/label
text, and a near-invisible tertiary shade for disabled/placeholder text
— three steps, not an open-ended set, per section 28's "sufficient
contrast" accessibility requirement."""

STATUS_GREEN = "#2ED573"
STATUS_AMBER = "#FFB020"
STATUS_RED = "#FF4D4D"
STATUS_GRAY = "#5A7086"
"""Healthy/operational, warning, critical, idle/unavailable — the brief's
own four-color status vocabulary. Every status indicator in this HUD
also carries a distinct shape/label (never color alone), per section
28's "no critical information communicated solely through color" rule —
enforced by each consuming widget, not by this module."""

FONT_FAMILY = "Segoe UI"
FONT_FAMILY_MONO = "Consolas"
"""A readable system sans-serif for prose/labels, a monospace face for
numeric HUD readouts (clock, metrics) where digit-width jitter would
read as visually noisy. Deliberately ordinary, licensed-for-Windows
system fonts — "futuristic but readable," per the brief's own Top-Left
Branding section, never a decorative font that damages legibility."""


def apply_dark_theme(app: QApplication) -> None:
    """Applies the JARVIS palette app-wide: a QPalette (so native dialogs
    / unstyled corners default sanely) plus a global stylesheet (for the
    actual HUD look). Called once, from ui/app.py's run_app(), right
    after QApplication is constructed and before any widget — so every
    widget built afterward, including third-party-styled ones like
    QMessageBox, picks up the theme from its very first paint."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_VOID))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_PANEL))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_PANEL_RAISED))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(BG_PANEL_RAISED))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_CYAN))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(BG_VOID))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_PANEL_RAISED))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_DIM))
    app.setPalette(palette)
    app.setStyleSheet(_STYLESHEET)


_STYLESHEET = f"""
QWidget {{
    background-color: {BG_VOID};
    color: {TEXT_PRIMARY};
    font-family: '{FONT_FAMILY}';
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background-color: {BG_VOID};
}}
QGroupBox {{
    border: 1px solid {BORDER_DIM};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    color: {TEXT_SECONDARY};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {ACCENT_CYAN};
}}
QLabel {{
    background: transparent;
}}
QPushButton {{
    background-color: {BG_PANEL_RAISED};
    border: 1px solid {BORDER_DIM};
    border-radius: 4px;
    padding: 6px 12px;
    color: {TEXT_PRIMARY};
}}
QPushButton:hover {{
    border: 1px solid {ACCENT_CYAN};
    color: {ACCENT_CYAN};
}}
QPushButton:pressed {{
    background-color: {BG_PANEL};
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    border: 1px solid {BG_PANEL_RAISED};
}}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_DIM};
    border-radius: 4px;
    padding: 4px 6px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_CYAN};
    selection-color: {BG_VOID};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT_CYAN};
}}
QSplitter::handle {{
    background-color: {BORDER_DIM};
}}
QMenuBar {{
    background-color: {BG_VOID};
    color: {TEXT_SECONDARY};
}}
QMenuBar::item:selected {{
    background-color: {BG_PANEL_RAISED};
    color: {ACCENT_CYAN};
}}
QMenu {{
    background-color: {BG_PANEL};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DIM};
}}
QMenu::item:selected {{
    background-color: {BG_PANEL_RAISED};
    color: {ACCENT_CYAN};
}}
QScrollBar:vertical {{
    background: {BG_VOID};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_DIM};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BORDER_ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""
