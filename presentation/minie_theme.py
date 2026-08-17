"""Minie Persona UI visual identity — palette, typography, and a
widget-scoped Qt stylesheet (Phase 1 of the Minie Persona UI
workstream, the sibling to the earlier JARVIS Holographic HUD reskin).

Tracked in code docstrings only, not docs/STATUS.md/sprint_book — same
out-of-band precedent presentation/theme.py's own docstring documents
for the Jarvis reskin and the earlier Runtime Refactor Sprint.

**Deliberately warm/companion-like, the opposite of theme.py's cold
cyan/blue HUD identity**: deep plum/near-black-purple backgrounds, a
neon-pink/rose primary accent, a lavender/violet secondary accent, soft
pink-white text — per the brief's own Color System section. Jarvis =
cold/technical/holographic/blue; Minie = warm/emotional/companion-like/
pink-purple/soft glass. The two personas must read as two different
interfaces belonging to the same AI system, not variations on one
palette.

**Not applied app-wide, unlike theme.apply_dark_theme()**: MainWindow
holds both HudShell (Jarvis) and MinieShell (Minie) as sibling pages of
one QStackedWidget (see ui/main_window.py), so a second
QApplication-wide palette/stylesheet call here would clobber Jarvis's
own theme for both personas regardless of which is mounted. Instead,
build_minie_stylesheet() returns a stylesheet MinieShell applies to
ITSELF via setStyleSheet() — Qt's own stylesheet cascade gives a
widget's own sheet precedence over an ancestor's for that widget and
its descendants, so this scopes cleanly to Minie's own subtree without
touching HudShell or anything outside MinieShell.

**PRIMARY_ACCENT/GLOW are one-time construction-time reads, not module
constants**: unlike the background/secondary/status colors below
(fixed identity, safe as plain module constants exactly like
theme.py's own reasoning), the accent and glow colors are
persona-identity-locked CONFIG values (PresentationConfig.
minie_ui_accent/minie_lighting_color) — the same "one-time read of a
locked identity value" precedent the Jarvis reskin's own Phase 9
established for jarvis_ui_accent/jarvis_lighting_color. Passed as
parameters to build_minie_stylesheet() rather than hardcoded, so a
config change retints Minie without a code change; PRIMARY_ACCENT_
DEFAULT/GLOW_DEFAULT below exist only as this module's own documented
fallback (matching config/defaults.yaml's own shipped values) for
callers that have no CoreManager handy (e.g. a unit test).
"""

from PySide6.QtGui import QColor

# --- Palette ---------------------------------------------------------

BG_VOID = "#0B0714"
"""The window's own outermost background — near-black with a deep
violet cast, the warm-persona counterpart to theme.BG_VOID's
near-black blue-black."""

BG_PANEL = "#1B1228"
BG_PANEL_RAISED = "#251A38"
"""Two panel fill shades with real contrast against BG_VOID — mirrors
theme.py's own BG_PANEL/BG_PANEL_RAISED reasoning exactly, just tinted
plum instead of blue-black."""

BORDER_DIM = "#3D2E52"
BORDER_ACCENT = "#FF7FB4"
"""A dim-but-visible lavender technical-line border most of the time
(BORDER_DIM); a bright neon-pink glow on hover/active/focus
(BORDER_ACCENT) — Minie's "soft pink borders... subtle neon glow"
counterpart to theme.py's BORDER_DIM/BORDER_ACCENT."""

SECONDARY_ACCENT = "#B79CE8"
"""Lavender/violet secondary accent — the brief's own "Secondary
accent: lavender, violet, soft purple" category, distinct from the
config-driven PRIMARY_ACCENT (below) so a UI element can read as
"Minie-family" without being the one identity-locked primary color."""

TEXT_PRIMARY = "#F5EAFB"
TEXT_SECONDARY = "#B8A2CC"
TEXT_DIM = "#5E4E76"
"""Soft pink-white primary text, a dimmer lavender-gray for secondary/
label text, a near-invisible tertiary shade for disabled/placeholder
text — the same three-step discipline theme.py's own TEXT_PRIMARY/
TEXT_SECONDARY/TEXT_DIM already established, per section 28's
accessibility requirement."""

STATUS_GREEN = "#4ADE80"
STATUS_AMBER = "#FBBF24"
STATUS_RED = "#FB7185"
STATUS_GRAY = "#8B7A9B"
"""Healthy/warning/critical/idle — the same four-color status
vocabulary theme.py's own STATUS_* constants establish, softened to sit
comfortably against Minie's warmer palette. Every status indicator also
carries a distinct shape/label, never color alone (section 28)."""

FONT_FAMILY = "Segoe UI"
FONT_FAMILY_MONO = "Consolas"
"""Identical font choice to theme.py, deliberately — "futuristic but
readable" applies to both personas equally; only color/shape identity
differs between them."""

PRIMARY_ACCENT_DEFAULT = "#B76E79"
GLOW_DEFAULT = "#C8A8E9"
"""Fallback values matching config/defaults.yaml's own
presentation.minie_ui_accent/minie_lighting_color shipped defaults —
used only by callers with no CoreManager handy (tests, previews). Real
construction always reads the live config value; see this module's own
docstring."""


def build_minie_stylesheet(accent_color: str = PRIMARY_ACCENT_DEFAULT) -> str:
    """Returns a Qt stylesheet scoped to whatever widget it's applied
    to (MinieShell.setStyleSheet(...) — see this module's own
    docstring for why this is never applied app-wide). accent_color is
    the one-time construction-time read of PresentationConfig.
    minie_ui_accent (see this module's own docstring) — every other
    color comes from this module's own fixed identity constants above.
    """
    return f"""
QWidget {{
    background-color: {BG_VOID};
    color: {TEXT_PRIMARY};
    font-family: '{FONT_FAMILY}';
    font-size: 10pt;
}}
QLabel {{
    background: transparent;
}}
QPushButton {{
    background-color: {BG_PANEL_RAISED};
    border: 1px solid {BORDER_DIM};
    border-radius: 14px;
    padding: 6px 14px;
    color: {TEXT_PRIMARY};
}}
QPushButton:hover {{
    border: 1px solid {accent_color};
    color: {accent_color};
}}
QPushButton:pressed {{
    background-color: {BG_PANEL};
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    border: 1px solid {BG_PANEL_RAISED};
}}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_DIM};
    border-radius: 16px;
    padding: 6px 14px;
    color: {TEXT_PRIMARY};
    selection-background-color: {accent_color};
    selection-color: {BG_VOID};
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {accent_color};
}}
QScrollArea {{
    border: none;
    background: transparent;
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


def accent_qcolor(accent_color: str = PRIMARY_ACCENT_DEFAULT) -> QColor:
    """A small convenience so QPainter-based widgets (avatar_stage.py's
    glow/particles) don't each re-wrap the same string in QColor()."""
    return QColor(accent_color)
