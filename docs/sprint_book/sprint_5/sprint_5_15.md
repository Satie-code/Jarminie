# Sprint 5.15 — Error Handling & Recovery Hardening

## Sprint ID

5.15

## Sprint Name

Error Handling & Recovery Hardening

## Purpose

Apply the Fail Gracefully Rule across Level 5 Part A's own six named failure scenarios, mirroring Sprint 2.13/3.13/4.12/4.19's identical role for their own Levels — the fully-wired real graph Sprint 5.14 just built is exactly where latent gaps become real, reachable failures for the first time.

## Engineering Rationale

**New sprint.** Following this project's own established precedent exactly: some scenarios need real production code changes, others confirm already-correct behavior with a new regression test proving it — an honest split, reasoned explicitly rather than assumed, the same discipline Sprint 4.19's own completion report modeled ("An honest split: three needed real production changes, three needed only regression tests").

Six scenarios, chosen because each was explicitly named as deferred-to-this-sprint somewhere in Sprints 5.1–5.14's own text, not invented fresh here:

**(a) VTube Studio disconnects mid-session** (named in Sprint 5.8's own Potential Risks: "A real reconnection attempt is explicitly Sprint 5.15's hardening job, not this sprint's"). **Real code change**: `VTubeStudioAvatarRenderer` gains a bounded reconnect attempt (`PresentationConfig.vtube_studio_reconnect_max_attempts`, a small default) triggered the next time any method is called while `_connected=False`, rather than requiring a full `unmount()`/`mount()` cycle — a session-long disconnect (VTube Studio crashes, or was never running) still degrades to the existing silent no-op after attempts are exhausted, never a crash, never a retry storm.

**(b) `EmotionDetectionEngine`/`EmotionalStateManager` failure mid-turn** (their own Sprint 5.1/5.2 contracts already promise "never raises"). **Confirmed already correct, regression test only**: a real induced failure (a malformed `TranscriptionResult`, a `NaN`-producing edge case in the EMA math) is driven through the real, fully-wired Sprint 5.14 graph, confirming `EmotionalState` simply doesn't update that turn and the turn's own spoken reply still completes normally.

**(c) A renderer's own per-frame paint/animation logic raises** (named implicitly by Sprint 5.7's own "must be cheap/non-blocking" `render_state()` contract, but the *animation timer's own tick handler* — a separate code path from `render_state()` — was never given the same guarantee). **Real code change**: `HolographicSphereWidget`/`SegmentedRingWidget`'s own `_on_tick()` methods (Sprint 5.7) and `PresentationController.refresh()`'s already-existing guard (Sprint 5.6) both get one more narrow try/except each — a single bad frame is caught, logged once (rate-limited to avoid log flooding from a persistently-broken paint path), and the previous frame's own last-good visual state is retained rather than a blank/half-drawn widget or a crashed timer thread.

**(d) A second persona switch arrives while `TransitionEngine.transition()` is still mid-sequence** (named explicitly in Sprint 5.10's own Potential Risks as "explicitly deferred to Sprint 5.15's own hardening scenario list"). **Real code change**: `TransitionEngine` tracks whether a transition is currently in progress; a new `transition()` call arriving mid-sequence cancels the in-flight one at its next phase boundary (never mid-phase) and immediately starts the new one from `LOADING_TARGET` (skipping the now-stale `SAVING_STATE`/`SYNCING_MEMORY`/`SHOWING_CORE`/`PARTICLE_TRANSITION` phases of the superseded transition) — the end state is always "the renderer matching whichever persona is now actually active is mounted," even under rapid double-switching, never a stuck overlay or two renderers both partially mounted.

**(e) Level 5 Part A's own construction fails at startup** (implicit in every prior sprint's "no live caller until Sprint 5.14" framing — this is the first sprint where a real construction failure could plausibly take down the whole app). **Real code change**: `main.py`'s `_construct_level5_modules()` call is wrapped in its own narrow try/except at the call site (not inside the function itself, keeping the function's own contract clean) — a genuine failure (e.g. an invalid `PresentationConfig`, though `AppConfig.validate()` should already catch most such cases before construction is ever attempted) logs a clear error and JARMINEI continues starting up with Level 1–4 fully intact and Level 5 Part A simply absent (no `PresentationController` registered, `MainWindow`'s `PresentationHostWidget` shows a plain "Presentation Layer unavailable" placeholder rather than failing to construct) — directly enacting the brief's own "Presentation never changes intelligence" principle at the availability level, not just the content level: a broken Presentation Layer must never take JARMINEI's actual intelligence down with it.

**(f) A bug elsewhere fires `GestureEngine.trigger_event()` far more often than intended** (a plausible, if unlikely, consequence of Sprint 5.14's new turn-lifecycle wiring — e.g. a retry loop accidentally calling it every millisecond). **Real code change**: `GestureEngine.trigger_event()` gains the same per-trigger rate-limiting `maybe_roll_ambient_gesture()` (Sprint 5.9) already has for the ambient path — a small, config-driven minimum interval per `GestureTrigger` value, so even a genuinely buggy caller can't flood a renderer with gesture calls.

## Objectives

- Six scenarios above, each either a real, narrow code change or a real, induced-failure regression test proving already-correct behavior.
- An explicit adversarial sweep of `presentation/`/`emotion/`'s own internal call sites (mirroring Sprint 4.12's own Implementation Task 2), confirming every collaborator call inside `PresentationController.refresh()`, `TransitionEngine.transition()`, and `CommunicationPipeline._run_presentation_pipeline()` degrades gracefully.

## Dependencies

5.14 (Presentation Layer Integration).

## Files to Create

- `tests/integration/test_presentation_layer_resilience.py`.

## Files to Modify

- `presentation/vtube_studio_renderer.py` — reconnect-attempt logic (a).
- `presentation/widgets/holographic_sphere_widget.py`, `presentation/widgets/segmented_ring_widget.py` — per-tick exception guarding (c).
- `presentation/transition_engine.py` — in-progress-transition cancellation/supersession (d).
- `main.py` — `_construct_level5_modules()` call-site try/except (e).
- `presentation/gesture_engine.py` — `trigger_event()` rate-limiting (f).
- `config/schema.py` — `PresentationConfig` gains `vtube_studio_reconnect_max_attempts: int = 3`, `gesture_trigger_min_interval_seconds: float = 0.5`.
- `tests/unit/presentation/test_vtube_studio_renderer.py`, `test_jarvis_renderer.py`, `test_transition_engine.py`, `test_gesture_engine.py`, `tests/unit/emotion/test_detection_engine.py`, `test_state_manager.py` — new hardening-scenario coverage.

## Expected Classes

None new.

## Expected Interfaces

None new.

## Expected Functions

New/modified functions per scenario, all listed in Engineering Rationale above — no signature changes to any existing public method beyond internal robustness (every caller's existing usage continues to work unmodified).

## Data Flow

Not applicable in the way earlier sprints used this section — this sprint verifies and hardens existing data flows (Sprint 5.14's own diagram) rather than introducing new ones, the identical framing Sprint 4.20/3.14 used for their own hardening/freeze sprints' Data Flow sections.

## Implementation Tasks

1. Scenario (a): `VTubeStudioAvatarRenderer` reconnect logic + regression test (a fake transport that fails then recovers).
2. Scenario (b): regression test only, against the real Sprint 5.14 graph with an induced malformed-input failure.
3. Scenario (c): per-tick exception guarding in both widgets + regression test (a fake paint path that raises).
4. Scenario (d): `TransitionEngine` supersession logic + regression test (two rapid `transition()` calls, asserting the final mounted renderer is correct and no overlay is left stuck).
5. Scenario (e): `main.py` call-site guarding + regression test (a deliberately-broken Level 5 construction, asserting `CoreManager.startup()` still succeeds for Levels 1–4).
6. Scenario (f): `GestureEngine.trigger_event()` rate-limiting + regression test (rapid repeated calls, asserting the renderer's own `trigger_gesture()` call count is bounded).
7. Adversarial sweep of `presentation/`/`emotion/` internal call sites (Objectives).
8. Full regression run.

## Architecture Notes

No new architecture — every change above is a narrow, targeted fix at the file that owns the gap, never a redesign, the same discipline every prior hardening sprint in this project has followed without exception.

## Integration Considerations

- This sprint's own scenarios are all genuinely composition-dependent (each needs the real Sprint 5.14 graph to manifest) — none are testable meaningfully at the pre-5.14 component level, the same reasoning Sprint 4.19/4.12 both used to justify why hardening comes after integration, not before.
- Sprint 5.16 (Integration Testing & Level Freeze) re-confirms these six scenarios at the full system level, explicitly reasoning about which (if any) don't need a third repetition — matching Sprint 3.14/4.13/4.20's own established judgment-call precedent.

## Potential Risks

- **Scenario (d)'s supersession logic is the most structurally delicate change in this sprint** — a race between "cancel the old transition" and "start the new one" could, if implemented carelessly, leave two overlapping `mount_renderer()` calls in flight; mitigated by the phase-boundary-only cancellation design (Engineering Rationale) and a dedicated, explicit regression test asserting exactly one final `mount_renderer()` call wins.
- **Rate-limiting (scenario f) could mask a real, otherwise-visible bug in a caller** that's genuinely firing gestures too often — an acceptable trade-off (the same one `ActionRegistry.dispatch()`'s own bounded-retry logic already makes elsewhere in this codebase), since silently dropping excess gesture calls is strictly safer than a flooded renderer, and the rate-limit itself is logged when it actually engages, so the underlying bug remains discoverable.

## Acceptance Criteria

- All six scenarios pass their own dedicated regression test against the real, fully-wired Sprint 5.14 graph (or fakes at the true external boundary — VTube Studio, real hardware — matching this project's own established fakes-at-the-boundary testing discipline).
- A deliberately-broken Level 5 Part A construction never prevents Levels 1–4 from starting up successfully.
- Full Level 1–5 Part A regression suite passes; `ruff check .` clean.

## Testing Checklist

- [ ] (a) VTube Studio disconnect-then-reconnect.
- [ ] (b) Emotion pipeline induced-failure regression (confirmed already correct).
- [ ] (c) Renderer per-tick paint exception, previous frame retained.
- [ ] (d) Overlapping transition supersession, exactly one final `mount_renderer()` call.
- [ ] (e) Broken Level 5 construction, Levels 1–4 still start.
- [ ] (f) Gesture trigger flood, bounded call count.
- [ ] Adversarial sweep of `presentation/`/`emotion/` internal call sites.
- [ ] Full regression: entire Level 1–5 Part A suite passes.

## Documentation Checklist

- [ ] Each of the six scenarios documented in its owning file's own docstring (the same "hardening documented at the file it touches" convention every prior hardening sprint used).
- [ ] `docs/STATUS.md` — Level 5 Part A hardening milestone noted.
- [ ] Any new, real findings from the adversarial sweep logged plainly, matching `backlog/technical_debt.md`'s own established format.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.16 — Integration Testing & Level Freeze (Part A).

## Future Considerations

- None beyond what Sprint 5.16 itself will surface — this sprint's own scope is fully bounded by the six named scenarios above.
