# Sprint 5.14 — Presentation Layer Integration

## Sprint ID

5.14

## Sprint Name

Presentation Layer Integration

## Purpose

Wire the entire Level 5 Part A graph built across Sprints 5.1–5.13 into one real, running system — mirroring exactly what Sprint 2.12/3.12/4.11/4.18 each did for their own Levels. Every "no live caller until Sprint 5.14" gap named throughout this Sprint Book closes here, in one sprint, the same "one dedicated integration sprint per Level" discipline this project has applied without exception since Level 2.

## Engineering Rationale

**New sprint**, no new architecture — every class this sprint wires already exists from Sprints 5.1–5.13. The real work is threading a real per-turn `EmotionalState` update, a real `PresentationController.refresh()` trigger, real renderer mounting inside `MainWindow`, and real `TransitionEngine`/`GestureEngine`/`AdaptiveWorkspaceController`/`CompanionExperienceEngine` callers into `voice/pipeline.py`'s `CommunicationPipeline` and `main.py`'s composition root — exactly the same shape of work Sprint 4.11 did for Device Control/Workflow and Sprint 4.18 did for Scheduler/Internet Agent.

**`main.py` gains a fifth construct/register stage**, extending the existing four-level pipeline Sprint 4.11 established (`_construct_level2_modules()` -> `_construct_level4_modules()` -> `_construct_pipeline()`, then `_register_level2/3/4_modules()`): `_construct_level5_modules()` builds `EmotionDetectionEngine`, `EmotionalStateManager`, `EmotionalMemory`, `PresentationController` (with both `PresentationStateComputer`s and both `Renderer`s — `JarvisRenderer`, `MinieRenderer(VTubeStudioAvatarRenderer)` — bound into its two dicts), `GestureEngine`, `TransitionEngine`, `AdaptiveWorkspaceController`, `CompanionExperienceEngine`, `VoicePersonalityModulator`, `LipSyncDriver`; `_register_level5_modules()` registers the `ManagedModule`s among them (`PresentationController`, `EmotionDetectionEngine`, `EmotionalStateManager`) with `CoreManager`, following registration-order discipline (constructed after Level 2's `PersonaManager` exists, since `PresentationController` needs it; before or after Level 3/4 is immaterial since neither depends on Level 5).

**One real design decision, made explicitly by this sprint rather than left implicit**: `MainWindow`'s central layout gains a `QSplitter` with a new top pane — a `PresentationHostWidget` — above the existing `StatusPanel` (unchanged, not removed, not repurposed). `PresentationHostWidget` asks `PresentationController` which renderer is currently mounted and embeds `JarvisRenderer.widget()` directly when it's Jarvis; when it's Minie (whose real avatar renders inside the separately-running VTube Studio window, per Sprint 5.8's own Architecture Notes — JARMINEI never renders Live2D itself), it instead shows a small, honest connection-status widget (`MinieRenderer.status_widget()`, new this sprint — "Connected to VTube Studio" / "VTube Studio not detected," never a fake in-app avatar standing in for the real one). This asymmetry is a direct, disclosed consequence of Sprint 5.8's own architecture, not an oversight.

## Objectives

- `main.py`: `_construct_level5_modules()`, `_register_level5_modules()`.
- `voice/pipeline.py`: `CommunicationPipeline` gains a real per-turn emotion/presentation hook (`_run_presentation_pipeline()`, mirroring `_run_decision_pipeline()`'s own established shape) and real `EMOTION_SUPPORT` dispatch.
- `ui/main_window.py`: `PresentationHostWidget` embedding.
- Every named "Sprint 5.14's job" gap across Sprints 5.1–5.13 closed (enumerated in Implementation Tasks).

## Dependencies

5.1–5.13 (every Part A component sprint), 4.11 (Workflow & Device Control Integration — the four-level `main.py` construct/register pattern this sprint extends), 4.18 (Scheduler & Internet Agent Integration — the most recent precedent for adding a new subsystem's construct/register stage).

## Files to Create

- `presentation/presentation_host_widget.py` (the `PresentationHostWidget`, and the real `TransitionOverlay` implementation named in Sprint 5.10's own Integration Considerations — `presentation/qt_transition_overlay.py`).
- `tests/integration/test_presentation_pipeline_integration.py`.

## Files to Modify

- `main.py` — fifth construct/register stage per Engineering Rationale.
- `voice/pipeline.py` — `_run_presentation_pipeline()`; `_handle_turn_complete()` calls it alongside the existing `_run_decision_pipeline()` call; a new `EMOTION_SUPPORT`-branch dispatch (calls `compose_reply_safely()` with the real `emotional_state`, same as the default `CONVERSATIONAL_RESPONSE` path — see Sprint 5.4's own Engineering Rationale on why `EMOTION_SUPPORT` selects a style, not a subsystem); the reply-to-`speak()` call site gains `VoicePersonalityModulator.shape_pacing()` and, when the mounted renderer is an `AvatarRenderer`, a `LipSyncDriver.drive_from_audio()` call run alongside playback.
- `personas/persona_manager.py`'s real construction site (in `main.py`) — passes `TransitionEngine.transition` as `on_switch`.
- `ui/main_window.py` — `PresentationHostWidget` embedded via `QSplitter`, `StatusPanel` unchanged.
- `presentation/minie_renderer.py` — `status_widget()` new method (Engineering Rationale).
- `requirements.txt` — the WebSocket client dependency Sprint 5.8's own stop-and-ask gate resolved (added here if not already added at that sprint's own implementation time).

## Expected Classes

- **`PresentationHostWidget`** (`QWidget`) — per Engineering Rationale.
- **`QtTransitionOverlay`** (implements `TransitionOverlay`, Sprint 5.10) — a real, minimal Qt widget (a semi-transparent overlay drawing a neutral pulse during `SHOWING_CORE`/`PARTICLE_TRANSITION`) shown atop `PresentationHostWidget` during a transition.

## Expected Interfaces

None new — this sprint implements existing Protocols (`TransitionOverlay`) and wires existing classes; no new abstraction is introduced.

## Expected Functions

- `CommunicationPipeline._run_presentation_pipeline(context: ConversationContext, context_analysis: ContextAnalysis | None) -> None` — per real turn: `EmotionDetectionEngine.collect_signals()` + `.estimate()` -> `EmotionalStateManager.decay_toward_baseline(elapsed)` then `.apply_estimate(estimate)` -> (conditionally, per Sprint 5.3's own significance threshold) `EmotionalMemory.record_significant_moment()` -> `PresentationController.refresh()` -> `AdaptiveWorkspaceController.select_profile()`/`.should_switch()` (Jarvis-only path) -> `GestureEngine.trigger_event(TURN_END, ...)`. Wrapped in its own narrow exception boundary, mirroring `_run_decision_pipeline()`'s own Sprint 3.13 hardening precedent exactly — a failure here must degrade to "presentation simply doesn't update this turn," never abort the turn's own spoken reply.
- `main.py`'s `_construct_level5_modules()` / `_register_level5_modules()` — per Engineering Rationale.

## Data Flow

```
CommunicationPipeline._handle_turn_complete()  (existing)
        |
        +--> _run_decision_pipeline()  (existing, Sprint 3.12, unchanged)
        |         -> DecisionTrace
        |
        +--> _run_presentation_pipeline(context, context_analysis)   <-- NEW this sprint
        |         |
        |         +--> EmotionDetectionEngine.collect_signals()/.estimate()   (5.1)
        |         +--> EmotionalStateManager.decay_toward_baseline()/.apply_estimate()  (5.2)
        |         +--> EmotionalMemory.record_significant_moment()  (5.3, conditional)
        |         +--> PresentationController.refresh()  (5.6) -> mounted Renderer.render_state()
        |         +--> AdaptiveWorkspaceController.select_profile()/.should_switch()  (5.12)
        |         +--> GestureEngine.trigger_event(TURN_END, ...)  (5.9)
        |
        +--> PersonaManager.compose_reply_safely(..., emotional_state)   (5.4, now real)
        |         -> reply: str
        |
        +--> VoicePersonalityModulator.shape_pacing(reply, voice_warmth)   (5.11)
        |         -> paced_reply: str
        |
        +--> TextToSpeech.speak(paced_reply, voice_id)   (existing, unmodified)
        |         (in parallel, if mounted renderer is an AvatarRenderer:)
        +--> LipSyncDriver.drive_from_audio(...)   (5.11)


PersonaManager.select() / .resume_previous()  (existing, Sprint 2.11)
        |
        v (on_switch, now real)
TransitionEngine.transition(old, new)   (5.10)  -> PresentationController.mount_renderer()


CompanionExperienceEngine.check_for_greeting()/.check_for_celebration()   (5.13)
        |
        v (at session start / idle-to-active transition, this sprint's own new trigger)
   folded into the next reply's own content input
```

## Implementation Tasks

1. `main.py` — `_construct_level5_modules()`/`_register_level5_modules()`, wiring every Part A class's real constructor dependencies (all already-established DI signatures from Sprints 5.1–5.13, no new ones invented here).
2. `voice/pipeline.py` — `_run_presentation_pipeline()`; `EMOTION_SUPPORT` dispatch branch; `shape_pacing()`/`LipSyncDriver` wiring at the reply-to-speech call site.
3. `presentation/minie_renderer.py` — `status_widget()`.
4. `presentation/presentation_host_widget.py`, `presentation/qt_transition_overlay.py`.
5. `ui/main_window.py` — `QSplitter`, `PresentationHostWidget` embedding, `StatusPanel` unchanged below it.
6. `CompanionExperienceEngine`'s session-start/idle-to-active trigger wired into `CommunicationPipeline`/`voice/quiet_mode.py`'s existing transition points.
7. `AdaptiveWorkspaceController`'s running debounce counter (a small piece of new, genuinely-this-sprint's-own state, since Sprint 5.12 deliberately left ownership of it to the integration sprint).
8. Jarvis's real per-phase `RingState` (`LISTENING`/`THINKING`/`SPEAKING`/`PROCESSING`) — the granularity gap Sprint 5.7 named explicitly — closed here by threading `OperatingMode`/turn-phase signals from `voice/quiet_mode.py`/`voice/session_manager.py` through to `JarvisRenderer`.
9. `tests/integration/test_presentation_pipeline_integration.py` — a real conversation turn through the full graph (fakes for TTS/STT/Ollama/VTube-Studio, matching this project's own established integration-test precedent), asserting: `EmotionalState` measurably updates after an emotionally-loaded scripted turn; the mounted renderer receives a `render_state()` call; a persona switch triggers `TransitionEngine`'s full phase sequence and a real `mount_renderer()` call; `EMOTION_SUPPORT` routing reaches `compose_reply_safely()` with a real `emotional_state`.
10. Full regression run across the entire Level 1–5 Part A suite.

## Architecture Notes

No new architecture — every class wired here already exists. The one real judgment call (`PresentationHostWidget`'s Jarvis-widget-vs-Minie-status-widget asymmetry) is disclosed explicitly in Engineering Rationale rather than silently implemented, the same "log a real structural decision, don't let it pass unremarked" discipline this Sprint Book has applied throughout (`docs/sprint_book/INDEX.md`'s own breakdown note is the canonical example).

## Integration Considerations

- **This sprint is the last one before Part A's own hardening/freeze pair** — Sprint 5.15 (Error Handling & Recovery Hardening) and Sprint 5.16 (Integration Testing & Level Freeze, Part A) remain, mirroring every prior Level's own three-sprint integration/reliability/level-gate closing sequence.
- **Real VTube Studio connectivity is still not required for this sprint's own fast test suite** — `test_presentation_pipeline_integration.py` uses a fake `AvatarRenderer`, the same "real external dependency stays opt-in, verified for real only at the Level-freeze sprint" precedent `test_level3_real_model_verification.py`/`test_level4_part_b_real_verification.py` already established; Sprint 5.16 is where real VTube Studio verification (opt-in) happens.

## Potential Risks

- **This is the largest single wiring sprint in Level 5 Part A**, touching `main.py`, `voice/pipeline.py`, and `ui/main_window.py` at once — the same real complexity Sprint 4.11/4.18 each carried for their own Levels; mitigated by every individual piece already being independently unit-tested from its own component sprint, so this sprint's own job is narrowly "wire correctly," not "get any individual piece right for the first time."
- **`_run_presentation_pipeline()` adds real per-turn latency** (an emotion estimate, a state update, a presentation refresh, on every turn) — flagged explicitly given this project's own documented history with turn-latency issues (`docs/changelog/0.4.3-decision-engine-latency-fix.md`'s own "~45% per-turn LLM latency waste" finding); this sprint's own Acceptance Criteria requires a real, measured latency check, not an assumption that "it's probably fine."
- **The Jarvis ring-state-granularity closure (Implementation Task 8) touches `voice/quiet_mode.py`/`voice/session_manager.py`-adjacent signals** — a real, if narrow, cross-Level touch point; kept as narrow as possible (reading existing signals, not adding new state to either file) per this project's own "don't expand a sprint's own Files to Modify beyond what's genuinely needed" discipline.

## Acceptance Criteria

- A full scripted conversation turn through the real (fakes-at-the-boundary) graph produces a measurable `EmotionalState` change, a real `render_state()` call on the mounted renderer, and a correctly-paced spoken reply.
- A real persona switch triggers `TransitionEngine`'s complete phase sequence and a real renderer swap.
- `EMOTION_SUPPORT`-routed turns reach `compose_reply_safely()` with a real, non-`None` `emotional_state`.
- Per-turn latency added by `_run_presentation_pipeline()` is measured directly (not assumed) and reported in this sprint's own completion report, with a documented follow-up if it proves significant (mirroring `0.4.3`'s own precedent of treating latency as a first-class, measured concern).
- Full Level 1–5 Part A regression suite passes; `ruff check .` clean.

## Testing Checklist

- [ ] Integration: full scripted turn through the real graph (Implementation Task 9's four assertions).
- [ ] Integration: persona-switch-triggers-transition, end to end.
- [ ] Integration: `EMOTION_SUPPORT` routing reaches the real, adapted `compose_reply_safely()` path.
- [ ] Measured: per-turn latency added by `_run_presentation_pipeline()`.
- [ ] Full regression: entire Level 1–5 Part A suite passes.

## Documentation Checklist

- [ ] `main.py`'s own module-level composition-root documentation updated to describe the fifth construct/register stage.
- [ ] `voice/pipeline.py`'s docstring updated with `_run_presentation_pipeline()`'s own role, mirroring `_run_decision_pipeline()`'s existing documentation depth.
- [ ] `docs/STATUS.md` — Level 5 Part A's own integration milestone noted.
- [ ] Measured latency finding documented plainly, whatever it turns out to be (Potential Risks above).

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

High.

## Estimated Development Time

3–3.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.15 — Error Handling & Recovery Hardening.

## Future Considerations

- If the measured latency finding is significant, a dedicated future hardening pass (mirroring `0.4.3`'s own dedicated fix) may be warranted — not pre-built here, named as a real possible follow-up.

---

## Sprint Completion Report (2026-08-03)

**Wired the entire Level 5 Part A graph into one real, running system, exactly as this sprint's own Purpose promised.** `main.py` gained `_construct_level5_modules()`/`_register_level5_modules()` (a new `_Level5Modules` bundle, constructed after Level 2 for `PresentationController`'s own `persona_manager`/`quiet_mode_controller` dependency, registering the three real `ManagedModule`s — `EmotionDetectionEngine`, `EmotionalStateManager`, `PresentationController` — last, mirroring every prior level's own "register after `communication_pipeline`" ordering discipline). `voice/pipeline.py`'s `CommunicationPipeline` gained twelve new constructor dependencies and `_run_presentation_pipeline(context, context_analysis)`, implemented to the exact bullet list this sprint's own Expected Functions named: `EmotionDetectionEngine.collect_signals()`/`.estimate()` → `EmotionalStateManager.decay_toward_baseline()`/`.apply_estimate()` → (conditionally, gated on `_score_significance(state) >= MemoryConfig.emotional_moment_recall_threshold`) `EmotionalMemory.record_significant_moment()` → `PresentationController.refresh()` → (Jarvis-only) `AdaptiveWorkspaceController.select_profile()`/`.should_switch()` → `GestureEngine.trigger_event(TURN_END, ...)`. A real `EMOTION_SUPPORT` branch now calls `PersonaManager.compose_reply_safely()` with the real, live `EmotionalState` directly, matching decision/authority.py's own "selects a style, not a subsystem" contract. `VoicePersonalityModulator.shape_pacing()` and, when Minie's `AvatarRenderer` is the mounted renderer, `LipSyncDriver.drive_from_audio()` (run via a new `on_audio_ready` hook threaded through `TextToSpeech.speak()`/`VoiceSessionManager.speak_reply()`) are both real at the single reply-to-`speak()` call site. `JarvisRenderer.apply_turn_phase()` (new) closes Sprint 5.7's own named ring-state-granularity gap: real `THINKING`/`SPEAKING`/`LISTENING` phases now thread through from three real points in `_handle_turn_complete()`, reading `voice/session_manager.py`'s own real `SessionState`/`TranscriptionResult` via two new narrow accessors (`current_session_state()`, `last_transcription_result()`) rather than adding new state to that file. `PersonaManager.select()`'s `on_switch` now really fires `TransitionEngine.transition()`, resolved via a `CallbackRelay` (`persona_switch_relay`) identical in shape to `turn_complete_relay`/`session_ended_relay` — the same circular-construction problem those two already solved, since `TransitionEngine` needs a `PresentationController` that needs the same `PersonaManager` already built. `ui/main_window.py` gained a `QSplitter` embedding the new `PresentationHostWidget` (`presentation/presentation_host_widget.py`) above the unchanged `StatusPanel`; `PresentationHostWidget` polls `PresentationController.mounted_persona_name` and swaps between `JarvisRenderer.widget()` and the new `MinieRenderer.status_widget()` — a small, honest "Connected to VTube Studio" / "VTube Studio not detected" readout, never a fake in-app avatar, disclosed explicitly in this sprint's own Engineering Rationale. `presentation/qt_transition_overlay.py`'s `QtTransitionOverlay` is a real, minimal semi-transparent pulse-and-label overlay, wired into the already-constructed `TransitionEngine` via a new `set_overlay()` setter (a real QWidget cannot exist at `main.py`'s composition-root time, before `QApplication` does — the identical ordering constraint `_prewarm_tts_before_pyside6()` already exists to manage).

**Five real gaps found during this sprint's own integration testing, each resolved directly and disclosed here — none silently absorbed into "someone else's job":**

1. **A genuine Qt cross-thread violation** (`QObject::killTimer: Timers cannot be stopped from another thread`), concretely reproduced the first time a live persona switch ran through the real graph: `JarvisRenderer.mount()`/`.unmount()`/`.apply_workspace_profile()` are, as of this sprint, real callers from `CommunicationPipeline`'s own background thread (`VoiceSessionManager._session_loop`), but `self._timer`/`self._container` are real `QObject`s permanently bound to the main/Qt thread. Fixed via `JarvisRenderer._run_on_main_thread()`, using `QTimer.singleShot(0, context, callable)` — Qt6's own documented idiom for this, verified directly against this project's installed PySide6 version with a standalone cross-thread probe before trusting it, not assumed from the C++ docs alone. `render_state()`/`apply_turn_phase()`/`trigger_gesture()` were confirmed (not assumed) to need no such marshaling — each only ever writes plain Python attributes, never a real Qt API call.
2. **A real, measured latency problem**: `VTubeStudioAvatarRenderer.mount()`'s own connection attempt against a non-running VTube Studio instance — the common, undriven case this project's own test suite runs under by default — was measured directly at **~4.1 seconds** (not assumed), which would have stalled an entire spoken reply by that amount on every persona switch to Minie. Fixed at `MinieRenderer.mount()` (this sprint's own file), which now spawns a background daemon thread rather than calling `AvatarRenderer.mount()` synchronously — the identical "spawn and return immediately" precedent `LipSyncDriver.drive_from_audio()` already established (Sprint 5.11) — leaving `VTubeStudioAvatarRenderer` itself, and its own Sprint 5.8 tests, untouched.
3. **`voice/text_to_speech.py`'s `TextToSpeech.speak()`/`CoquiTextToSpeech.speak()`** gained an optional `on_audio_ready: Callable[[bytes, int], None] | None = None` parameter (default `None`, every existing caller's behavior unchanged) — the only way to give `LipSyncDriver` the real synthesized audio buffer without restructuring `speak()`'s own deliberately-bundled synthesis-and-playback contract (that module's own Sprint 2.4 docstring). `VoiceSessionManager.speak_reply()` forwards it straight through.
4. **`memory/emotional_memory.py`'s private `_score_significance()`** is imported directly into `voice/pipeline.py` (not duplicated) to gate `record_significant_moment()` — the identical cross-module reuse `tests/unit/memory/test_emotional_memory.py` already established for this exact function, so the "record only when genuinely significant" gate cannot drift from `EmotionalMemory`'s own definition of significant.
5. **A genuine Qt native crash** (`Windows fatal exception: access violation`, a hard process segfault, not a normal assertion failure), found and root-caused only by running the real, full combined suite — `PresentationController.start()` now really builds a `JarvisRenderer` (a real, unparented top-level `QWidget` + `QTimer`) in every test using `tests/integration/conftest.py`'s `pipeline_harness`/`tests/system/conftest.py`'s `app_harness` (previously a purely non-Qt test tier). Neither harness's own teardown ever processed Qt's event loop, so ~140 such widgets accumulated across a full run with nothing ever draining the backlog, until some later, entirely unrelated test's own first real `qtbot.wait()` call (`tests/unit/presentation/test_jarvis_renderer.py`) forced Qt to process it all at once — reliably reproduced (confirmed deterministic across three separate runs, always the identical crash site) before the fix, confirmed gone after it. Fixed by having both harnesses explicitly `deleteLater()` the constructed `JarvisRenderer`'s own widget and pump `QApplication.processEvents()` in their own `finally` block, keeping Qt's internal bookkeeping consistent incrementally, per test, rather than letting it batch up. A test-suite-scale artifact, not a production one — `main.py` constructs exactly one `JarvisRenderer` for the whole app's own lifetime, never hundreds in quick succession — but a real, serious finding regardless, since a hard crash mid-suite is unacceptable in any tier.

**Companion-experience session-start wiring is a disclosed, narrower implementation than the Sprint Book's own Data Flow diagram literally shows**: `CommunicationPipeline._maybe_prepare_companion_moment()` tracks first-turn-per-`session_id` itself (new, genuinely this sprint's own state — no changes to `voice/quiet_mode.py` were needed or made), reusing `ConversationContext.last_activity_at` (already flowing through this pipeline via `EmotionDetectionEngine`'s own pause signal) as the idle-duration measurement. A `CompanionMoment`'s content is folded into the reply as a plain-text prefix composed directly in `voice/pipeline.py` (`_prefix_companion_moment()`), not through `Persona.compose_reply()` — extending that method's own signature would touch `personas/base.py`/`personas/jarvis.py`/`personas/minie.py`, none of which are this sprint's own Files to Modify. The real behavior (a companion moment's content really does reach the spoken reply) is preserved; only the phrasing mechanism is narrower than the diagram's literal wording, the same "disclosed narrower implementation, real behavior preserved" precedent this Sprint Book has applied before (Sprint 5.13's own `WELLNESS` omission, Sprint 5.7's own gesture-interpretation narrowing).

**Measured, not assumed, per this sprint's own Acceptance Criteria**: `_run_presentation_pipeline()`'s own added per-turn latency, sampled ten times against the real `pipeline_harness` object graph (real `EmotionDetectionEngine`/`EmotionalStateManager`/`PresentationController`/`JarvisRenderer`, no network/Ollama calls anywhere in this method's own path) — **mean ~1.6ms, max ~16ms** (a one-time first-call cost). Negligible next to a real turn's own Decision Engine LLM call, which dominates total per-turn latency by two to three orders of magnitude; no dedicated follow-up hardening pass is warranted (contrast `0.4.3`'s own genuine ~45%-latency-waste finding, which did require one). `tests/integration/test_presentation_pipeline_integration.py::test_measured_presentation_pipeline_latency_is_reported` keeps this a real, re-checked regression guard, not a one-time claim.

**Every constructor-signature change this sprint made — `CommunicationPipeline`, `PersonaManager.__init__`'s already-existing `on_switch` (now really wired), `MainWindow.__init__`, `MinieRenderer.__init__` — rippled into every shared test harness that constructs these classes**: `tests/integration/conftest.py`'s `pipeline_harness`/`fast_scheduler_harness` and `tests/system/conftest.py`'s `app_harness`/`fast_scheduler_app_harness` both now build the real Level 5 Part A graph too (the one real external boundary, VTube Studio, is deliberately left unfaked — its own `mount()` now degrades fast and asynchronously, so a real, self-degrading `create_avatar_renderer()` costs this suite nothing), gaining a `qapp` (pytest-qt) fixture dependency since `PresentationController.start()` now really constructs `QWidget`s via `JarvisRenderer`. `tests/unit/voice/test_pipeline.py`'s `collaborators()` fixture gained the twelve new mocked dependencies, each configured to a real no-op default (`companion_experience_engine.check_for_greeting()`/`.check_for_celebration()` → `None`, `voice_personality_modulator.shape_pacing()` → identity passthrough) specifically so none of the ~40 pre-existing reply-text assertions in that file needed to change — only `speak_reply()`'s own call-site assertions gained the new `on_audio_ready=...` kwarg (16 sites, transformed mechanically, verified against the real method). `tests/unit/ui/test_main_window.py` gained a shared `mock_presentation_handles` fixture. `tests/unit/presentation/test_minie_renderer.py` gained a `core_manager` fixture argument and an `avatar.mount_called` `threading.Event` wait, replacing a same-thread assumption `mount()`'s own new asynchrony broke.

**A second, real, cross-cutting regression found via the full suite (not assumed absent): `VoicePersonalityModulator.shape_pacing()` running for real, for the first time, on every spoken reply legitimately changes reply text wherever an existing sentence/clause boundary exists** — eleven pre-existing exact-string reply assertions across `tests/system/`/`tests/integration/` (comparing against `FakeLanguageModelClient.conversational_response`, a templated fallback reply, a scheduler-failure message, and two composed internet-agent summaries) needed `.replace("... ", "")` before comparison, per `VoicePersonalityModulator`'s own structural "de-marking reconstructs the original exactly" guarantee — a real, intended behavior change from this sprint's own wiring, not a bug, fixed at the test layer rather than papered over.

**`main.py`'s own `_prewarm_tts_before_pyside6()` call moved to the true first line of `main()`'s body** (previously immediately before `ui.app`'s own local import): `presentation/jarvis_renderer.py`/`presentation/minie_renderer.py` (both real Level 5 constructions this sprint's own `_construct_level5_modules()` now performs, well before `ui.app` is ever imported) import `PySide6` at their own module level — the prior call site was already too late to guarantee the documented root-cause fix (Coqui `TTS`/`six.moves` cached in `sys.modules` before PySide6's own import hook installs) once Level 5 construction, not just `ui.app`, became a real path that imports PySide6 first.

**Full regression suite**: 1589 total tests (1586 passing + 1 pre-existing failure, the same already-documented real-Ollama-output nondeterminism flake since Sprint 5.2, in a file this sprint never touches + 2 skipped), run as one real, combined `pytest` invocation across the entire repository (unit + integration + system in a single process — the same real-world shape a CI run would take, not run tier-by-tier), `ruff check .` clean.

**This closes Level 5 Part A's own component-and-integration work through Sprint 5.14 — Sprint 5.15 (Error Handling & Recovery Hardening) and Sprint 5.16 (Integration Testing & Level Freeze, Part A) remain, the same integration/hardening/freeze trio every prior Level has closed with.**

## Post-Sprint Fix (2026-08-04, found during Sprint 5.16's adversarial re-read)

Two real, previously-latent gaps in this sprint's own two `QTimer`-driven, un-tested-until-now files (`presentation/qt_transition_overlay.py`, `presentation/presentation_host_widget.py`) — both missed by Sprint 5.15's own scenario (c) hardening pass, which only named `HolographicSphereWidget`/`SegmentedRingWidget` in its own Files to Modify.

1. **`QtTransitionOverlay._on_tick()` had no exception guard** — the identical "a `QTimer` slot has nothing upstream to catch it" risk Sprint 5.15 scenario (c) fixed for the other two animation widgets, just missed for this one since it wasn't in that sprint's own file list. Fixed with the identical pattern (a `_tick_failure_logged` flag, logged once per failure streak, reset on recovery).
2. **`PresentationHostWidget.refresh()`'s own try/except only wrapped the `mounted_persona_name` read, not `_swap_displayed_widget()`** (real `QWidget`/`QLayout` construction and mutation) — widened to cover the whole method body. A second, deeper gap surfaced while fixing the first: `_swap_displayed_widget()` used to set `self._displayed_persona_name = mounted_name` *before* actually building the new widget, so a genuine `widget()`/`status_widget()` failure would leave that bookkeeping permanently pointing at the new name even though nothing was ever displayed — `refresh()`'s own "no change, skip" check (`mounted_name == self._displayed_persona_name`) would then silently short-circuit every future retry forever, not just for that one failed tick. Restructured so the bookkeeping update happens only after the new widget is actually built and added; a failure now leaves the two genuinely out of sync, so the very next `refresh()` tick retries for real.

Neither file had a dedicated unit test file before this fix — both now do (`tests/unit/presentation/test_qt_transition_overlay.py`, `tests/unit/presentation/test_presentation_host_widget.py`), 13 tests total, covering the fixes directly (including the deferred-bookkeeping regression specifically) plus basic construction/mount/swap sanity coverage neither class had at all previously.
