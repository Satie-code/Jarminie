# Sprint 5.7 — Jarvis Renderer

## Sprint ID

5.7

## Sprint Name

Jarvis Renderer

## Purpose

Build the first concrete `Renderer` (Sprint 5.6): Jarvis's holographic core — a central translucent sphere, a segmented ring visualizing Idle/Listening/Thinking/Speaking/Processing, ambient lighting, and a dashboard shell ready for Sprint 5.12's task-adaptive panels — entirely on native PySide6, per the locked rendering decision (`docs/sprint_book/INDEX.md`'s "Level 5 breakdown changes" note): no QML, OpenGL only if a later profiling pass proves it necessary.

## Engineering Rationale

**New sprint.** The rendering-technology decision was made explicitly, via `AskUserQuestion`, before this Sprint Book was written — not chosen here. This sprint's own job is applying it concretely:

1. **`QPainter` over a `QWidget`, driven by a `QTimer`**, the identical animation-refresh pattern `ui/status_panel.py` already established at Sprint 1.7 (a periodic timer calling a redraw), extended from "redraw with fresh data" to "redraw with fresh data AND advance an animation toward a target." The sphere is drawn as a radial-gradient-filled ellipse (`QRadialGradient`); the segmented ring as a set of arcs (`QPainterPath.arcTo`) whose per-segment color/opacity encodes the current `OperatingMode`/animation phase. No `QGraphicsView`/`QGraphicsScene` is needed for a shape this simple — introducing one would be unjustified complexity for two primitives and a handful of panels, matching this project's own "avoid unnecessary abstraction" discipline.
2. **Animation state lives in the renderer, not in `PresentationState`.** `PresentationState.animation_speed` (5.5) is a *multiplier*; the actual current animation phase (e.g. how far through one "breathing" pulse cycle the sphere currently is) is this renderer's own private, continuously-advancing internal state, updated every timer tick regardless of how often `render_state()` itself is called — otherwise the sphere would visibly jump rather than animate between `PresentationController.refresh()` calls (Sprint 5.6), which may be infrequent (once per turn) while a smooth animation needs many frames per second.

## Objectives

- `presentation/jarvis_renderer.py`: `JarvisRenderer` implementing `Renderer` (5.6), internally composed of a `HolographicSphereWidget` and a `SegmentedRingWidget` (both `QWidget` subclasses) plus a simple panel-container widget for the adaptive dashboard shell.
- A real, running `QTimer`-driven animation loop, decoupled from `render_state()`'s own call frequency.
- `JarvisRenderer.widget() -> QWidget` — the accessor `ui/main_window.py` will use at Sprint 5.14 to embed this renderer's visuals into the existing desktop shell.

## Dependencies

5.6 (Presentation Layer Foundation & Renderer Interface), 1.6 (Desktop Shell & Main Window — the `QApplication`/`QMainWindow` this renderer's widgets live inside), 1.7 (Status Panel — the `QTimer`-driven-refresh precedent this sprint follows).

## Files to Create

- `presentation/jarvis_renderer.py`
- `presentation/widgets/holographic_sphere_widget.py`
- `presentation/widgets/segmented_ring_widget.py`
- `presentation/widgets/__init__.py`
- `tests/unit/presentation/test_jarvis_renderer.py`

## Files to Modify

None outside `presentation/`/`tests/` this sprint — embedding into `MainWindow` is Sprint 5.14's job (Integration Considerations).

## Expected Classes

- **`JarvisRenderer`** (implements `Renderer`): constructor DI receives `PresentationConfig` (5.5, for the locked Jarvis color palette and animation-speed range) only — no direct `EmotionalStateManager`/`PresentationController` reference, keeping it a pure consumer of whatever `PresentationState` it's handed via `render_state()`, per Sprint 5.6's own "renderers consume, they do not determine" contract.
- **`HolographicSphereWidget`** (`QWidget`): owns the sphere's own paint logic and its private animation phase (a slow, continuous "breathing" pulse — radius/opacity oscillation — whose *rate* is scaled by `PresentationState.animation_speed`, and whose *base color* is `PresentationState.lighting_color`).
- **`SegmentedRingWidget`** (`QWidget`): owns the ring's own paint logic — a fixed number of arc segments (`PresentationConfig.jarvis_ring_segment_count`, default a real, config-driven value) whose active/lit segment count and rotation speed encode the current animation state (see `RingState` below).

## Expected Interfaces

`JarvisRenderer` implements `Renderer` (`presentation/renderer.py`, Sprint 5.6) — `mount()` constructs the widget hierarchy (lazily, not at `__init__` time — a `QWidget` must not be constructed before a `QApplication` exists, the same ordering constraint `ui/app.py`'s own `run_app()` already respects); `unmount()` hides/detaches the widget hierarchy (does not necessarily destroy it — cheaply re-mountable if Sprint 5.10's `TransitionEngine` switches back to Jarvis shortly after switching away, avoiding a full teardown/rebuild for what may be a brief interruption); `render_state(state: PresentationState) -> None` updates each child widget's own target values (color, animation-speed multiplier, ring "active state") without itself calling `.update()`/`.repaint()` directly on every call — the `QTimer` loop (Objectives) is solely responsible for scheduling actual repaints, keeping `render_state()` itself cheap and non-blocking per Sprint 5.6's own Protocol contract.

## Expected Functions

- **`RingState`** (`Enum`, `presentation/widgets/segmented_ring_widget.py`): `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `PROCESSING` — the exact five states the brief names for the segmented ring. Derived inside `JarvisRenderer.render_state()` from `PresentationState.avatar_focus` combined with the `OperatingMode`/turn-phase information `PresentationState` itself does not carry directly (see Architecture Notes on this gap and its resolution).
- `HolographicSphereWidget.set_target(color: QColor, animation_speed: float) -> None` — sets the next animation target; actual interpolation happens per-tick, not instantly (a jump-cut color/speed change would violate the brief's own "smooth, deliberate, purposeful" mandate).
- `SegmentedRingWidget.set_ring_state(ring_state: RingState, animation_speed: float) -> None`.
- `JarvisRenderer.widget() -> QWidget` — returns the top-level container widget (sphere + ring + dashboard-panel area) for embedding.

## Data Flow

```
PresentationController.refresh()  (5.6)
        |
        v
JarvisRenderer.render_state(state: PresentationState)
        |
        +--> HolographicSphereWidget.set_target(state.lighting_color, state.animation_speed)
        +--> SegmentedRingWidget.set_ring_state(_derive_ring_state(state), state.animation_speed)
        |
        v
   (returns immediately — no repaint yet)

--- independently, on every QTimer tick (this renderer's own internal loop) ---

HolographicSphereWidget._on_tick() -> advance animation phase toward target -> self.update()
SegmentedRingWidget._on_tick()     -> advance rotation/segment-lit phase   -> self.update()
        |
        v
   Qt's own paintEvent() machinery -> QPainter draw calls
```

## Implementation Tasks

1. `presentation/widgets/holographic_sphere_widget.py` — `HolographicSphereWidget`, `QPainter`-based radial-gradient sphere with a breathing-pulse animation.
2. `presentation/widgets/segmented_ring_widget.py` — `SegmentedRingWidget`, `RingState`, arc-based segmented ring.
3. `presentation/jarvis_renderer.py` — `JarvisRenderer`, composing both widgets plus a placeholder dashboard-panel container (Sprint 5.12 populates it; this sprint ships it empty but present, matching `MainWindow`'s own established "central QVBoxLayout container" shape from Sprint 1.6/1.7).
4. `_derive_ring_state(state: PresentationState) -> RingState` (module-private) — this sprint's own honest, narrow mapping from `avatar_focus`/a small additional constructor-supplied hint; see Architecture Notes for the real limitation named here rather than hidden.
5. `tests/unit/presentation/test_jarvis_renderer.py` — using `pytest-qt` (already a project dependency per `ui/` tests' own established precedent — see `tests/unit/ui/`), verify `mount()`/`unmount()`/`render_state()` update internal widget state correctly without requiring actual pixel-level rendering assertions (the same "verify the state that drives rendering, not the rendered pixels themselves" discipline any GUI test suite in this codebase would need — `tests/unit/ui/test_status_panel.py` sets this precedent already).

## Architecture Notes

**A real, honestly-named gap**: `PresentationState` (Sprint 5.5) carries `avatar_focus` (`"user"`/`"task"`/`"idle"`) but nothing that distinguishes *Listening* from *Thinking* from *Speaking* from *Processing* — those four are turn-phase signals belonging to `voice/quiet_mode.py`'s `OperatingMode` and `voice/session_manager.py`'s own session lifecycle, not to the emotional/persona state `PresentationStateComputer` (5.5) was built to compute. This sprint's `_derive_ring_state()` is therefore deliberately narrow this sprint: it maps `avatar_focus == "idle"` to `RingState.IDLE` and everything else to a single generic `RingState.PROCESSING`, with a documented, named limitation that real per-phase ring states (`LISTENING` while capturing audio, `THINKING` while the Decision Engine pipeline runs, `SPEAKING` while TTS plays) need a real turn-phase signal threaded in — **not built here, real work for Sprint 5.14** (Presentation Layer Integration), which is where `CommunicationPipeline`'s own real turn-phase transitions become available to wire through (mirrors this project's own repeated "routing is this sprint's job, real enforcement/detail is a later sprint's" pattern, e.g. `decision/authority.py`'s own device-control/workflow routing split from `CommunicationPipeline`'s real dispatch).

**No QML, confirmed in the actual implementation, not just in prose**: every visual element in this sprint is drawn via `QPainter` primitives (`QRadialGradient`, `QPainterPath`, `drawArc`) inside overridden `paintEvent()` methods — this sprint's own Testing Checklist includes a direct, mechanical check (no `.qml` file, no `QQuickWidget`/`QQuickView` import anywhere under `presentation/`) so this constraint is verified, not merely asserted.

## Integration Considerations

- **Not embedded into `MainWindow` yet** — `JarvisRenderer.widget()` exists and is directly testable via `pytest-qt`, but `ui/main_window.py` is not modified this sprint; Sprint 5.14 is where `MainWindow` gains a real host for it (see that sprint's own design note on where it goes relative to the existing `StatusPanel`).
- **Ring-state granularity gap** (Architecture Notes above) is explicitly deferred to Sprint 5.14, not silently left unaddressed.
- Sprint 5.9 (Gesture Engine) will call into `JarvisRenderer` for Jarvis-specific gesture visuals (e.g. a dashboard-accent pulse) — a small, additive extension point this sprint should leave room for (a `trigger_gesture(gesture_id: str) -> None` method is explicitly NOT built this sprint — Sprint 5.9 adds it once the Gesture Engine's own vocabulary of gesture ids is real, avoiding a speculative, possibly-wrong signature guessed at now).
- Sprint 5.12 (Adaptive Workspace) populates the dashboard-panel container this sprint ships empty.

## Potential Risks

- **`QPainter`-based custom animation is real, nontrivial GUI work with no automated way to verify visual correctness** — mitigated by testing internal state/target values rather than pixels (Implementation Tasks above), with real visual confirmation named explicitly as part of Sprint 5.16's own manual-verification criterion, not claimed provable by any unit test.
- **Timer-driven repainting has a real performance/resource cost** (a continuously-ticking `QTimer` even while JARMINEI is otherwise idle) — mitigated by a config-driven, deliberately modest tick rate (`PresentationConfig.jarvis_animation_tick_ms`, a real, reviewable default, e.g. 33ms/~30fps — smooth enough for a "deliberate, purposeful" animation without chasing a high frame rate this class of visual doesn't need) and by `Renderer.unmount()` stopping the timer entirely rather than merely hiding the widget, so an unmounted Jarvis renderer (while Minie is active) consumes no CPU at all — a genuine resource-protection concern this sprint must not hand-wave, consistent with Part 3's own "continuous resource monitoring... never trade responsiveness for cleverness" engineering practice.

## Acceptance Criteria

- `mount()`/`unmount()` are idempotent and safe to call multiple times or out of order (a defensive property this sprint verifies directly; full Fail-Gracefully hardening is Sprint 5.15's job).
- `render_state()` never directly triggers a synchronous repaint — verified by asserting no `update()`/`repaint()` call happens within `render_state()` itself, only target-value mutation.
- The animation timer is genuinely stopped on `unmount()` — verified by asserting no further ticks occur after unmounting.
- No QML/`QQuick*` import exists anywhere under `presentation/` (mechanical check, Architecture Notes above).
- `ruff check .` clean; full existing suite unaffected.

## Testing Checklist

- [ ] Unit (`pytest-qt`): `mount()`/`unmount()` lifecycle, including double-mount/double-unmount safety.
- [ ] Unit: `render_state()` correctly sets internal targets without triggering an immediate repaint.
- [ ] Unit: animation timer starts on `mount()`, stops on `unmount()` (verified via a controllable/fake timer or a bounded real-timer wait).
- [ ] Unit: `_derive_ring_state()` mapping for both currently-supported cases (`idle`, everything else -> `PROCESSING`), with the granularity gap covered by an explicit `pytest.mark.skip`-free test documenting today's real behavior (not a TODO comment alone).
- [ ] Mechanical: no QML/`QQuickWidget` import anywhere under `presentation/`.
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `presentation/jarvis_renderer.py` module docstring names the ring-state granularity gap explicitly and points at Sprint 5.14 as where it closes.
- [ ] `presentation/widgets/*.py` docstrings explain the target-vs-animated-phase distinction (Architecture Notes above) — the single most likely point of future confusion for anyone extending these widgets.
- [ ] `docs/STATUS.md` — Level 5 Part A row updated.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

High.

## Estimated Development Time

2.5–3 days.

## Risks

See Potential Risks above.

## Next Sprint

5.8 — Minie Renderer & Avatar Renderer Interface.

## Future Considerations

- Real per-phase (`LISTENING`/`THINKING`/`SPEAKING`) ring states — named as Sprint 5.14's job, not built here.
- If profiling at Sprint 5.16 (Integration Testing & Level Freeze) shows `QPainter`-based rendering is genuinely too slow on the real target machine, revisit the OpenGL option the rendering-decision explicitly left open ("OpenGL only where profiling shows it is necessary for performance") — not assumed necessary now.
