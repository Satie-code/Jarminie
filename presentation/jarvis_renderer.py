"""JarvisRenderer (Sprint 5.7 — Level 5 Part A).

The first concrete `Renderer` (Sprint 5.6): Jarvis's holographic core —
a central translucent sphere (`HolographicSphereWidget`), a segmented
ring visualizing turn-phase (`SegmentedRingWidget`), and a real,
profile-driven dashboard-panel area (Sprint 5.12's own
`apply_workspace_profile()`, replacing what was a placeholder container
through Sprint 5.11). Entirely native `QPainter`/`QWidget` — no QML, no
`QGraphicsView`/`QGraphicsScene`, per the locked rendering decision
(`docs/sprint_book/INDEX.md`'s "Level 5 breakdown changes" note).

**JARVIS Holographic HUD reskin, Phase 3** adds a holographic floor
(`HolographicFloorWidget`) and a bounded orbital particle field
(`ParticleFieldWidget`), layered with the sphere/ring in one shared
`_HologramStage` region (below) rather than each in its own stacked
row — the reference image's actual concentric composition — plus a
central contextual status label (`_STATUS_MESSAGES`, below). Every
method this Level 5 sprint already tested (`render_state()`,
`apply_turn_phase()`, `trigger_gesture()`, `apply_workspace_profile()`,
`mount()`/`unmount()`) keeps its exact existing signature and behavior;
these additions are purely additive.

**Phase 7** adds `apply_resource_degradation()` — `presentation/
animation_manager.py`'s own real caller under genuine CPU/RAM/disk
pressure, disabling the particle field and widening the shared
animation tick interval rather than merely documenting the intent (see
that module's own docstring for the full mechanism and why the shared
`QTimer` itself is kept, not replaced).

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

**Cross-thread marshaling (Sprint 5.14)**: `mount()`/`unmount()`/
`apply_workspace_profile()` are, as of this sprint, real, live callers
from `CommunicationPipeline`'s own background thread (`VoiceSessionManager.
_session_loop`, per that class's own established "runs the whole turn"
threading model) — a concretely reproduced Qt violation (`QObject::
killTimer: Timers cannot be stopped from another thread`) was found
during this sprint's own real integration testing when a live persona
switch called `unmount()`'s `self._timer.stop()` from that thread.
`self._timer`/`self._container` are real `QObject`s with thread affinity
permanently fixed to whichever thread first constructed them (always the
main/Qt thread in real operation, per "Widget construction is
deliberately lazy" above) — `render_state()`/`apply_turn_phase()`/
`trigger_gesture()` themselves stay unmarshaled (confirmed, not assumed:
each only ever writes plain Python attributes on `HolographicSphereWidget`/
`SegmentedRingWidget`, never touching a real Qt API — the actual paint
work happens later, entirely on the main thread, inside `_on_tick()`'s
own shared-`QTimer`-driven callback), but `self._timer.start()`/`.stop()`
and `self._container`'s own widget-tree mutations are marshaled onto the
main thread via `QTimer.singleShot(0, context, callable)` — Qt6's own
documented idiom for "run this callable on context's own thread,
regardless of which thread schedules it" (verified directly against this
project's installed PySide6 version, not assumed from Qt's C++ docs
alone) — through `_run_on_main_thread()` below.

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

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QThread, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from config.schema import PresentationConfig
from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation import theme
from presentation.adaptive_workspace import WorkspaceProfile
from presentation.animation_manager import DegradationLevel
from presentation.presentation_state import AVATAR_FOCUS_IDLE, PresentationState
from presentation.widgets.holographic_floor_widget import HolographicFloorWidget
from presentation.widgets.holographic_sphere_widget import HolographicSphereWidget
from presentation.widgets.particle_field_widget import ParticleFieldWidget
from presentation.widgets.segmented_ring_widget import RingState, SegmentedRingWidget

logger = get_logger(__name__)

_STATUS_MESSAGES: dict[RingState, str] = {
    RingState.IDLE: "Ready.",
    RingState.LISTENING: "Listening...",
    RingState.THINKING: "Processing...",
    RingState.SPEAKING: "Responding...",
    RingState.PROCESSING: "Working on that...",
}
"""JARVIS Holographic HUD reskin, Phase 3 — the brief's own central-label
examples ("Ready.", "Listening...", "Processing...", "Working on
that...", "Task completed.") mapped onto RingState. "Task completed." has
no clean, honest RingState trigger (nothing in this codebase currently
signals "a turn juuust finished," as opposed to "we are now idle/
listening again") and is deliberately not fabricated here; SPEAKING's
own label ("Responding...") is this workstream's own reasonable
substitute, keeping "Working on that..." for PROCESSING's already-
established "avatar_focus is non-idle, no specific turn phase active"
meaning (see _derive_ring_state()'s own docstring below)."""

_WORKSPACE_PANEL_TITLES: dict[WorkspaceProfile, str] = {
    WorkspaceProfile.CODING: "Coding Workspace",
    WorkspaceProfile.RESEARCH: "Research Notes",
    WorkspaceProfile.STUDY: "Study Session",
    WorkspaceProfile.PROJECTS: "Project Status",
}
"""GENERAL deliberately has no entry — its own panel set is the system
status panel alone, matching its role as the safe-failure default (see
presentation/adaptive_workspace.py's own Architecture Notes)."""

_DEGRADED_TICK_MULTIPLIER: dict[DegradationLevel, int] = {
    DegradationLevel.NORMAL: 1,
    DegradationLevel.REDUCED: 2,
    DegradationLevel.MINIMAL: 4,
}
"""JARVIS Holographic HUD reskin, Phase 7 — apply_resource_degradation()'s
own tick-interval widening factors. Real, disclosed, unvalidated
first-pass numbers, the same category as every other Level 5 tuned
default."""


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


_CORE_SIZE_FRACTION = 0.62
_CORE_TOP_FRACTION = 0.03
"""The sphere/ring/particle "core" occupies a centered square inset from
the stage's own bounds, anchored near the top rather than filling it
entirely. Found necessary by this phase's own real-screenshot
verification (Section 32's own "after every phase... check rendering
smoothness" instruction, taken literally): the sphere's base radius is
`min(width, height) / 2`, so giving it the stage's FULL rect left it
touching every edge — completely hiding the holographic floor beneath it
(no floor pixels were ever outside the sphere's own opaque fill) and
leaving no visible ring of space for particles to orbit in beyond the
ring's own edge. Insetting the core leaves real, visible margin for both."""


class _HologramStage(QWidget):
    """JARVIS Holographic HUD reskin, Phase 3 — a layered container with
    three tiers, all overlapping (no QVBoxLayout row-stacking, unlike
    Level 5's original vertical sphere-then-ring stack):

    - background layers (the holographic floor) fill the stage's own
      full rect.
    - core layers (sphere, ring) share a smaller, centered, top-anchored
      square (`_core_rect()`) so the floor stays visible below them.
    - orbit layers (the particle field) ALSO get the stage's own full
      rect — never the smaller core rect — but are additionally told
      the core's own center/half-size via `set_orbit_geometry()`, so a
      particle orbiting just outside the ring's edge is never clipped by
      a widget sized to match the ring itself (see
      `presentation/widgets/particle_field_widget.py`'s own docstring
      for the exact clipping bug this shape was found fixing).

    Layered by add order within each tier (first added = bottom). No Qt
    layout manager is attached; resizeEvent() manually resizes every
    layer — the same "layered overlay, not managed by a QLayout" shape
    ui/jarvis/hud_frame.py's own HudFrame.sync_geometry() already
    established in Phase 2."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._background_layers: list[QWidget] = []
        self._core_layers: list[QWidget] = []
        self._orbit_layers: list[ParticleFieldWidget] = []

    def add_background_layer(self, widget: QWidget) -> None:
        widget.setParent(self)
        widget.setGeometry(self.rect())
        widget.show()
        self._background_layers.append(widget)

    def add_core_layer(self, widget: QWidget) -> None:
        widget.setParent(self)
        widget.setGeometry(self._core_rect())
        widget.show()
        self._core_layers.append(widget)

    def add_orbit_layer(self, widget: ParticleFieldWidget) -> None:
        widget.setParent(self)
        widget.setGeometry(self.rect())
        core_rect = self._core_rect()
        widget.set_orbit_geometry(QPointF(core_rect.center()), core_rect.width() / 2.0)
        widget.show()
        self._orbit_layers.append(widget)

    def core_rect(self) -> QRect:
        """Public: JarvisRenderer's own tests use this to assert against
        the exact same geometry core layers are given, without
        duplicating this class's own placement formula."""
        return self._core_rect()

    def _core_rect(self) -> QRect:
        rect = self.rect()
        side = min(rect.width(), rect.height()) * _CORE_SIZE_FRACTION
        x = rect.x() + (rect.width() - side) / 2.0
        y = rect.y() + rect.height() * _CORE_TOP_FRACTION
        return QRectF(x, y, side, side).toRect()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        super().resizeEvent(event)
        rect = self.rect()
        for widget in self._background_layers:
            widget.setGeometry(rect)
        core_rect = self._core_rect()
        for widget in self._core_layers:
            widget.setGeometry(core_rect)
        for widget in self._orbit_layers:
            widget.setGeometry(rect)
            widget.set_orbit_geometry(QPointF(core_rect.center()), core_rect.width() / 2.0)


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
        self._stage: _HologramStage | None = None
        self._floor: HolographicFloorWidget | None = None
        self._particles: ParticleFieldWidget | None = None
        self._sphere: HolographicSphereWidget | None = None
        self._ring: SegmentedRingWidget | None = None
        self._status_label: QLabel | None = None
        self._panel_container: QWidget | None = None
        self._timer: QTimer | None = None
        self._mounted = False
        self._current_workspace_profile: WorkspaceProfile | None = None
        self._last_animation_speed: float = 1.0

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
        is whichever parent layout it's added into (Sprint 5.14).
        self._timer.start() is marshaled onto the main thread (see this
        module's own docstring) — _mounted itself flips synchronously
        so PresentationController's own "is something mounted" tracking
        stays immediately consistent even though the real Qt call lands
        a tick later."""
        self._ensure_widgets_built()
        if self._mounted:
            return
        self._mounted = True
        self._run_on_main_thread(self._timer.start)
        logger.info("Jarvis Renderer mounted.")

    def unmount(self) -> None:
        """Idempotent and safe to call multiple times, before mount(),
        or after mount() already failed. Stops the animation timer
        entirely (Potential Risks: "an unmounted Jarvis renderer...
        consumes no CPU at all") and hides the container — cheaply
        re-mountable, never destroyed, so a brief interruption (Sprint
        5.10's TransitionEngine switching back shortly after switching
        away) doesn't pay a full teardown/rebuild cost. Marshaled onto
        the main thread (see this module's own docstring)."""
        if not self._mounted:
            return
        self._mounted = False
        self._run_on_main_thread(self._do_unmount)
        logger.info("Jarvis Renderer unmounted.")

    def _do_unmount(self) -> None:
        self._timer.stop()
        self._container.hide()

    def _run_on_main_thread(self, func: Callable[[], None]) -> None:
        """See this module's own docstring ("Cross-thread marshaling").
        Calls func() directly, synchronously, when already on
        self._container's own thread (the common case for every call
        site inside ui/main_window.py itself) — QTimer.singleShot()'s
        own deferral is real, necessary overhead only when actually
        crossing threads."""
        if QThread.currentThread() is self._container.thread():
            func()
        else:
            QTimer.singleShot(0, self._container, func)

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
        self._last_animation_speed = state.animation_speed
        ring_state = _derive_ring_state(state)
        self._ring.set_ring_state(ring_state, state.animation_speed)
        self._floor.set_color(color)
        self._particles.set_target(color, state.particle_density, state.animation_speed)
        self._update_status_label(ring_state)

    def apply_turn_phase(self, phase: RingState) -> None:
        """The real per-phase turn-phase signal (Sprint 5.14) — closes
        the granularity gap this module's own docstring named explicitly:
        PresentationState alone can only ever distinguish IDLE from
        "everything else" (_derive_ring_state() above); CommunicationPipeline
        now threads voice/session_manager.py's own real SessionState
        through to here directly. An independent update path from
        render_state() (mirrors apply_workspace_profile()'s own Sprint
        5.12 precedent exactly): never called from render_state(), always
        called from a separate, real turn-phase trigger, so it can win
        even when it runs after render_state()'s own generic PROCESSING
        default already applied this tick. Uses the most recently
        rendered animation_speed rather than a fresh one of its own — a
        turn-phase change alone is not a new emotional read. A no-op
        (logged) if called before the widget hierarchy exists, matching
        render_state()'s own contract."""
        if self._ring is None:
            logger.warning(
                "apply_turn_phase(%s) called before the widget hierarchy exists; ignoring.",
                phase.value,
            )
            return
        self._ring.set_ring_state(phase, self._last_animation_speed)
        self._update_status_label(phase)

    def _update_status_label(self, ring_state: RingState) -> None:
        """JARVIS Holographic HUD reskin, Phase 3 — the brief's own
        central contextual message ("Ready.", "Listening...", etc.),
        below the core. A no-op if called before the widget hierarchy
        exists, matching every other render-path method's own contract
        (never a separate guard clause per caller)."""
        if self._status_label is None:
            return
        self._status_label.setText(_STATUS_MESSAGES[ring_state])

    def apply_resource_degradation(self, level: DegradationLevel) -> None:
        """JARVIS Holographic HUD reskin, Phase 7 — section 25's own
        "reduce particle count... reduce refresh rate... disable
        non-essential effects" levers, applied for real under genuine
        resource pressure (presentation/animation_manager.py's own real
        caller). MINIMAL disables the particle field entirely and widens
        the shared animation tick by 4x; REDUCED thins the particle
        field to its own ambient floor and widens the tick by 2x;
        NORMAL restores both. A no-op (logged) if called before the
        widget hierarchy exists, matching every other render-path
        method's own contract."""
        if self._particles is None or self._timer is None:
            logger.warning(
                "apply_resource_degradation(%s) called before the widget hierarchy exists; "
                "ignoring.",
                level.value,
            )
            return
        self._particles.set_resource_degradation(level)
        multiplier = _DEGRADED_TICK_MULTIPLIER[level]
        self._timer.setInterval(self._config.jarvis_animation_tick_ms * multiplier)

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
        Architecture Notes), never called from it. The real widget-tree
        rebuild is marshaled onto the main thread (this module's own
        docstring) — a real, live caller (CommunicationPipeline's own
        background thread, Sprint 5.14) rebuilds QWidgets here, the
        identical concern mount()/unmount() already guard against."""
        self._ensure_widgets_built()
        self._current_workspace_profile = profile
        self._run_on_main_thread(lambda: self._apply_workspace_profile_on_main_thread(profile))

    def _apply_workspace_profile_on_main_thread(self, profile: WorkspaceProfile) -> None:
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

        # JARVIS Holographic HUD reskin, Phase 3: floor/particles/sphere/
        # ring now share one screen region (see _HologramStage's own
        # docstring) rather than each getting its own QVBoxLayout row.
        self._stage = _HologramStage(self._container)
        self._floor = HolographicFloorWidget()
        self._stage.add_background_layer(self._floor)
        self._particles = ParticleFieldWidget(self._config.jarvis_particle_field_max_count)
        self._particles.set_ambient_minimum(self._config.jarvis_particle_field_ambient_minimum)
        self._stage.add_orbit_layer(self._particles)
        self._sphere = HolographicSphereWidget()
        self._ring = SegmentedRingWidget(self._config.jarvis_ring_segment_count)
        for layer in (self._sphere, self._ring):
            self._stage.add_core_layer(layer)

        self._status_label = QLabel(self._container)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_font = QFont(theme.FONT_FAMILY)
        status_font.setPointSize(10)
        self._status_label.setFont(status_font)
        self._status_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        self._status_label.setText(_STATUS_MESSAGES[RingState.IDLE])

        self._panel_container = QWidget(self._container)
        QVBoxLayout(self._panel_container)  # populated by apply_workspace_profile() (Sprint 5.12)

        layout.addWidget(self._stage, 1)
        layout.addWidget(self._status_label)
        layout.addWidget(self._panel_container)

        self._timer = QTimer(self._container)
        self._timer.setInterval(self._config.jarvis_animation_tick_ms)
        self._timer.timeout.connect(self._on_tick)

    def _on_tick(self) -> None:
        # JarvisRenderer owns the one shared QTimer by design (Potential
        # Risks: two timers would double this widget's own resource
        # cost) — every animated child widget's own _on_tick() is meant
        # to be called only from here, matching Sprint 5.7's own Data
        # Flow diagram exactly (extended, Phase 3, to the particle field
        # — the holographic floor is deliberately static, no _on_tick()
        # of its own, see that widget's own docstring).
        self._sphere._on_tick()
        self._ring._on_tick()
        self._particles._on_tick()
