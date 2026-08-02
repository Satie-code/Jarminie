"""JarvisRenderer (Sprint 5.7 — Level 5 Part A).

The first concrete `Renderer` (Sprint 5.6): Jarvis's holographic core —
a central translucent sphere (`HolographicSphereWidget`), a segmented
ring visualizing turn-phase (`SegmentedRingWidget`), and a real,
profile-driven dashboard-panel area (Sprint 5.12's own
`apply_workspace_profile()`, replacing what was a placeholder container
through Sprint 5.11). Entirely native `QPainter`/`QWidget` — no QML, no
`QGraphicsView`/`QGraphicsScene`, per the locked rendering decision
(`docs/sprint_book/INDEX.md`'s "Level 5 breakdown changes" note).

**A real, honestly-named gap**: `PresentationState` (Sprint 5.5) carries
`avatar_focus` (`"user"`/`"task"`/`"idle"`) but nothing that
distinguishes Listening from Thinking from Speaking from Processing —
those four are turn-phase signals belonging to `voice/quiet_mode.py`'s
`OperatingMode`/`voice/session_manager.py`'s own session lifecycle, not
to the emotional/persona state `PresentationStateComputer` was built to
compute. `_derive_ring_state()` below is therefore deliberately narrow
this sprint: `avatar_focus == "idle"` maps to `RingState.IDLE`,
everything else maps to a single generic `RingState.PROCESSING`. Real
per-phase ring states (`LISTENING` while capturing audio, `THINKING`
while the Decision Engine pipeline runs, `SPEAKING` while TTS plays)
need a real turn-phase signal threaded in — **not built here, real
work for Sprint 5.14** (Presentation Layer Integration), where
`CommunicationPipeline`'s own real turn-phase transitions become
available to wire through.

**Widget construction is deliberately lazy** — never at `__init__`
time, since a `QWidget` must not be constructed before a `QApplication`
exists, and `JarvisRenderer` is constructed at `main.py`'s composition-root
time (before `ui/app.py`'s `run_app()` constructs the real
`QApplication`). Both `mount()` and `widget()` trigger the same
one-time lazy build via `_ensure_widgets_built()`, so Sprint 5.14 can
call `widget()` first (to embed into `MainWindow`'s layout at startup)
and `mount()` later (once this persona becomes active) without forcing
a particular call order.

No live embedding into `ui/main_window.py` this sprint (Sprint 5.14's
job).

**`trigger_gesture()` (Sprint 5.9)**: a deliberately narrow, honestly
disclosed interpretation. Jarvis's own locked visual vocabulary is "a
single subtle ring/dashboard accent" (the brief's own restraint) —
rather than invent a second, Jarvis-specific mapping from `gesture_id`
to a distinct visual effect, `trigger_gesture()` applies one uniform,
config-timed accent pulse (`SegmentedRingWidget.trigger_pulse()`)
regardless of which `gesture_id` `GestureEngine` chose upstream. The
`gesture_id` itself is still logged (useful for debugging which
trigger fired) and still exists as a real, distinct value for a future
sprint to differentiate against — Minie's own `AvatarRenderer.
trigger_gesture()` path already can, since it forwards the id verbatim
to whatever real Live2D hotkey the user's own model defines.

**`apply_workspace_profile()` (Sprint 5.12)**: an independent update
path from `render_state()` (that sprint's own Architecture Notes) —
never called from it, always called from a separate trigger
(`AdaptiveWorkspaceController`'s own future live caller, Sprint 5.14).
Rebuilds the dashboard-panel area for a given `WorkspaceProfile`: the
real, live `_SystemStatusPanel` below (always present, every profile)
plus one profile-specific placeholder panel (absent for `GENERAL`, its
own safe-failure role — see `presentation/adaptive_workspace.py`'s own
docstring). `_SystemStatusPanel` is a genuinely **thin adapter**, per
this sprint's own Integration Considerations: it reuses `CoreManager`'s
own existing data source (`module_states()`/`check_resources()`/
`ui_config()`, the exact same calls `ui/status_panel.py`'s own
`StatusPanel` already makes) directly — it does NOT import or wrap
`StatusPanel` itself. `presentation/` must never depend on `ui/`; that
dependency runs the other way (`ui/main_window.py` is what will embed
this renderer's own `widget()` at Sprint 5.14) — importing `StatusPanel`
here would invert it. The per-profile placeholder panels (Coding
Workspace / Research Notes / Study Session / Project Status) are
honestly empty content this sprint — real per-profile data sources
(`WorkflowStore` for Project Status, `ResearchEngine` for Research
Notes, etc.) are outside this sprint's own named Dependencies (only 5.7
and 3.8) and are real future content work (Future Considerations), not
built speculatively here.
"""

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from config.schema import PresentationConfig
from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation.adaptive_workspace import WorkspaceProfile
from presentation.presentation_state import AVATAR_FOCUS_IDLE, PresentationState
from presentation.widgets.holographic_sphere_widget import HolographicSphereWidget
from presentation.widgets.segmented_ring_widget import RingState, SegmentedRingWidget

logger = get_logger(__name__)

_WORKSPACE_PANEL_TITLES: dict[WorkspaceProfile, str] = {
    WorkspaceProfile.CODING: "Coding Workspace",
    WorkspaceProfile.RESEARCH: "Research Notes",
    WorkspaceProfile.STUDY: "Study Session",
    WorkspaceProfile.PROJECTS: "Project Status",
}
"""GENERAL deliberately has no entry — its own panel set is the system
status panel alone, matching its role as the safe-failure default (see
presentation/adaptive_workspace.py's own Architecture Notes)."""


class _SystemStatusPanel(QWidget):
    """A thin, presentation-owned read-only adapter over CoreManager's
    own existing data source — reuses module_states()/check_resources()/
    ui_config() directly, the same calls ui/status_panel.py's own
    StatusPanel already makes, without importing or wrapping that class
    (see this module's own docstring for why). Deliberately minimal — a
    live one-line summary, not a full reimplementation of StatusPanel's
    own richer per-module display."""

    def __init__(self, core_manager: CoreManager) -> None:
        super().__init__()
        self._core_manager = core_manager
        self._label = QLabel()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>System Status</b>"))
        layout.addWidget(self._label)

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Same Fail Gracefully shape as StatusPanel.refresh() — a
        transient CoreManager read failure is logged and the display
        simply keeps its last-known-good text, never crashes the
        recurring QTimer callback."""
        try:
            states = self._core_manager.module_states()
            snapshot = self._core_manager.check_resources()
        except Exception:
            logger.exception("System status panel refresh failed; keeping last displayed values.")
            return
        running = sum(1 for state in states.values() if state == "running")
        self._label.setText(
            f"{running}/{len(states)} modules running   "
            f"CPU: {snapshot.cpu_percent:.0f}%   RAM: {snapshot.ram_percent:.0f}%"
        )


def _build_placeholder_panel(title: str) -> QWidget:
    """A small, honest placeholder — see this module's own docstring for
    why real per-profile data isn't wired in this sprint."""
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.addWidget(QLabel(f"<b>{title}</b>"))
    layout.addWidget(QLabel("Coming soon."))
    return panel


def _derive_ring_state(state: PresentationState) -> RingState:
    """This sprint's own deliberately narrow, honestly-limited mapping —
    see this module's own docstring for the real gap this leaves."""
    if state.avatar_focus == AVATAR_FOCUS_IDLE:
        return RingState.IDLE
    return RingState.PROCESSING


class JarvisRenderer:
    """Constructor DI per 03_Engineering_Standards.md: receives the
    PresentationConfig it reads the locked Jarvis palette and
    ring/timer settings from — no direct EmotionalStateManager/
    PresentationController reference, keeping this a pure consumer of
    whatever PresentationState it's handed via render_state(), per
    Sprint 5.6's own "renderers consume, they do not determine"
    contract. Implements Renderer (presentation/renderer.py)
    structurally (Protocol, no explicit inheritance needed).

    core_manager (Sprint 5.12, required) is _SystemStatusPanel's own
    real data source — a real, necessary constructor addition beyond
    this class's own original signature, the same "found a real gap,
    resolved it directly, disclosed it here" precedent PresentationController's
    own Sprint 5.6/5.9/5.10 additions already used."""

    def __init__(self, presentation_config: PresentationConfig, core_manager: CoreManager) -> None:
        self._config = presentation_config
        self._core_manager = core_manager
        self._container: QWidget | None = None
        self._sphere: HolographicSphereWidget | None = None
        self._ring: SegmentedRingWidget | None = None
        self._panel_container: QWidget | None = None
        self._timer: QTimer | None = None
        self._mounted = False
        self._current_workspace_profile: WorkspaceProfile | None = None

    def widget(self) -> QWidget:
        """The top-level container widget (sphere + ring + dashboard-panel
        area) for embedding — ui/main_window.py's own accessor at Sprint
        5.14. Lazily builds the widget hierarchy on first call if
        mount() hasn't already (see this module's own docstring)."""
        self._ensure_widgets_built()
        return self._container

    def mount(self) -> None:
        """Idempotent and safe to call multiple times or out of order
        (this sprint's own Acceptance Criteria): builds the widget
        hierarchy on first call only, then (re)starts the shared
        animation timer. Does not itself show/embed the widget — that
        is whichever parent layout it's added into (Sprint 5.14)."""
        self._ensure_widgets_built()
        if self._mounted:
            return
        self._mounted = True
        self._timer.start()
        logger.info("Jarvis Renderer mounted.")

    def unmount(self) -> None:
        """Idempotent and safe to call multiple times, before mount(),
        or after mount() already failed. Stops the animation timer
        entirely (Potential Risks: "an unmounted Jarvis renderer...
        consumes no CPU at all") and hides the container — cheaply
        re-mountable, never destroyed, so a brief interruption (Sprint
        5.10's TransitionEngine switching back shortly after switching
        away) doesn't pay a full teardown/rebuild cost."""
        if not self._mounted:
            return
        self._timer.stop()
        self._container.hide()
        self._mounted = False
        logger.info("Jarvis Renderer unmounted.")

    def render_state(self, state: PresentationState) -> None:
        """Updates each child widget's own target values — never calls
        update()/repaint() directly (Sprint 5.6's own Protocol contract:
        render_state() must be cheap/non-blocking; actual repaints are
        scheduled solely by the shared QTimer loop's own _on_tick()
        calls). A no-op (logged) if called before mount()/widget() ever
        built the widget hierarchy."""
        if self._sphere is None or self._ring is None:
            logger.warning("render_state() called before the widget hierarchy exists; ignoring.")
            return
        color = QColor(state.lighting_color)
        self._sphere.set_target(color, state.animation_speed)
        self._ring.set_color(color)
        self._ring.set_ring_state(_derive_ring_state(state), state.animation_speed)

    def trigger_gesture(self, gesture_id: str) -> None:
        """One uniform accent pulse on the segmented ring — see this
        module's own docstring for why gesture_id's content itself is
        not differentiated here. A no-op (logged) if called before the
        widget hierarchy exists, matching render_state()'s own contract."""
        if self._ring is None:
            logger.warning(
                "trigger_gesture(%s) called before the widget hierarchy exists; ignoring.",
                gesture_id,
            )
            return
        self._ring.trigger_pulse(self._config.jarvis_gesture_pulse_ticks)
        logger.info("Jarvis Renderer gesture triggered: %s.", gesture_id)

    def apply_workspace_profile(self, profile: WorkspaceProfile) -> None:
        """Rebuilds the dashboard-panel area for profile — see this
        module's own docstring for the real/placeholder panel split. An
        independent update path from render_state() (Sprint 5.12's own
        Architecture Notes), never called from it."""
        self._ensure_widgets_built()
        self._current_workspace_profile = profile
        self._clear_panel_container()
        layout = self._panel_container.layout()
        layout.addWidget(_SystemStatusPanel(self._core_manager))
        title = _WORKSPACE_PANEL_TITLES.get(profile)
        if title is not None:
            layout.addWidget(_build_placeholder_panel(title))
        logger.info("Jarvis Renderer workspace profile applied: %s.", profile.value)

    def _clear_panel_container(self) -> None:
        layout = self._panel_container.layout()
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _ensure_widgets_built(self) -> None:
        if self._container is not None:
            return
        self._container = QWidget()
        layout = QVBoxLayout(self._container)
        self._sphere = HolographicSphereWidget(self._container)
        self._ring = SegmentedRingWidget(self._config.jarvis_ring_segment_count, self._container)
        self._panel_container = QWidget(self._container)
        QVBoxLayout(self._panel_container)  # populated by apply_workspace_profile() (Sprint 5.12)
        layout.addWidget(self._sphere)
        layout.addWidget(self._ring)
        layout.addWidget(self._panel_container)

        self._timer = QTimer(self._container)
        self._timer.setInterval(self._config.jarvis_animation_tick_ms)
        self._timer.timeout.connect(self._on_tick)

    def _on_tick(self) -> None:
        # JarvisRenderer owns the one shared QTimer by design (Potential
        # Risks: two timers would double this widget's own resource
        # cost) — both child widgets' own _on_tick() are meant to be
        # called only from here, matching this sprint's own Data Flow
        # diagram exactly.
        self._sphere._on_tick()
        self._ring._on_tick()
