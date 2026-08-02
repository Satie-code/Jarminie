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

## Sprint Completion Report (2026-08-02)

Implemented as specified, authorized directly ("continue with sprint 5.7") right after Sprint 5.6 closed in the same session.

### Summary

`presentation/widgets/holographic_sphere_widget.py`'s `HolographicSphereWidget` and `presentation/widgets/segmented_ring_widget.py`'s `SegmentedRingWidget` (plus its own `RingState` enum, the exact five brief-named states) are both real, complete `QPainter`-based widgets — no QML, no `QGraphicsView`/`QGraphicsScene`. Each keeps its own continuously-advancing animation *phase* strictly private, moved only by its own `_on_tick()`; `set_target()`/`set_ring_state()` (called from `render_state()`) set what to animate *toward*, never an instant jump. `presentation/jarvis_renderer.py`'s `JarvisRenderer` composes both plus an empty placeholder dashboard-panel container (Sprint 5.12's future job) behind a single shared `QTimer` (`PresentationConfig.jarvis_animation_tick_ms`) that calls both widgets' `_on_tick()` every interval — one timer, not two, per this sprint's own Potential Risks resource-cost concern. `mount()`/`unmount()`/`widget()` all funnel through one lazy `_ensure_widgets_built()` so the widget hierarchy is constructed exactly once, on whichever of `mount()`/`widget()` is called first — never at `__init__` time, since `JarvisRenderer` is constructed at `main.py`'s composition-root time, before a real `QApplication` exists.

`_derive_ring_state()` is this sprint's own honestly-narrow mapping, exactly as its own Architecture Notes predicted before implementation: `avatar_focus == "idle"` maps to `RingState.IDLE`, everything else collapses to `RingState.PROCESSING` — `PresentationState` alone has no way to distinguish Listening/Thinking/Speaking, and this sprint does not invent a signal to fake it. The widget-level `RingState` handling itself is complete for all five states (verified: `SegmentedRingWidget.set_ring_state()` accepts and correctly drives lit-fraction/rotation-speed for every value), so Sprint 5.14's real turn-phase wiring only ever needs to change `_derive_ring_state()`'s own body, never the widget.

One real implementation-time decision, not spelled out by the spec, was resolved and is worth naming explicitly: **widget construction ordering relative to `mount()` vs. `widget()`.** The spec's Expected Interfaces says `mount()` "constructs the widget hierarchy (lazily, not at `__init__` time)," which read literally would mean `widget()` — the accessor Sprint 5.14's `MainWindow` needs to embed this renderer into a fixed UI slot at startup — might have nothing to return if called before `mount()`. Since a real embedding sequence plausibly calls `widget()` first (build the UI once) and `mount()`/`unmount()` later (toggle whichever persona is active), both methods were routed through the same one-time `_ensure_widgets_built()` lazy-build helper, so neither has to be called first. Verified directly: a dedicated test calls `widget()` before `mount()` and confirms it returns a real, usable container.

### Files Created

- `presentation/jarvis_renderer.py`
- `presentation/widgets/__init__.py`
- `presentation/widgets/holographic_sphere_widget.py`
- `presentation/widgets/segmented_ring_widget.py`
- `tests/unit/presentation/test_jarvis_renderer.py`

**Not created**: `tests/unit/presentation/__init__.py` — see Sprint 5.5/5.6's own identical, documented-convention precedent.

### Files Modified

- `config/schema.py` — `PresentationConfig.jarvis_ring_segment_count`/`jarvis_animation_tick_ms` fields + validation. **Not explicitly named as a file to modify beyond the sprint's own Expected Classes text** ("PresentationConfig... jarvis_ring_segment_count, default a real, config-driven value") — a real, necessary addition following directly from that text, same category as Sprint 5.5's own original `PresentationConfig` work.
- `config/defaults.yaml` — matching new field defaults.

### Tests Added

- `tests/unit/presentation/test_jarvis_renderer.py` — 30 tests: `mount()`/`unmount()`/`widget()` lifecycle (idempotency in both directions, out-of-order safety, widget-hierarchy reuse across an unmount/remount cycle); `render_state()` correctly sets both widgets' own targets and — verified directly via a mocked `.update()` — never triggers a synchronous repaint itself; the animation timer genuinely advances both widgets' own phase across a bounded real-timer wait, and genuinely stops advancing after `unmount()`; `_derive_ring_state()`'s both currently-real cases (`idle`, and `user`/`task` both collapsing to `PROCESSING`); a mechanical, file-content-scanning check that no `.qml` file or `QQuick*` import exists anywhere under `presentation/`; direct, isolated widget-level tests (`HolographicSphereWidget`/`SegmentedRingWidget` paint without raising via a real `.grab()` render, phase wrapping stays bounded within `[0, 2*pi)`, `set_ring_state()` sets fields correctly, `PROCESSING` lights strictly more segments than `IDLE`, a degenerate 0×0-sized ring widget's `paintEvent()` doesn't crash).

### Documentation Updated

- `presentation/jarvis_renderer.py`'s module docstring (the ring-state granularity gap named explicitly, pointing at Sprint 5.14; the widget-construction-ordering resolution above).
- `presentation/widgets/holographic_sphere_widget.py`'s/`segmented_ring_widget.py`'s own docstrings (the target-vs-animated-phase distinction, stated explicitly in both).
- `config/schema.py`'s `PresentationConfig` docstring (new fields).
- This Sprint Completion Report.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated (see below).

### Acceptance Criteria Checklist

- ✔ `mount()`/`unmount()` are idempotent and safe to call multiple times or out of order — verified directly (double-mount, double-unmount, unmount-before-mount, remount-after-unmount all covered).
- ✔ `render_state()` never directly triggers a synchronous repaint — verified by mocking `.update()` on both child widgets and asserting zero calls.
- ✔ The animation timer is genuinely stopped on `unmount()` — verified by a bounded real-timer wait (`qtbot.wait()`) confirming the phase does not advance afterward, not merely by checking `.isActive()`.
- ✔ No QML/`QQuick*` import exists anywhere under `presentation/` — verified mechanically (a real filesystem scan + file-content grep), not merely asserted in prose.
- ✔ `ruff check .` clean; full existing suite unaffected.

### Risks

- Same "`QPainter`-based custom animation has no automated way to verify visual correctness" and "timer-driven repainting has a real performance/resource cost" risks named in the spec — the former is explicitly deferred to Sprint 5.16's own manual verification; the latter is mitigated as designed (one shared timer, a config-driven modest tick rate, genuinely stopped on `unmount()` — all three verified directly, not just documented).
- The exact pulse-range/rotation-multiplier/lit-fraction numeric constants (`_MIN_PULSE_SCALE`/`_MAX_PULSE_SCALE`, `_LIT_FRACTION`, `_ROTATION_MULTIPLIER`, `_BASE_PHASE_STEP`, `_BASE_ROTATION_STEP`) are real, disclosed, unvalidated first-pass content choices — same category as every other Level 5 visual/config default so far, correctable without a code change where they live in `PresentationConfig`, or with a small, localized code change for the ones that don't (a real, disclosed scope choice: only segment count/tick rate were made config fields this sprint, not every animation constant — see Recommendations below).
- Not embedded into `MainWindow` yet, and `trigger_gesture()` deliberately does not exist yet — both explicitly named as later sprints' own jobs (5.14, 5.9 respectively), not silently deferred.

### Technical Debt

None introduced. The `PresentationConfig` additions were made within this sprint, not deferred or found later.

### Recommendations

- Whether the remaining animation constants (`_MIN_PULSE_SCALE`/`_MAX_PULSE_SCALE`/`_LIT_FRACTION`/`_ROTATION_MULTIPLIER`/`_BASE_PHASE_STEP`/`_BASE_ROTATION_STEP`) should also move into `PresentationConfig` is a real open question — deferred here since none of them are tunable per-persona or per-deployment in a way this sprint's own two config additions (segment count, tick rate) already are; revisit if Sprint 5.16's manual visual verification finds a specific one needs frequent tuning.
- Once Sprint 5.14 wires a real `CommunicationPipeline` turn-phase signal through, `_derive_ring_state()` is the only function that needs to change — confirmed structurally sound by this sprint's own widget-level `RingState` test coverage already exercising all five states.

### Verification

Full suite: 1378 passing + 1 pre-existing failure (the same already-established real-Ollama-output nondeterminism flake from Sprint 5.2/5.3/5.5/5.6's own verification, in a file this sprint never touches) + 1 skipped + 1 deselected. `ruff check .` clean across the whole repository. A direct, non-mocked smoke script (a real `QApplication`, a real `JarvisRenderer` against a real `PresentationConfig`) confirmed `widget()`/`mount()`/`render_state()`/`_on_tick()`/`unmount()`/remount all behave as designed end-to-end, including the target-vs-phase separation (calling `_on_tick()` twice measurably advances both widgets' own private phase).

**No git commit made** — per this project's own "only commit when explicitly asked" rule, changes left in the working tree; the user has not yet been asked whether to commit.

**Sprint 5.8 (Minie Renderer & Avatar Renderer Interface) is next.**
