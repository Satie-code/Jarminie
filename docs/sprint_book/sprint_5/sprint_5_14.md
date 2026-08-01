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
