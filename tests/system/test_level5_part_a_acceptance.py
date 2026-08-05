"""Level 5 Part A — Emotional Intelligence & Presentation Layer formal
Acceptance Pass (Sprint 5.16), closing Level 5 Part A. Mirrors Sprint
2.14/3.14/4.13/4.20's own identical role for their own Levels/Parts.

**`v0.5` itself remains gated on Part B too** (Companion Intelligence —
Wellness/Analytics/Learning, sprints 5.17-5.23, not yet written) — this
sprint's own "Level 5 Part A complete" marker is explicitly not a
semver tag, the same distinction sprint_4_13.md drew for Level 4 Part A.

One continuous scripted scenario through the real, complete
`CoreManager` graph (`app_harness`, tests/system/conftest.py — the same
harness `test_level4_part_b_acceptance.py` already uses, now also
carrying every Level 5 Part A object). Covers, in order: measurable
`EmotionalState` evolution from a real emotionally-loaded turn; the
brief's own core "one intelligence, different presentation" promise,
checked directly and mechanically (Engineering Rationale); a real
persona transition running `TransitionEngine`'s complete seven-phase
sequence; `AdaptiveWorkspaceController`'s real profile switch from two
consecutive task-shaped turns; and `CompanionExperienceEngine`'s
greeting on a session's own first turn.

**Sprint 5.15 hardening re-confirmation** (Objective 3), applying the
same judgment Sprint 3.14/4.13/4.20 each already used for their own six
scenarios — none of the six get a dedicated system-level repeat here,
each for its own explicit reason:
- **(a)** VTube Studio reconnect — purely component-level (`Vtube
  StudioAvatarRenderer`'s own connection/thread bookkeeping); nothing
  about `CoreManager`'s own graph changes that behavior. Already
  exhaustively covered at the unit level
  (`tests/unit/presentation/test_vtube_studio_renderer.py`).
- **(b)** Emotion pipeline failure — already re-confirmed through the
  real, fully-wired object graph in Sprint 5.15's own integration tests
  (`tests/integration/test_presentation_layer_resilience.py`, which
  builds the identical real classes `main.py`/`app_harness` do). A
  third repetition through `CoreManager.startup()` specifically would
  exercise the exact same `voice/pipeline.py` try/except with no new
  collaborator in the loop — this scenario's own real prerequisite
  (the emotion pipeline genuinely running through the complete graph)
  is naturally exercised, un-broken, by this file's own Step 1 below.
- **(c)** Widget per-tick exception guarding — pure `QWidget`/`QTimer`
  internals (`HolographicSphereWidget`/`SegmentedRingWidget`), zero
  `CoreManager` dependency of any kind. Already covered at the unit
  level (`tests/unit/presentation/test_jarvis_renderer.py`).
- **(d)** Transition supersession — this codebase's own only real
  caller (`PersonaManager.on_switch`) processes turns sequentially on
  one session-loop thread (voice/session_manager.py's own established
  threading model); a literal concurrent race cannot be reproduced
  through a real scripted conversation any more faithfully than Sprint
  5.15's own deterministic re-entrant-overlay unit tests already do
  (`tests/unit/presentation/test_transition_engine.py`) — forcing an
  artificial repeat here would add ceremony, not confidence. This
  file's own Step 3 below does re-confirm a real, complete, un-superseded
  transition sequence through the full graph.
- **(e)** Broken Level 5 construction — already re-confirmed against a
  real `CoreManager` in Sprint 5.15's own integration tests, using
  `main.py`'s own real `_null_level5_modules()`/`_register_level5_modules()`
  functions directly. A further repetition through `app_harness`'s own
  full graph would need injecting a construction failure into that
  fixture's own hand-assembled object graph — a real conftest.py
  structural change this Level-freeze sprint's own "no new architecture"
  mandate does not warrant for a scenario whose own mechanism (a
  try/except at one call site) has no path-dependence on what else is
  registered.
- **(f)** Gesture rate limiting — pure `GestureEngine`-internal
  bookkeeping (a `dict[GestureTrigger, datetime]`), zero `CoreManager`
  dependency. Already covered at the unit level
  (`tests/unit/presentation/test_gesture_engine.py`).

The one remaining Acceptance Criterion — a supervised, real-machine,
human-observed pass (the sphere/ring genuinely animating; a real VTube
Studio avatar genuinely responding to voice/emotion; a real
persona-switch transition genuinely playing) — is explicitly NOT
performed by this automated suite, matching every prior Level-freeze
sprint's own precedent of naming a manual step rather than silently
assuming it happened; see this sprint's own completion report.
"""

import dataclasses

from emotion.state_manager import EmotionalState
from presentation.adaptive_workspace import WorkspaceProfile
from presentation.transition_engine import TransitionPhase

_TURN_TIMEOUT = 10.0
"""Matches test_level4_part_b_acceptance.py's own more generous timeout
— this file's own scenario is similarly long/composite."""

_DIAGNOSTIC_TERMS = ("diagnos", "disorder", "illness", "clinical", "syndrome", "pathology")
"""Substrings that would indicate a clinical/diagnostic field name, if
one ever crept into EmotionalState — the mechanical half of Part 4's
own "Never performs medical diagnosis" acceptance criterion (the other
half — that JARMINEI's own reply phrasing never claims to diagnose — is
a persona-template/prompt concern outside this dataclass, already
covered by personas/base.py's own template review at Sprint 5.4)."""


def _reset_wake_detection(h) -> None:
    """See test_level3/4_acceptance.py's own identical helper for the
    full rationale (a real, previously-reproduced timing race, Sprint
    3.12)."""
    h.wake_engine.calls = 0


def test_emotional_state_has_no_clinical_or_diagnostic_field():
    """Part 4's own Phase 5.1 acceptance criterion, "Never performs
    medical diagnosis," confirmed structurally: EmotionalState (Sprint
    5.2) and EmotionLabel (Sprint 5.1) were both designed with no
    clinical field at all, per their own docstrings ("never a
    diagnosis... no clinical field exists") — a mechanical check that
    this structural promise still holds, not merely re-asserted."""
    field_names = [f.name for f in dataclasses.fields(EmotionalState)]
    for name in field_names:
        lowered = name.lower()
        assert not any(term in lowered for term in _DIAGNOSTIC_TERMS), (
            f"EmotionalState.{name} looks clinical/diagnostic — violates this "
            "project's own locked 'never a diagnosis' design."
        )


def test_level5_part_a_full_acceptance_scenario(
    app_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    h = app_harness

    # --- Step 1: a real emotionally-loaded turn (Jarvis, the default
    # active persona) measurably moves EmotionalState away from its
    # neutral defaults, and the mounted renderer genuinely receives the
    # updated state — re-derives test_presentation_pipeline_integration.py's
    # own Sprint 5.14 finding through this sprint's own complete Level
    # 1-5 graph, not just Level 1-5's own hand-assembled pipeline_harness. ---
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    baseline_state = h.emotional_state_manager.current_state()
    assert baseline_state.stress == 50.0  # neutral default, confirmed before asserting a real move

    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: feeling overwhelmed\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    jarvis_question = "what's the status of my project"
    h.llm_client.conversational_response = "Here's a real, generated answer to your question."
    h.stt.pending_transcripts.append(
        "I'm so stressed and overwhelmed right now, I can't keep up with anything"
    )
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)

    updated_state = h.emotional_state_manager.current_state()
    assert updated_state.stress != 50.0  # a real, measurable move away from neutral
    assert updated_state.updated_at > baseline_state.updated_at
    assert h.presentation_controller.mounted_persona_name == "jarvis"
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- Step 2: "same intelligence, different presentation," half one —
    # a neutral question, asked of Jarvis, with a fixed canned reply from
    # the fake LLM (Engineering Rationale's own equivalence check). -----
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: general question\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append(jarvis_question)
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    jarvis_reply, jarvis_voice_id = h.tts.speak_calls[-1]
    assert h.persona_manager.active_persona().name == "jarvis"
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- Step 3: two consecutive coding-shaped turns (Jarvis still
    # active) genuinely rearrange the dashboard — AdaptiveWorkspaceController's
    # own debounce (workspace_switch_debounce_turns=2 by default) met
    # for real, through the real, complete graph. ------------------------
    assert h.jarvis_renderer._current_workspace_profile is None  # never applied yet
    for _ in range(2):
        _reset_wake_detection(h)
        wait_for_active_capture(h.mic)
        h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
        h.llm_client.context_response = (
            "TOPIC: debugging a python script\nENTITIES: script\nREFERENCES_PAST: NO\n"
            "PERSONA: NONE\nSENTIMENT: NEUTRAL"
        )
        h.tts.spoken_event.clear()
        h.stt.pending_transcripts.append("help me debug this function")
        push_utterance(h.audio_backend)
        assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
        wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    assert h.jarvis_renderer._current_workspace_profile is WorkspaceProfile.CODING

    # --- Step 4: a real persona transition (Jarvis -> Minie) runs
    # TransitionEngine's complete seven-phase choreography and ends with
    # Minie's own renderer genuinely mounted. ----------------------------
    class _RecordingOverlay:
        def __init__(self) -> None:
            self.phases: list[TransitionPhase] = []
            self.shown = False
            self.hidden = False

        def show(self) -> None:
            self.shown = True

        def set_phase(self, phase: TransitionPhase) -> None:
            self.phases.append(phase)

        def hide(self) -> None:
            self.hidden = True

    overlay = _RecordingOverlay()
    h.transition_engine.set_overlay(overlay)

    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("talk to minie please")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)

    assert h.persona_manager.active_persona().name == "minie"
    assert h.presentation_controller.mounted_persona_name == "minie"
    assert overlay.shown
    assert overlay.hidden
    assert overlay.phases == [
        TransitionPhase.SAVING_STATE,
        TransitionPhase.SYNCING_MEMORY,
        TransitionPhase.SHOWING_CORE,
        TransitionPhase.PARTICLE_TRANSITION,
        TransitionPhase.LOADING_TARGET,
        TransitionPhase.RESTORING_CONVERSATION,
        TransitionPhase.COMPLETE,
    ]
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- Step 5: "same intelligence, different presentation," half two —
    # the exact same neutral question, now asked of Minie. The fake LLM's
    # own conversational_response is dispatched purely by prompt-template
    # substring match (tests/system/conftest.py's own FakeLanguageModelClient
    # docstring), never by which persona is asking — so the RAW reply text
    # is identical in substance regardless of persona; only VoicePersonality
    # Modulator.shape_pacing()'s own per-persona pacing-marker insertion
    # (voice_warmth-driven) can make the two strings differ verbatim. -----
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: general question\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append(jarvis_question)
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    minie_reply, minie_voice_id = h.tts.speak_calls[-1]
    assert h.persona_manager.active_persona().name == "minie"
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # The brief's own locked rule, checked directly and mechanically:
    # substance (content) is equivalent; presentation (voice, pacing)
    # differs.
    marker = "... "
    assert jarvis_reply.replace(marker, "") == minie_reply.replace(marker, ""), (
        "Same underlying question/decision-trace content produced substantively "
        "different reply text between personas — the brief's own 'one intelligence' "
        "promise may have been violated."
    )
    assert jarvis_voice_id != minie_voice_id  # presentation (voice) genuinely differs

    # --- Step 6: CompanionExperienceEngine's own greeting fires on a
    # brand-new session's first turn — greeting_idle_threshold_seconds is
    # lowered to 0.0 for this one step only (a real session, seconds old,
    # cannot naturally exceed the real 3600s default; see this module's
    # own docstring for why waiting a real hour would be the wrong way to
    # prove this capability, the same reasoning test_level4_part_b_
    # acceptance.py's own _due_item() precedent already established for
    # ReminderEngine). ----------------------------------------------------
    h.companion_experience_engine._config.greeting_idle_threshold_seconds = 0.0
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("hello again")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    greeting_reply, _ = h.tts.speak_calls[-1]
    assert greeting_reply.startswith("Welcome back")
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- Every Level 1-5 Part A module is registered and running through
    # the real, complete CoreManager graph. -------------------------------
    states = h.core_manager.module_states()
    assert set(states) == {
        "task_scheduler",
        "calendar_store",
        "microphone",
        "speech_to_text",
        "text_to_speech",
        "conversation_store",
        "persona_manager",
        "voice_session_manager",
        "quiet_mode_controller",
        "wake_word_detector",
        "communication_pipeline",
        "memory_store",
        "memory_lifecycle_manager",
        "intent_detector",
        "context_analyzer",
        "priority_queue_manager",
        "authority_evaluator",
        "action_audit_log",
        "workflow_store",
        "emotion_detection_engine",
        "emotional_state_manager",
        "presentation_controller",
        # Sprint 5.24 (Level 5 Part B — Companion Intelligence).
        "usage_store",
        "usage_tracker",
        "pattern_store",
        "pattern_recognizer",
        "wellness_tracker",
    }
    assert all(state == "running" for state in states.values())
