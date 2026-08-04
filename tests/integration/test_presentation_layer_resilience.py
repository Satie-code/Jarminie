"""Integration tests for Sprint 5.15 (Error Handling & Recovery
Hardening, Level 5 Part A) — the six named scenarios that specifically
need the real, fully-wired Sprint 5.14 graph to manifest at all (this
sprint's own Integration Considerations). Component-level regression
coverage for each scenario lives at its own owning unit-test file
(tests/unit/presentation/test_vtube_studio_renderer.py for (a),
test_jarvis_renderer.py for (c), test_transition_engine.py for (d),
test_gesture_engine.py for (f)); this file covers only what a
component-level test cannot: (b) a full live turn surviving a broken
emotion pipeline (tests/integration/conftest.py's real pipeline_harness
— see that module's own docstring), and (e) a broken Level 5 Part A
construction never taking a real CoreManager's Level 1-4 modules down
with it (main.py's own composition-root functions, imported directly).
"""

from unittest.mock import MagicMock

import main
from config.schema import AppConfig, PresentationConfig
from core.manager import CoreManager
from presentation.avatar_renderer_registry import NullAvatarRenderer
from presentation.jarvis_renderer import JarvisRenderer

_WAIT_TIMEOUT = 5.0


def _reset_wake_detection(h) -> None:
    h.wake_engine.calls = 0


# --- scenario (b): a broken emotion pipeline still completes the turn --------


def test_a_raising_emotion_detection_engine_still_completes_the_turn(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """EmotionDetectionEngine.estimate() itself already promises "never
    raises" (Sprint 5.1's own contract, confirmed at the unit level by
    tests/unit/emotion/test_detection_engine.py's own
    test_never_raises_for_degenerate_signals) — this test instead proves
    the SURROUNDING turn is resilient even in the deliberately worse
    case where that contract is violated: voice/pipeline.py's own
    _handle_turn_complete() wraps _run_presentation_pipeline() in its
    own narrow try/except (Sprint 5.14), so a real induced failure here
    must still let the turn's own spoken reply complete normally."""
    h = pipeline_harness
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    h.emotion_detection_engine.estimate = MagicMock(
        side_effect=RuntimeError("emotion detection exploded")
    )

    h.stt.pending_transcripts.append("what time is it")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)  # the reply still completed


def test_a_raising_emotional_state_manager_still_completes_the_turn(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """Same as above, for EmotionalStateManager.apply_estimate() —
    Sprint 5.2's own "never raises" contract, deliberately violated here
    to prove the turn itself survives regardless."""
    h = pipeline_harness
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    h.emotional_state_manager.apply_estimate = MagicMock(
        side_effect=RuntimeError("state update exploded")
    )

    h.stt.pending_transcripts.append("what time is it")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)  # the reply still completed


def test_emotional_state_is_simply_not_updated_this_turn_when_the_pipeline_fails(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """The exact behavior the sprint's own scenario (b) text names:
    "EmotionalState simply doesn't update that turn" — not a crash, not
    a corrupted/partial update."""
    h = pipeline_harness
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    h.emotion_detection_engine.estimate = MagicMock(
        side_effect=RuntimeError("emotion detection exploded")
    )
    baseline = h.emotional_state_manager.current_state()

    h.stt.pending_transcripts.append(
        "I'm so stressed and overwhelmed right now, I can't keep up with anything"
    )
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)

    updated = h.emotional_state_manager.current_state()
    assert updated == baseline  # untouched, not partially/incorrectly moved


# --- scenario (e): a broken Level 5 Part A construction (main.py) ------------


class _RecordingModule:
    """Mirrors tests/unit/core/test_manager.py's own _RecordingModule —
    a minimal real ManagedModule stand-in for Levels 1-4."""

    def __init__(self, name: str, calls: list[str]) -> None:
        self._name = name
        self._calls = calls

    def start(self) -> None:
        self._calls.append(f"{self._name}.start")

    def stop(self) -> None:
        self._calls.append(f"{self._name}.stop")

    def health_check(self) -> bool:
        return True


def _fake_level2_modules() -> object:
    return MagicMock(persona_manager=MagicMock(), quiet_mode_controller=MagicMock())


def _fake_level3_modules() -> object:
    return MagicMock(memory_store=MagicMock())


def _fake_core_manager() -> CoreManager:
    return CoreManager(config=AppConfig(), resource_monitor=MagicMock(), config_loader=MagicMock())


def test_null_level5_modules_constructs_a_fully_valid_but_inert_graph():
    core_manager = _fake_core_manager()

    modules = main._null_level5_modules(
        AppConfig(), core_manager, _fake_level2_modules(), _fake_level3_modules()
    )

    assert modules.available is False
    assert isinstance(modules.jarvis_renderer, JarvisRenderer)
    assert isinstance(modules.avatar_renderer, NullAvatarRenderer)
    assert modules.avatar_renderer.is_connected() is False
    # Nothing bound to mount — the exact same "no renderer bound yet"
    # state PresentationController already handles safely pre-5.14.
    modules.presentation_controller.start()
    assert modules.presentation_controller.mounted_persona_name is None
    modules.presentation_controller.refresh()  # must not raise


def test_null_level5_modules_never_raises_even_with_a_broken_avatar_backend_config():
    """The real, concrete failure named in main.py's own docstring:
    create_avatar_renderer() raising UnknownAvatarBackendError for a
    misconfigured avatar_backend. _null_level5_modules() itself must
    never depend on that call succeeding (it uses NullAvatarRenderer
    directly, never create_avatar_renderer())."""
    core_manager = _fake_core_manager()
    broken_config = AppConfig(presentation=PresentationConfig(avatar_backend="not_a_real_backend"))

    modules = main._null_level5_modules(  # must not raise
        broken_config, core_manager, _fake_level2_modules(), _fake_level3_modules()
    )

    assert modules.available is False


def test_register_level5_modules_skips_registration_when_unavailable():
    core_manager = _fake_core_manager()
    modules = main._null_level5_modules(
        AppConfig(), core_manager, _fake_level2_modules(), _fake_level3_modules()
    )

    main._register_level5_modules(core_manager, modules)

    states = core_manager.module_states()
    assert "presentation_controller" not in states
    assert "emotion_detection_engine" not in states
    assert "emotional_state_manager" not in states


def test_a_broken_level5_construction_never_prevents_levels_1_through_4_from_starting():
    """The Acceptance Criteria's own exact words: "A deliberately-broken
    Level 5 Part A construction never prevents Levels 1-4 from starting
    up successfully." Reproduces main()'s own real call-site sequence
    (try _construct_level5_modules(), except: fall back to
    _null_level5_modules(), then _register_level5_modules()) against a
    real CoreManager carrying real (stand-in) Level 1-4 modules."""
    core_manager = _fake_core_manager()
    calls: list[str] = []
    core_manager.register_module("level1_stub", _RecordingModule("level1_stub", calls))
    core_manager.register_module("level4_stub", _RecordingModule("level4_stub", calls))

    try:
        raise RuntimeError("simulated Level 5 Part A construction failure")
    except Exception:
        level5_modules = main._null_level5_modules(
            AppConfig(), core_manager, _fake_level2_modules(), _fake_level3_modules()
        )
    main._register_level5_modules(core_manager, level5_modules)

    core_manager.startup()  # must not raise, and must genuinely start the stand-ins

    assert calls == ["level1_stub.start", "level4_stub.start"]
    assert core_manager.module_states()["level1_stub"] == "running"
    assert core_manager.module_states()["level4_stub"] == "running"
    assert "presentation_controller" not in core_manager.module_states()
