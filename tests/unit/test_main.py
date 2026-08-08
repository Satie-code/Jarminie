"""Unit tests for main.py.

Deliberately narrow: this project tests main.py's actual subsystem wiring
via the extracted _construct_levelN_modules()/_register_levelN_modules()
functions and the full tests/system suite, not by invoking main() itself
(which constructs a real QApplication and blocks on app.exec()). This
file exists for one specific, real risk flagged during Runtime Phase 5
(Runtime Refactor Sprint): a refactorer doing "lazy-loading cleanup"
could plausibly delete or reorder the _prewarm_tts_before_pyside6() call,
believing it's now redundant now that CoquiTextToSpeech.start() is lazy —
it isn't; the two are unrelated fixes for unrelated problems (see
main.py's own docstring for the real PySide6/six.moves import-order bug
this works around, independent of when CoquiTextToSpeech.start() runs).
"""

import ast
import inspect
from unittest.mock import MagicMock

import main
from config.schema import AppConfig
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
from core.runtime_manager import ServiceTier


def _real_core_manager() -> CoreManager:
    resource_monitor = ResourceMonitor(AppConfig().resources)
    return CoreManager(AppConfig(), resource_monitor, config_loader=MagicMock())


def _fake_level3_modules() -> "main._Level3Modules":
    """register_module() never calls a method on the object it's given
    (it only stores the reference, in both ModuleRegistry and
    RuntimeManager) — so a plain MagicMock() per field is sufficient to
    drive _register_level3_modules() for real, without needing a genuine
    Level 3 object graph."""
    return main._Level3Modules(
        intent_detector=MagicMock(),
        context_analyzer=MagicMock(),
        response_generator=MagicMock(),
        memory_retrieval_engine=MagicMock(),
        priority_queue_manager=MagicMock(),
        authority_evaluator=MagicMock(),
        short_term_memory=MagicMock(),
        confidence_scorer=MagicMock(),
        memory_lifecycle_manager=MagicMock(),
        memory_store=MagicMock(),
        real_memory_store=MagicMock(),
    )


def _fake_level2_modules() -> "main._Level2Modules":
    return main._Level2Modules(
        mic=MagicMock(),
        stt=MagicMock(),
        tts=MagicMock(),
        conversation_store=MagicMock(),
        context_manager=MagicMock(),
        persona_manager=MagicMock(),
        session_manager=MagicMock(),
        quiet_mode_controller=MagicMock(),
        wake_word_detector=MagicMock(),
        turn_complete_relay=MagicMock(),
        session_ended_relay=MagicMock(),
        persona_switch_relay=MagicMock(),
    )


def _fake_level4_modules() -> "main._Level4Modules":
    return main._Level4Modules(
        action_registry=MagicMock(),
        action_audit_log=MagicMock(),
        action_recovery_manager=MagicMock(),
        workflow_store=MagicMock(),
        workflow_executor=MagicMock(),
    )


def _fake_level5_modules() -> "main._Level5Modules":
    return main._Level5Modules(
        emotion_detection_engine=MagicMock(),
        emotional_state_manager=MagicMock(),
        emotional_memory=MagicMock(),
        presentation_controller=MagicMock(),
        jarvis_renderer=MagicMock(),
        minie_renderer=MagicMock(),
        avatar_renderer=MagicMock(),
        gesture_engine=MagicMock(),
        transition_engine=MagicMock(),
        adaptive_workspace_controller=MagicMock(),
        companion_experience_engine=MagicMock(),
        voice_personality_modulator=MagicMock(),
        lip_sync_driver=MagicMock(),
    )


def _fake_level5b_modules() -> "main._Level5PartBModules":
    return main._Level5PartBModules(
        usage_store=MagicMock(),
        usage_tracker=MagicMock(),
        wellness_tracker=MagicMock(),
        wellness_escalation_manager=MagicMock(),
        adaptive_wellness_adjuster=MagicMock(),
        pattern_store=MagicMock(),
        pattern_recognizer=MagicMock(),
        dashboard_service=MagicMock(),
        preference_learner=MagicMock(),
        recommendation_engine=MagicMock(),
    )


def test_register_level2_modules_configures_stt_and_tts_idle_timeout():
    """Runtime Phase 9 — speech_to_text/text_to_speech both register with
    idle_timeout_seconds sourced from core_manager.config().runtime.
    default_idle_timeout_seconds (AppConfig()'s own default, 300.0, since
    _real_core_manager() supplies no override)."""
    core_manager = _real_core_manager()
    level2_modules = _fake_level2_modules()

    main._register_level2_modules(core_manager, level2_modules, MagicMock())

    level2_modules.stt.mark_idle_timeout.assert_called_once_with(300.0)
    level2_modules.tts.mark_idle_timeout.assert_called_once_with(300.0)


def test_register_level3_modules_tags_intent_detector_and_context_analyzer_warm():
    """Runtime Phase 7 (Runtime Refactor Sprint) — both move off the
    synchronous Tier A path onto the background warm-up thread."""
    core_manager = _real_core_manager()

    main._register_level3_modules(core_manager, _fake_level3_modules())

    runtime_manager = core_manager.runtime_manager()
    assert runtime_manager.tier_of("intent_detector") is ServiceTier.WARM
    assert runtime_manager.tier_of("context_analyzer") is ServiceTier.WARM
    assert runtime_manager.is_lazy("intent_detector") is False
    assert runtime_manager.is_lazy("context_analyzer") is False


def test_register_level3_modules_keeps_memory_store_lazy_and_warm():
    """Runtime Phase 6 regression guard, re-asserted alongside Phase 7's
    own new tier assignments in the same registration function."""
    core_manager = _real_core_manager()

    main._register_level3_modules(core_manager, _fake_level3_modules())

    runtime_manager = core_manager.runtime_manager()
    assert runtime_manager.tier_of("memory_store") is ServiceTier.WARM
    assert runtime_manager.is_lazy("memory_store") is True
    assert runtime_manager.tier_of("memory_lifecycle_manager") is ServiceTier.WARM
    assert runtime_manager.is_lazy("memory_lifecycle_manager") is False


def test_register_level3_modules_configures_memory_stores_idle_timeout():
    """Runtime Phase 9 — memory_store registers with idle_timeout_seconds
    sourced from core_manager.config().runtime.default_idle_timeout_seconds
    (AppConfig()'s own default, 300.0, since _real_core_manager() supplies
    no override)."""
    core_manager = _real_core_manager()
    level3_modules = _fake_level3_modules()

    main._register_level3_modules(core_manager, level3_modules)

    level3_modules.real_memory_store.mark_idle_timeout.assert_called_once_with(300.0)


def test_register_level3_modules_leaves_priority_queue_and_authority_always_loaded():
    """Neither is on the user's Runtime Phase 4/7 lazy-load list — the
    governing default (anything not explicitly named stays eager) should
    leave both at ServiceTier.ALWAYS_LOADED."""
    core_manager = _real_core_manager()

    main._register_level3_modules(core_manager, _fake_level3_modules())

    runtime_manager = core_manager.runtime_manager()
    assert runtime_manager.tier_of("priority_queue_manager") is ServiceTier.ALWAYS_LOADED
    assert runtime_manager.tier_of("authority_evaluator") is ServiceTier.ALWAYS_LOADED


def test_register_level4_modules_tags_action_audit_log_and_workflow_store_warm():
    """Runtime Phase 8 (Runtime Refactor Sprint) — both move off the
    synchronous Tier A path onto the background warm-up thread."""
    core_manager = _real_core_manager()

    main._register_level4_modules(core_manager, _fake_level4_modules())

    runtime_manager = core_manager.runtime_manager()
    for name in ("action_audit_log", "workflow_store"):
        assert runtime_manager.tier_of(name) is ServiceTier.WARM, name
        assert runtime_manager.is_lazy(name) is False, name


def test_register_level5_modules_tags_all_three_warm_and_not_lazy():
    """Runtime Phase 8 — emotion_detection_engine/emotional_state_manager/
    presentation_controller all move off the synchronous Tier A path."""
    core_manager = _real_core_manager()

    main._register_level5_modules(core_manager, _fake_level5_modules())

    runtime_manager = core_manager.runtime_manager()
    for name in (
        "emotion_detection_engine",
        "emotional_state_manager",
        "presentation_controller",
    ):
        assert runtime_manager.tier_of(name) is ServiceTier.WARM, name
        assert runtime_manager.is_lazy(name) is False, name


def test_register_level5_part_b_modules_tags_all_five_warm_and_not_lazy():
    """Runtime Phase 7 — usage_store/usage_tracker/pattern_store/
    pattern_recognizer/wellness_tracker all move off the synchronous
    Tier A path; none needs lazy=True (no expensive load, no per-turn
    synchronous gate — see main.py's own registration comment)."""
    core_manager = _real_core_manager()

    main._register_level5_part_b_modules(core_manager, _fake_level5b_modules())

    runtime_manager = core_manager.runtime_manager()
    for name in (
        "usage_store",
        "usage_tracker",
        "pattern_store",
        "pattern_recognizer",
        "wellness_tracker",
    ):
        assert runtime_manager.tier_of(name) is ServiceTier.WARM, name
        assert runtime_manager.is_lazy(name) is False, name


def test_prewarm_tts_before_pyside6_is_the_first_statement_in_main():
    """Source-order/AST check, not a runtime reproduction: tests/conftest.py
    already applies the identical prewarm fix suite-wide, so PySide6 is
    already safely cached in sys.modules by the time any test file loads
    — the real crash this guards against is unreproducible inside this
    test process. The only meaningful guard left is confirming main()'s
    own source still calls _prewarm_tts_before_pyside6() as its literal
    first statement, exactly as its own docstring requires ("must run
    before ANY construction below, not merely before ui.app's own
    import" — Sprint 5.14)."""
    source = inspect.getsource(main.main)
    function_def = ast.parse(source).body[0]

    assert isinstance(function_def, ast.FunctionDef)
    first_statement = function_def.body[0]

    assert isinstance(first_statement, ast.Expr)
    assert isinstance(first_statement.value, ast.Call)
    assert isinstance(first_statement.value.func, ast.Name)
    assert first_statement.value.func.id == "_prewarm_tts_before_pyside6"


def test_prewarm_tts_before_pyside6_still_exists_and_is_still_callable():
    """A refactorer removing the function entirely (not just its call
    site) would break the test above too, but this makes the failure
    mode explicit rather than an AttributeError buried in the AST test."""
    assert callable(main._prewarm_tts_before_pyside6)


def test_module_level_prewarm_runs_before_pyside6_touching_imports():
    """Regression test for the real gap the two tests above didn't catch
    (found while debugging a live crash): _prewarm_tts_before_pyside6()
    being main()'s own first statement is not early enough by itself,
    because this file's own top-level `from presentation.jarvis_renderer
    import JarvisRenderer` / `from presentation.minie_renderer import
    MinieRenderer` (both import PySide6 at their own module level) run
    when main.py itself is imported — before main() is ever called.
    Confirms the module-level TTS.api prewarm block (mirroring
    tests/conftest.py's own identical fix) appears earlier in source
    order than either import."""
    source = inspect.getsource(main)
    module_body = ast.parse(source).body

    def _index_of(predicate):
        for i, stmt in enumerate(module_body):
            if predicate(stmt):
                return i
        raise AssertionError("expected statement not found in main.py's module body")

    def _is_prewarm_try(stmt):
        return isinstance(stmt, ast.Try) and any(
            isinstance(inner, ast.Expr)
            and isinstance(inner.value, ast.Call)
            and isinstance(inner.value.func, ast.Attribute)
            and inner.value.func.attr == "import_module"
            for inner in stmt.body
        )

    def _imports_pyside6_touching_renderer(stmt):
        return isinstance(stmt, ast.ImportFrom) and stmt.module in (
            "presentation.jarvis_renderer",
            "presentation.minie_renderer",
        )

    prewarm_index = _index_of(_is_prewarm_try)
    renderer_import_index = _index_of(_imports_pyside6_touching_renderer)

    assert prewarm_index < renderer_import_index
