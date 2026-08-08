"""JARMINEI application entrypoint — the sole composition root.

Constructs concrete subsystem instances and wires them together via
dependency injection; no other file in the codebase should construct
these directly. See docs/sprint_book/sprint_1_5.md, sprint_1_6.md,
sprint_2_12.md (Level 2's Communication Pipeline Integration),
sprint_3_12.md (Level 3's Decision Engine Integration), and
sprint_4_11.md (Level 4 Part A's Workflow & Device Control Integration).

Startup happens inside ui.app.run_app(); shutdown happens inside
MainWindow.closeEvent() when the user closes the window — the Qt event
loop (app.exec()) is what keeps the process alive between the two.

**Runtime stability fix (PySide6 <-> Coqui TTS import-order conflict,
docs/backlog/technical_debt.md item 29's own resolution)**: `ui.app` is
therefore deliberately NOT imported at module level here like everything
else — see `main()`'s own docstring/body for the full root cause and the
`_prewarm_tts_before_pyside6()` call that must run immediately before it.

**Correction to the above, found while debugging a live crash the fix
above did not actually prevent**: calling `_prewarm_tts_before_pyside6()`
as `main()`'s own first statement is not early enough on its own. This
file's own top-level imports below — `from presentation.jarvis_renderer
import JarvisRenderer` and `from presentation.minie_renderer import
MinieRenderer` — both pull in `PySide6.QtCore`/`QtWidgets` (each renderer
module imports PySide6 at its own module level) the moment THIS file
itself is imported, which happens before `main()` is ever called, let
alone its first statement. So PySide6 (and shiboken6's global import
hook) was already loaded by the time `_prewarm_tts_before_pyside6()` ran,
every time, in the real running app — the exact conflict this whole fix
exists to avoid. The block immediately below, before any other import in
this file, is what actually keeps the promise this fix makes; it mirrors
tests/conftest.py's own identical, correctly-ordered prewarm (added for
the identical reason, suite-wide). The later call inside `main()` is kept
too — a cheap sys.modules cache hit once this has already run — so the
existing regression tests guarding that call site stay meaningful.
"""

import importlib

try:
    importlib.import_module("TTS.api")
except Exception:
    pass

import sys  # noqa: I001 — must stay after the prewarm block above, not sorted into it
from dataclasses import dataclass, replace

from analytics.dashboard_data import AnalyticsDashboardService
from analytics.usage_store import UsageStore
from analytics.usage_tracker import UsageTracker
from config import ConfigLoader
from config.schema import (
    AppConfig,
    LearningConfig,
    MemoryConfig,
    RuntimeConfig,
    SchedulerConfig,
    WellnessConfig,
)
from core import configure_logging
from core.logging_setup import get_logger
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
from core.runtime_manager import RuntimeManager, ServiceTier
from database.sqlite_client import SqliteClient
from decision.authority import AuthorityEvaluator
from decision.context_analyzer import ContextAnalyzer
from decision.intent_detector import IntentDetector
from decision.llm_client import OllamaClient
from decision.priority_queue import PriorityQueueManager
from decision.response_generator import ResponseGenerator
from device_control.action_engine import ActionRegistry
from device_control.action_log import ActionAuditLog, ActionRecoveryManager
from device_control.application_manager import ApplicationManager
from device_control.command_executor import CommandExecutionEngine
from device_control.file_operations import FileOperationsManager
from device_control.resource_gate import ActionResourceGate
from device_control.window_manager import WindowManager
from emotion.detection_engine import EmotionDetectionEngine
from emotion.state_manager import EmotionalStateManager
from internet.research_engine import ResearchEngine
from internet.search_provider_registry import create_search_provider_with_fallback
from internet.source_validator import SourceValidator
from internet.summarizer import Summarizer
from learning.pattern_recognizer import PatternRecognizer
from learning.pattern_store import PatternStore
from learning.preference_learner import PreferenceLearner
from learning.recommendation import RecommendationEngine
from memory.chroma_client import ChromaMemoryClient
from memory.confidence_scorer import ConfidenceScorer
from memory.emotional_memory import EmotionalMemory
from memory.event_memory import EventMemory
from memory.lifecycle_manager import MemoryLifecycleManager
from memory.memory_store import LazyMemoryStore, MemoryStore, MemoryStoreProtocol
from memory.persona_scoped_memory import PersonaScopedMemory
from memory.retrieval_engine import MemoryRetrievalEngine
from memory.short_term_memory import ShortTermMemory
from personas.jarvis import JarvisPersona
from personas.minie import MiniePersona
from personas.persona_manager import PersonaManager
from presentation.adaptive_workspace import AdaptiveWorkspaceController
from presentation.avatar_renderer import AvatarRenderer
from presentation.avatar_renderer_registry import NullAvatarRenderer, create_avatar_renderer
from presentation.companion_experience import CompanionExperienceEngine
from presentation.gesture_engine import GestureEngine
from presentation.jarvis_renderer import JarvisRenderer
from presentation.jarvis_state_computer import JarvisPresentationStateComputer
from presentation.lip_sync import LipSyncDriver
from presentation.minie_renderer import MinieRenderer
from presentation.minie_state_computer import MiniePresentationStateComputer
from presentation.presentation_controller import PresentationController
from presentation.transition_engine import TransitionEngine
from presentation.voice_personality import VoicePersonalityModulator
from scheduler.calendar_store import CalendarStore
from scheduler.reminder_engine import ReminderEngine
from scheduler.task_scheduler import TaskScheduler
from security.confirmation_service import VoiceConfirmationService
from security.permission_gate import PermissionGate
from security.policy_engine import PermissionPolicyEngine
from voice.context_manager import ContextManager
from voice.conversation_store import ConversationSessionStore
from voice.microphone import MicrophoneManager, SoundDeviceAudioBackend
from voice.pipeline import CallbackRelay, CommunicationPipeline
from voice.quiet_mode import QuietModeController
from voice.session_manager import VoiceSessionManager
from voice.speech_to_text import LazySpeechToText, WhisperSpeechToText
from voice.text_to_speech import CoquiTextToSpeech, LazyTextToSpeech, SoundDeviceAudioOutput
from voice.wake_word import OpenWakeWordEngine, WakeWordDetector
from wellness.adaptive_wellness import AdaptiveWellnessAdjuster
from wellness.escalation import WellnessEscalationManager
from wellness.wellness_tracker import WellnessTracker
from workflow.workflow_executor import WorkflowExecutor
from workflow.workflow_store import WorkflowStore

logger = get_logger(__name__)


@dataclass
class _Level2Modules:
    """Bundles every Level 2 (Communication) object except
    CommunicationPipeline itself — CommunicationPipeline additionally
    needs level3_modules/level4_modules (both constructed after this
    bundle), so it's built separately by _construct_pipeline() once all
    three levels' prerequisite objects exist. session_manager/
    persona_manager are the two objects Level 4's VoiceConfirmationService
    (Sprint 4.7/4.11) needs — the first Level 4 dependency on already-
    built Level 2 objects, which is why level4_modules is constructed
    after this bundle, not before it (the reverse of Level 3's own
    construct-before-Level-2 ordering)."""

    mic: MicrophoneManager
    stt: WhisperSpeechToText
    tts: CoquiTextToSpeech
    conversation_store: ConversationSessionStore
    context_manager: ContextManager
    persona_manager: PersonaManager
    session_manager: VoiceSessionManager
    quiet_mode_controller: QuietModeController
    wake_word_detector: WakeWordDetector
    turn_complete_relay: CallbackRelay
    session_ended_relay: CallbackRelay
    persona_switch_relay: CallbackRelay


@dataclass
class _Level3Modules:
    """Bundles every Level 3 object _register_level2_modules() (to build
    CommunicationPipeline) and _register_level3_modules() (to register
    the ManagedModules among them) need — private to this file, matching
    the composition-root's own "only this file constructs concrete
    subsystem instances" rule (Sprint 1.5)."""

    intent_detector: IntentDetector
    context_analyzer: ContextAnalyzer
    response_generator: ResponseGenerator
    memory_retrieval_engine: MemoryRetrievalEngine
    priority_queue_manager: PriorityQueueManager
    authority_evaluator: AuthorityEvaluator
    short_term_memory: ShortTermMemory
    confidence_scorer: ConfidenceScorer
    memory_lifecycle_manager: MemoryLifecycleManager
    memory_store: MemoryStoreProtocol
    real_memory_store: MemoryStore


@dataclass
class _Level4Modules:
    """Bundles every Level 4 Part A (Device Control & Workflow
    Automation) object CommunicationPipeline or CoreManager registration
    needs. permission_gate/policy_engine/confirmation_service/
    resource_gate and all four executors are constructed inside
    _construct_level4_modules() but not returned here — nothing outside
    that function references them directly; they're reached only through
    action_registry.dispatch(). action_recovery_manager IS kept here even
    though nothing calls it yet (backlog/technical_debt.md item 24: a
    voice-triggered "undo that" surface is real, wanted functionality,
    explicitly out of this Sprint Book's own scope until a future sprint
    names it) — constructed per this sprint's own Files to Modify, ready
    for that future caller."""

    action_registry: ActionRegistry
    action_audit_log: ActionAuditLog
    action_recovery_manager: ActionRecoveryManager
    workflow_store: WorkflowStore
    workflow_executor: WorkflowExecutor


@dataclass
class _Level4PartBModules:
    """Bundles every Level 4 Part B (Scheduler & Internet Agent) object
    CommunicationPipeline or CoreManager registration needs (Sprint
    4.18). Only task_scheduler and calendar_store are real ManagedModules
    — reminder_engine/research_engine/source_validator/summarizer are
    all plain, lifecycle-free collaborators, per each one's own
    originating sprint (4.15/4.16/4.16/4.17)."""

    task_scheduler: TaskScheduler
    calendar_store: CalendarStore
    reminder_engine: ReminderEngine
    research_engine: ResearchEngine
    source_validator: SourceValidator
    summarizer: Summarizer


@dataclass
class _Level5Modules:
    """Bundles every Level 5 Part A (Emotional Intelligence & Presentation
    Layer) object CommunicationPipeline, CoreManager registration, or
    ui/main_window.py's own Qt-layer assembly needs (Sprint 5.14). Only
    presentation_controller/emotion_detection_engine/emotional_state_manager
    are real ManagedModules — every other object here is plain and
    lifecycle-free (each one's own originating sprint, 5.1-5.13,
    documented this explicitly), the same "only register what has a real
    lifecycle" discipline every prior level's own Modules dataclass
    already established. persona_switch_relay is not a Level 5 object at
    all (it's constructed alongside PersonaManager in
    _construct_level2_modules(), Level 2) but is threaded through
    main()'s own body once transition_engine exists — see main()'s own
    ordering comment for the circular-construction problem this resolves,
    the identical CallbackRelay indirection voice/pipeline.py's own
    turn_complete_relay/session_ended_relay already established.

    available (Sprint 5.15, scenario e) is True for a real construction
    via _construct_level5_modules() and False only for the fallback
    _null_level5_modules() below — every field is still a real, valid
    object either way (CommunicationPipeline/run_app() both require all
    of them unconditionally; widening either to tolerate None would be
    a redesign, not this sprint's own "narrow, targeted fix" mandate),
    just wired inertly when available is False. _register_level5_modules()
    is the one real reader of this flag."""

    emotion_detection_engine: EmotionDetectionEngine
    emotional_state_manager: EmotionalStateManager
    emotional_memory: EmotionalMemory
    presentation_controller: PresentationController
    jarvis_renderer: JarvisRenderer
    minie_renderer: MinieRenderer
    avatar_renderer: AvatarRenderer
    gesture_engine: GestureEngine
    transition_engine: TransitionEngine
    adaptive_workspace_controller: AdaptiveWorkspaceController
    companion_experience_engine: CompanionExperienceEngine
    voice_personality_modulator: VoicePersonalityModulator
    lip_sync_driver: LipSyncDriver
    available: bool = True


@dataclass
class _Level5PartBModules:
    """Bundles every Level 5 Part B (Companion Intelligence — Wellness/
    Analytics/Learning) object CommunicationPipeline or CoreManager
    registration needs (Sprint 5.24). Mirrors _Level5Modules' own shape
    including Sprint 5.15's null-fallback-on-construction-failure
    discipline, but with a deliberately SIMPLER fallback than that
    dataclass's own always-real-but-inert objects: every field here is
    typed Type | None (matching CommunicationPipeline's own new
    constructor parameters, this sprint's own literal text), since none
    of Part B's objects are called unconditionally on every single turn
    the way Part A's presentation objects are — a plain None threaded
    through and guarded at each real call site is simpler than
    constructing a whole parallel inert object graph for objects nothing
    calls unless a real WELLNESS-routed turn or a real TaskScheduler job
    tick actually reaches them.

    Only usage_store/usage_tracker/pattern_store/pattern_recognizer/
    wellness_tracker are real ManagedModules — wellness_escalation_manager/
    adaptive_wellness_adjuster/dashboard_service/preference_learner/
    recommendation_engine are all plain, lifecycle-free collaborators, per
    each one's own originating sprint (5.19/5.22/5.20/5.23 respectively)."""

    usage_store: UsageStore | None
    usage_tracker: UsageTracker | None
    wellness_tracker: WellnessTracker | None
    wellness_escalation_manager: WellnessEscalationManager | None
    adaptive_wellness_adjuster: AdaptiveWellnessAdjuster | None
    pattern_store: PatternStore | None
    pattern_recognizer: PatternRecognizer | None
    dashboard_service: AnalyticsDashboardService | None
    preference_learner: PreferenceLearner | None
    recommendation_engine: RecommendationEngine | None
    available: bool = True


def _prewarm_tts_before_pyside6() -> None:
    """Must run before ANY import that could pull in PySide6, including
    the local `from ui.app import run_app` immediately below this call
    in `main()` — root-caused, not guessed: PySide6/shiboken6 installs a
    global import hook the moment `PySide6.QtWidgets` is first imported
    anywhere in the process (its own `__feature__`-support machinery),
    which then intercepts EVERY later import and calls
    `inspect.getsource()` on the freshly-imported module to check
    whether it "uses PySide". Coqui TTS transitively imports `six.moves`
    (TTS -> matplotlib.pyplot -> matplotlib.category -> dateutil.parser
    -> dateutil.tz -> six.moves) — a synthetic, loader-backed module
    `six`'s own `_SixMetaPathImporter` constructs. When PySide6's hook's
    own `inspect.getsource()` check runs against that synthetic module,
    formatting its own "is a built-in module" error message needs
    `repr(module)`, which Python 3.12's importlib then fails to compute
    for this specific loader shape: `AttributeError:
    '_SixMetaPathImporter' object has no attribute '_path'` (a real gap
    in the `six` package itself, unrelated to this project, only ever
    exercised because PySide6's hook forces this otherwise-never-taken
    code path). Confirmed via direct reproduction before writing this
    fix, not assumed: `import TTS` alone succeeds; `import
    PySide6.QtWidgets` then `import TTS` reliably crashes with the exact
    error above; the reverse order does not crash, and PySide6 itself
    still works normally afterward (a real `QApplication` constructs
    fine). See docs/backlog/technical_debt.md item 29's own resolution.

    voice/text_to_speech.py's `CoquiTextToSpeech` already lazy-imports
    `TTS.api` inside `start()` (Sprint 2.4), specifically so the real,
    heavy TTS/torch import cost is only ever paid when TTS is actually
    needed — but that laziness alone does not fix this conflict, since
    `ui/app.py`'s own `run_app()` imports `PySide6.QtWidgets` and
    constructs a real `QApplication` BEFORE `core_manager.startup()`
    ever reaches `CoquiTextToSpeech.start()`'s own lazy import — meaning
    the conflict was hit every time in the real running app, regardless
    of that existing laziness. Pre-warming the identical import here —
    immediately before `ui.app` is imported below, itself deliberately
    deferred to inside `main()` rather than this module's own top-level
    imports specifically so this ordering is achievable at all — makes
    Python cache the real `TTS`/`six.moves` modules in `sys.modules`
    before PySide6's hook is ever installed; `CoquiTextToSpeech.
    start()`'s own later, still-lazy call then just reuses what's
    already imported, unaffected by the hook. This changes WHEN an
    already-unavoidable import cost is paid (slightly earlier, at
    process start), not whether it's paid — no new, ongoing cost is
    introduced.

    Deliberately swallows any failure here: a genuine TTS-import problem
    (the package missing or broken) must not crash the whole application
    at startup — that failure is already handled correctly, later, by
    `CoquiTextToSpeech.start()`'s own `TextToSpeechError` path. This
    function's only job is import ORDER, never import success — if the
    pre-warm itself fails, `start()` will attempt (and correctly report)
    the same import again anyway."""
    import importlib

    try:
        importlib.import_module("TTS.api")
    except Exception:
        pass


def main() -> int:
    # Sprint 5.14: must run before ANY construction below, not merely
    # before ui.app's own import as previously — presentation/
    # jarvis_renderer.py/presentation/minie_renderer.py (both
    # Level 5 objects _construct_level5_modules() builds) import
    # PySide6.QtCore/QtWidgets at THEIR OWN module level, so simply
    # importing either module (which _construct_level5_modules() must,
    # to construct real JarvisRenderer/MinieRenderer instances) now
    # triggers PySide6's own import hook exactly as early as ui.app's
    # import previously did. Moving the call here — the true first line
    # of real work — keeps the fix's own root-cause contract intact
    # ("Coqui TTS/six.moves cached in sys.modules before PySide6's hook
    # is ever installed") regardless of which module ends up being the
    # first to actually import PySide6. See this function's own
    # docstring for the full history.
    _prewarm_tts_before_pyside6()

    config_loader = ConfigLoader()
    config = config_loader.load()
    configure_logging(config.logging)

    resource_monitor = ResourceMonitor(config.resources)
    core_manager = CoreManager(config, resource_monitor, config_loader)

    # Construction order: Level 3 first (no dependency on Level 2/4),
    # then Level 2 (VoiceConfirmationService, built inside Level 4,
    # needs its session_manager/persona_manager), then Level 4 Part A
    # (needs both Level 2 and Level 3 objects), then Level 4 Part B
    # (needs Level 3's priority_queue_manager), then Level 5 Part A
    # (needs Level 2's persona_manager/quiet_mode_controller and Level
    # 3's memory_store — constructed after Level 2 for that reason,
    # per _Level5Modules' own docstring; before-or-after Level 4/4B is
    # immaterial, neither depends on Level 5), then Level 5 Part B (needs
    # Level 4B's task_scheduler and Level 5 Part A's own
    # emotional_state_manager — constructed after both for that reason),
    # then the pipeline itself (needs all six). Registration order is
    # intentionally different — see _register_level4_part_b_early()'s,
    # _register_level3_modules()'s, and _register_level4_modules()'s own
    # docstrings for the two distinct ordering constraints this project
    # now balances: Level 3/4/5 Part A/4B/5B's remaining registrations
    # all happen AFTER communication_pipeline (keeping the
    # wake_word_detector-to-pipeline relay-wiring gap tight), while
    # task_scheduler/calendar_store are the one deliberate exception,
    # registered FIRST, before even Level 2 — CommunicationPipeline.
    # start() (Sprint 4.18) calls task_scheduler.add_job() directly,
    # which requires task_scheduler to already be started.
    level3_modules = _construct_level3_modules(config, resource_monitor, core_manager)
    level2_modules = _construct_level2_modules(config, core_manager)
    level4_modules = _construct_level4_modules(
        config, resource_monitor, level3_modules, level2_modules
    )
    level4b_modules = _construct_level4_part_b_modules(config, level3_modules)
    # Sprint 5.15, scenario (e): a genuine Level 5 Part A construction
    # failure (e.g. an invalid PresentationConfig, though AppConfig.
    # validate() already ran and should have caught most such cases
    # above — or create_avatar_renderer() raising UnknownAvatarBackendError
    # for a misconfigured avatar_backend) must not take Levels 1-4 down
    # with it — "Presentation never changes intelligence" at the
    # availability level, not just the content level (this sprint's own
    # Purpose). See _null_level5_modules()'s own docstring for exactly
    # what "Level 5 Part A simply absent" means concretely here.
    try:
        level5_modules = _construct_level5_modules(
            config, core_manager, level2_modules, level3_modules
        )
    except Exception:
        logger.exception(
            "Level 5 Part A construction failed; continuing startup with Levels 1-4 intact "
            "and Level 5 Part A unavailable."
        )
        level5_modules = _null_level5_modules(config, core_manager, level2_modules, level3_modules)

    # Sprint 5.24, mirroring Sprint 5.15 scenario (e)'s own discipline for
    # Level 5 Part A immediately above: a genuine Level 5 Part B
    # construction failure must not take Levels 1-5 Part A down with it.
    # Constructed after level5_modules is resolved (whether by the real
    # path or its own null fallback) — WellnessTracker's own optional
    # stress-sensitivity input needs level5_modules.emotional_state_manager,
    # which _null_level5_modules() still constructs for real either way
    # (see that function's own docstring).
    try:
        level5b_modules = _construct_level5_part_b_modules(
            config,
            level4b_modules.task_scheduler,
            level5_modules.emotional_state_manager,
            level3_modules.memory_store,
        )
    except Exception:
        logger.exception(
            "Level 5 Part B construction failed; continuing startup with Levels 1-5 Part A "
            "intact and Level 5 Part B unavailable."
        )
        level5b_modules = _null_level5_part_b_modules()

    # Resolves the real circular-construction problem Sprint 5.10's own
    # docstring named explicitly: PersonaManager (Level 2) must be
    # constructed with on_switch already set, but its real target,
    # TransitionEngine.transition, belongs to a TransitionEngine that
    # itself needs a PresentationController that needs this same
    # PersonaManager already built. level2_modules.persona_switch_relay
    # (a CallbackRelay, the identical indirection turn_complete_relay/
    # session_ended_relay already use for the analogous Level 2/3
    # ordering problem) stood in at PersonaManager's own construction
    # time; now that transition_engine really exists, point it at the
    # real target.
    level2_modules.persona_switch_relay.target = level5_modules.transition_engine.transition

    pipeline = _construct_pipeline(
        level2_modules, level3_modules, level4_modules, level4b_modules, level5_modules,
        level5b_modules, config.scheduler, config.memory, config.learning, config.wellness,
        core_manager.runtime_manager(), resource_monitor, config.runtime,
    )

    _register_level4_part_b_early(core_manager, level4b_modules)
    _register_level2_modules(core_manager, level2_modules, pipeline)
    _register_level3_modules(core_manager, level3_modules)
    _register_level4_modules(core_manager, level4_modules)
    _register_level5_modules(core_manager, level5_modules)
    _register_level5_part_b_modules(core_manager, level5b_modules)

    # ui.app is deliberately imported here, locally, rather than at this
    # module's own top level, so that _prewarm_tts_before_pyside6() above
    # (now this function's own first real statement) still runs before
    # PySide6 is definitely imported via this path too, even though — as
    # of Sprint 5.14 — it is no longer the only path that could trigger it.
    from ui.app import run_app

    return run_app(
        core_manager,
        level5_modules.presentation_controller,
        level5_modules.jarvis_renderer,
        level5_modules.minie_renderer,
        level5_modules.transition_engine,
    )


def _construct_level2_modules(config: AppConfig, core_manager: CoreManager) -> _Level2Modules:
    """Construct every Level 2 (Communication) subsystem via DI except
    CommunicationPipeline itself — see _Level2Modules' own docstring for
    why. VoiceSessionManager.on_turn_complete/on_session_ended cannot yet
    point at their real targets when VoiceSessionManager itself is
    constructed (QuietModeController and CommunicationPipeline, which own
    those targets, are built later) — CallbackRelay (voice/pipeline.py)
    stands in for both until CommunicationPipeline's own start() aims
    them at the real methods.

    Runtime Phase 5 (Runtime Refactor Sprint): core_manager is now a
    parameter (matching _construct_level5_modules()'s own established
    precedent for needing it) purely so this function can reach
    core_manager.runtime_manager() — VoiceSessionManager is wired with
    LazySpeechToText/LazyTextToSpeech proxies (real_stt/real_tts's
    start()/stop() timing is RuntimeManager's decision now, not
    CoreManager's own registration-order-driven eager start), while the
    REAL WhisperSpeechToText/CoquiTextToSpeech instances (real_stt/
    real_tts) are what _Level2Modules.stt/.tts hold and what
    _register_level2_modules() actually registers — the proxies are
    local to this function, needed only by VoiceSessionManager.
    """
    voice_config = config.voice
    model_config = config.models
    database_config = config.database

    mic = MicrophoneManager(voice_config, SoundDeviceAudioBackend())
    real_stt = WhisperSpeechToText(model_config)
    real_tts = CoquiTextToSpeech(model_config, SoundDeviceAudioOutput())
    runtime_manager = core_manager.runtime_manager()
    stt = LazySpeechToText(real_stt, "speech_to_text", runtime_manager)
    tts = LazyTextToSpeech(real_tts, "text_to_speech", runtime_manager)

    sqlite_client = SqliteClient(database_config.sqlite_path)
    conversation_store = ConversationSessionStore(sqlite_client, database_config)
    context_manager = ContextManager(conversation_store)

    # Sprint 5.14: persona_switch_relay stands in for PersonaManager's
    # on_switch until TransitionEngine (Level 5, built after this bundle)
    # really exists — see main()'s own docstring comment at the call
    # site that later sets .target to transition_engine.transition, and
    # this module's own CallbackRelay docstring for the general pattern.
    persona_switch_relay = CallbackRelay()
    jarvis = JarvisPersona(voice_config, config.emotion)
    minie = MiniePersona(voice_config, config.emotion)
    persona_manager = PersonaManager(jarvis, minie, voice_config, on_switch=persona_switch_relay)

    turn_complete_relay = CallbackRelay()
    session_ended_relay = CallbackRelay()
    session_manager = VoiceSessionManager(
        mic, stt, tts, voice_config, turn_complete_relay, session_ended_relay
    )
    quiet_mode_controller = QuietModeController(session_manager)

    wake_word_engine = OpenWakeWordEngine(voice_config)
    wake_word_detector = WakeWordDetector(
        mic, wake_word_engine, quiet_mode_controller._on_wake_word_detected
    )

    return _Level2Modules(
        mic=mic,
        stt=real_stt,
        tts=real_tts,
        conversation_store=conversation_store,
        context_manager=context_manager,
        persona_manager=persona_manager,
        session_manager=session_manager,
        quiet_mode_controller=quiet_mode_controller,
        wake_word_detector=wake_word_detector,
        turn_complete_relay=turn_complete_relay,
        session_ended_relay=session_ended_relay,
        persona_switch_relay=persona_switch_relay,
    )


def _construct_level3_modules(
    config: AppConfig, resource_monitor: ResourceMonitor, core_manager: CoreManager
) -> _Level3Modules:
    """Construct every Level 3 (Memory Engine, Dynamic Memory, Decision
    Engine) subsystem via DI — construction only, no CoreManager
    registration (see _register_level3_modules() below for why the two
    are deliberately separate calls, made at different points in
    main()). Has no dependency on Level 2 or Level 4, so it's
    constructed first, before either — CommunicationPipeline (built last,
    by _construct_pipeline(), once every level's objects exist) is what
    actually holds the reference to what this function returns.
    approved_emergency_procedures stays at AuthorityEvaluator's own empty
    default here — Sprint 4.7 reviewed and deliberately left it empty
    (see decision/authority.py's own docstring); this sprint does not
    itself decide the whitelist's contents, per sprint_4_11.md's own
    Integration Considerations.

    Runtime Phase 6 (Runtime Refactor Sprint): core_manager is now a
    parameter (matching _construct_level2_modules()'s own Runtime Phase 5
    precedent) purely so this function can reach core_manager.
    runtime_manager() — every consumer that could plausibly run before
    Memory Store's own background warm-up finishes (persona_scoped_memory/
    event_memory/short_term_memory, and — via _Level3Modules.memory_store
    — Level 5's EmotionalMemory and Level 5B's PreferenceLearner) is wired
    with a LazyMemoryStore proxy instead of the real MemoryStore.
    memory_lifecycle_manager is the one deliberate exception, wired with
    real_memory_store directly — see LazyMemoryStore's own docstring
    (memory/memory_store.py) for why threading the proxy through it too
    would be pure duplication, not a correctness need."""
    database_config = config.database
    memory_config = config.memory
    model_config = config.models

    sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)
    real_memory_store = MemoryStore(sqlite_client, chroma_client)
    runtime_manager = core_manager.runtime_manager()
    memory_store = LazyMemoryStore(real_memory_store, "memory_store", runtime_manager)

    persona_scoped_memory = PersonaScopedMemory(memory_store)
    event_memory = EventMemory(memory_store)
    short_term_memory = ShortTermMemory(memory_store, memory_config)
    confidence_scorer = ConfidenceScorer(memory_config)
    memory_lifecycle_manager = MemoryLifecycleManager(
        real_memory_store, confidence_scorer, memory_config
    )
    memory_retrieval_engine = MemoryRetrievalEngine(
        persona_scoped_memory, event_memory, short_term_memory, confidence_scorer, memory_config
    )

    llm_client = OllamaClient(model_config)
    intent_detector = IntentDetector(llm_client, model_config)
    context_analyzer = ContextAnalyzer(llm_client, model_config)
    # Reuses the same llm_client/model_config as intent_detector/
    # context_analyzer above — no second OllamaClient, unlike Summarizer's
    # own deliberately-separate one (which exists only to honor
    # InternetConfig.summarization_model's optional model override; a
    # conversational reply has no equivalent per-engine override need).
    response_generator = ResponseGenerator(llm_client, model_config)

    priority_queue_manager = PriorityQueueManager(resource_monitor)
    authority_evaluator = AuthorityEvaluator()

    return _Level3Modules(
        intent_detector=intent_detector,
        context_analyzer=context_analyzer,
        response_generator=response_generator,
        memory_retrieval_engine=memory_retrieval_engine,
        priority_queue_manager=priority_queue_manager,
        authority_evaluator=authority_evaluator,
        short_term_memory=short_term_memory,
        confidence_scorer=confidence_scorer,
        memory_lifecycle_manager=memory_lifecycle_manager,
        memory_store=memory_store,
        real_memory_store=real_memory_store,
    )


def _construct_level4_modules(
    config: AppConfig,
    resource_monitor: ResourceMonitor,
    level3_modules: _Level3Modules,
    level2_modules: _Level2Modules,
) -> _Level4Modules:
    """Construct every Level 4 Part A (Device Control & Workflow
    Automation) subsystem via DI — construction only, no CoreManager
    registration (see _register_level4_modules() below, the same
    construct/register split _construct_level3_modules()/
    _register_level3_modules() already established). Needs
    level2_modules (VoiceConfirmationService depends on session_manager/
    persona_manager — the first Level 4 dependency on already-built
    Level 2 objects) and level3_modules (PermissionGate depends on
    authority_evaluator; ActionResourceGate depends on
    priority_queue_manager) already constructed, so this runs after
    both — unlike Level 3, which is constructed before Level 2.

    Every ActionExecutor (ApplicationManager, FileOperationsManager,
    WindowManager, CommandExecutionEngine) and every non-ManagedModule
    collaborator (PermissionGate, PermissionPolicyEngine,
    ConfirmationService, ActionResourceGate, ActionRecoveryManager) is
    plain and lifecycle-free, per each one's own originating sprint —
    only ActionAuditLog and WorkflowStore are real ManagedModules among
    everything constructed here.
    """
    device_control_config = config.device_control
    security_config = config.security
    workflow_config = config.workflow
    database_config = config.database

    policy_engine = PermissionPolicyEngine(security_config)
    confirmation_service = VoiceConfirmationService(
        level2_modules.session_manager,
        level2_modules.persona_manager,
        security_config.confirmation_timeout_seconds,
    )
    permission_gate = PermissionGate(
        level3_modules.authority_evaluator,
        policy_engine,
        confirmation_service,
        device_control_config,
    )
    resource_gate = ActionResourceGate(
        resource_monitor, level3_modules.priority_queue_manager, device_control_config
    )

    audit_sqlite_client = SqliteClient(database_config.sqlite_path)
    audit_log = ActionAuditLog(audit_sqlite_client, device_control_config)

    action_registry = ActionRegistry(
        permission_gate,
        resource_gate,
        audit_log,
        max_retry_attempts=device_control_config.max_retry_attempts,
    )

    application_manager = ApplicationManager(device_control_config)
    file_operations_manager = FileOperationsManager(device_control_config)
    window_manager = WindowManager(device_control_config)
    command_executor = CommandExecutionEngine(device_control_config)
    for executor in (
        application_manager,
        file_operations_manager,
        window_manager,
        command_executor,
    ):
        action_registry.register(executor)

    action_recovery_manager = ActionRecoveryManager(
        audit_log, file_operations_manager, application_manager
    )

    workflow_sqlite_client = SqliteClient(database_config.sqlite_path)
    workflow_store = WorkflowStore(workflow_sqlite_client, workflow_config)
    workflow_executor = WorkflowExecutor(
        workflow_store, action_registry, policy_engine, confirmation_service, workflow_config
    )

    return _Level4Modules(
        action_registry=action_registry,
        action_audit_log=audit_log,
        action_recovery_manager=action_recovery_manager,
        workflow_store=workflow_store,
        workflow_executor=workflow_executor,
    )


def _construct_level4_part_b_modules(
    config: AppConfig, level3_modules: _Level3Modules
) -> _Level4PartBModules:
    """Construct every Level 4 Part B (Scheduler & Internet Agent)
    subsystem via DI — construction only, no CoreManager registration
    (see _register_level4_part_b_early() below). Needs level3_modules
    (ReminderEngine depends on priority_queue_manager) already
    constructed.

    Summarizer gets its OWN, separately-constructed OllamaClient rather
    than reusing Level 3's — internet_config.summarization_model exists
    specifically to let Summarization use a different model than
    IntentDetector/ContextAnalyzer (see config/schema.py's
    InternetConfig docstring); this is the first real wiring decision
    that actually reads that field, resolving what was previously
    "purely informational... guide Sprint 4.18's own main.py wiring."
    None (the default) falls back to model_config.ollama_model exactly
    as documented."""
    scheduler_config = config.scheduler
    internet_config = config.internet
    model_config = config.models
    database_config = config.database

    task_scheduler = TaskScheduler()

    calendar_sqlite_client = SqliteClient(database_config.sqlite_path)
    calendar_store = CalendarStore(calendar_sqlite_client, scheduler_config)
    reminder_engine = ReminderEngine(
        calendar_store, level3_modules.priority_queue_manager, task_scheduler, scheduler_config
    )

    # create_search_provider_with_fallback() (Runtime Stability & Internet
    # Layer Refactor, 2026-08-01), not the single-provider create_search_
    # provider() — the real, live default behavior is now
    # InternetConfig.search_providers' own multi-provider fallback chain,
    # not a single hardcoded/configured provider. See internet/
    # search_provider_registry.py's own docstring.
    search_provider = create_search_provider_with_fallback(internet_config)
    research_engine = ResearchEngine(search_provider, internet_config)
    source_validator = SourceValidator(internet_config)

    summarizer_model_config = (
        replace(model_config, ollama_model=internet_config.summarization_model)
        if internet_config.summarization_model
        else model_config
    )
    summarizer_llm_client = OllamaClient(summarizer_model_config)
    summarizer = Summarizer(summarizer_llm_client, internet_config, model_config)

    return _Level4PartBModules(
        task_scheduler=task_scheduler,
        calendar_store=calendar_store,
        reminder_engine=reminder_engine,
        research_engine=research_engine,
        source_validator=source_validator,
        summarizer=summarizer,
    )


def _construct_level5_modules(
    config: AppConfig,
    core_manager: CoreManager,
    level2_modules: _Level2Modules,
    level3_modules: _Level3Modules,
) -> _Level5Modules:
    """Construct every Level 5 Part A (Emotional Intelligence &
    Presentation Layer) subsystem via DI — construction only, no
    CoreManager registration (see _register_level5_modules() below).
    Needs level2_modules.persona_manager/quiet_mode_controller
    (PresentationController depends on both) and level3_modules.memory_store
    (EmotionalMemory depends on it) already constructed.

    event_memory is constructed fresh here (a second instance alongside
    the one _construct_level3_modules() already built to feed
    memory_retrieval_engine) rather than threaded through _Level3Modules
    — it is a plain, stateless wrapper over memory_store (Sprint 3.3's
    own "not a ManagedModule — owns no resource of its own" design), the
    same "cheap to construct twice, not worth widening an existing
    dataclass for" reasoning _construct_level4_modules()'s own
    audit_sqlite_client/workflow_sqlite_client already established for
    SqliteClient.

    avatar_backend construction (create_avatar_renderer()) can raise
    UnknownAvatarBackendError — deliberately NOT caught here either way
    (this function's own contract stays "construct or raise," per Sprint
    5.15's own scenario (e) text: "not inside the function itself,
    keeping the function's own contract clean"). **Superseded note**:
    this docstring previously said such a failure "must stop startup
    loudly" as this project's own final word — true when this function
    had no live caller (pre-Sprint 5.14) and true in isolation today,
    but main()'s own call site now wraps this whole function in a
    try/except (Sprint 5.15, scenario e) and falls back to
    _null_level5_modules() below rather than letting ANY Level 5 Part A
    construction failure take Levels 1-4 down with it — a real,
    considered supersession of the "fail fast" instinct recorded here at
    Sprint 5.8, disclosed rather than silently reversed. See main()'s
    own call site and _null_level5_modules()'s docstring for the full
    reasoning.
    """
    emotion_config = config.emotion
    presentation_config = config.presentation
    memory_config = config.memory

    emotion_detection_engine = EmotionDetectionEngine(emotion_config)
    emotional_state_manager = EmotionalStateManager(emotion_config)

    event_memory = EventMemory(level3_modules.memory_store)
    emotional_memory = EmotionalMemory(level3_modules.memory_store, memory_config)

    gesture_engine = GestureEngine(presentation_config)

    jarvis_state_computer = JarvisPresentationStateComputer(presentation_config)
    minie_state_computer = MiniePresentationStateComputer(presentation_config)
    jarvis_renderer = JarvisRenderer(presentation_config, core_manager)
    avatar_renderer = create_avatar_renderer(presentation_config)
    minie_renderer = MinieRenderer(avatar_renderer, presentation_config, core_manager)

    presentation_controller = PresentationController(
        persona_manager=level2_modules.persona_manager,
        emotional_state_manager=emotional_state_manager,
        quiet_mode_controller=level2_modules.quiet_mode_controller,
        state_computers={"jarvis": jarvis_state_computer, "minie": minie_state_computer},
        renderers={"jarvis": jarvis_renderer, "minie": minie_renderer},
        gesture_engine=gesture_engine,
    )
    # overlay is set later, once a real QApplication and PresentationHostWidget
    # exist to parent a real QtTransitionOverlay to — see
    # TransitionEngine.set_overlay()'s own docstring.
    transition_engine = TransitionEngine(presentation_controller, presentation_config)

    adaptive_workspace_controller = AdaptiveWorkspaceController(presentation_config)
    companion_experience_engine = CompanionExperienceEngine(
        emotional_memory, event_memory, presentation_config
    )
    voice_personality_modulator = VoicePersonalityModulator(presentation_config)
    lip_sync_driver = LipSyncDriver(presentation_config)

    return _Level5Modules(
        emotion_detection_engine=emotion_detection_engine,
        emotional_state_manager=emotional_state_manager,
        emotional_memory=emotional_memory,
        presentation_controller=presentation_controller,
        jarvis_renderer=jarvis_renderer,
        minie_renderer=minie_renderer,
        avatar_renderer=avatar_renderer,
        gesture_engine=gesture_engine,
        transition_engine=transition_engine,
        adaptive_workspace_controller=adaptive_workspace_controller,
        companion_experience_engine=companion_experience_engine,
        voice_personality_modulator=voice_personality_modulator,
        lip_sync_driver=lip_sync_driver,
    )


def _null_level5_modules(
    config: AppConfig,
    core_manager: CoreManager,
    level2_modules: _Level2Modules,
    level3_modules: _Level3Modules,
) -> _Level5Modules:
    """Sprint 5.15, scenario (e) — the fallback main() uses only when
    _construct_level5_modules() itself raised. CommunicationPipeline and
    ui.app.run_app() both require every one of _Level5Modules' own
    fields unconditionally (Sprint 5.14 wired them in deeply) — widening
    either to tolerate None throughout would be a real redesign, not
    this sprint's own "narrow, targeted fix" mandate (Architecture
    Notes). Instead, every object here is real and constructed from
    already-validated config/already-built collaborators using ONLY
    code paths that cannot themselves plausibly fail (no I/O, no
    registry lookups) — the one call known to be able to raise,
    create_avatar_renderer(), is replaced with a NullAvatarRenderer
    (presentation/avatar_renderer_registry.py). presentation_controller
    gets an EMPTY renderers dict — the exact same "no renderer bound
    yet" state its own tests already exercised before Sprint 5.14
    existed, so mount_renderer()/refresh() both already no-op safely
    with zero new code; nothing is ever mounted, so jarvis_renderer's
    own widget (still real, still safe to construct — no I/O, see that
    class's own "widget construction is deliberately lazy" docstring)
    exists for ui/main_window.py to embed unmodified, but stays static.
    _register_level5_modules() checks the returned available=False flag
    and skips CoreManager registration entirely — "no PresentationController
    registered," this sprint's own Purpose text. (A literal "Presentation
    Layer unavailable" placeholder widget in ui/main_window.py itself is
    NOT built here — that file is not in this sprint's own Files to
    Modify list; the static, unmounted Jarvis widget above is the actual,
    disclosed degraded state a user would see.)"""
    emotion_config = config.emotion
    presentation_config = config.presentation
    memory_config = config.memory

    emotion_detection_engine = EmotionDetectionEngine(emotion_config)
    emotional_state_manager = EmotionalStateManager(emotion_config)

    event_memory = EventMemory(level3_modules.memory_store)
    emotional_memory = EmotionalMemory(level3_modules.memory_store, memory_config)

    gesture_engine = GestureEngine(presentation_config)

    jarvis_renderer = JarvisRenderer(presentation_config, core_manager)
    avatar_renderer = NullAvatarRenderer()
    minie_renderer = MinieRenderer(avatar_renderer, presentation_config, core_manager)

    presentation_controller = PresentationController(
        persona_manager=level2_modules.persona_manager,
        emotional_state_manager=emotional_state_manager,
        quiet_mode_controller=level2_modules.quiet_mode_controller,
        state_computers={},
        renderers={},
        gesture_engine=gesture_engine,
    )
    transition_engine = TransitionEngine(presentation_controller, presentation_config)

    adaptive_workspace_controller = AdaptiveWorkspaceController(presentation_config)
    companion_experience_engine = CompanionExperienceEngine(
        emotional_memory, event_memory, presentation_config
    )
    voice_personality_modulator = VoicePersonalityModulator(presentation_config)
    lip_sync_driver = LipSyncDriver(presentation_config)

    return _Level5Modules(
        emotion_detection_engine=emotion_detection_engine,
        emotional_state_manager=emotional_state_manager,
        emotional_memory=emotional_memory,
        presentation_controller=presentation_controller,
        jarvis_renderer=jarvis_renderer,
        minie_renderer=minie_renderer,
        avatar_renderer=avatar_renderer,
        gesture_engine=gesture_engine,
        transition_engine=transition_engine,
        adaptive_workspace_controller=adaptive_workspace_controller,
        companion_experience_engine=companion_experience_engine,
        voice_personality_modulator=voice_personality_modulator,
        lip_sync_driver=lip_sync_driver,
        available=False,
    )


def _construct_level5_part_b_modules(
    config: AppConfig,
    task_scheduler: TaskScheduler,
    emotional_state_manager: EmotionalStateManager | None,
    memory_store: MemoryStoreProtocol,
) -> _Level5PartBModules:
    """Construct every Level 5 Part B (Companion Intelligence) subsystem
    via DI — construction only, no CoreManager registration (see
    _register_level5_part_b_modules() below). Needs task_scheduler
    (UsageTracker/WellnessTracker both reuse it, per Sprint 4.15's own
    established TaskScheduler.add_job()/remove_job() precedent),
    emotional_state_manager (WellnessTracker's own optional stress-
    sensitivity input, Sprint 5.18) and memory_store (PreferenceLearner's
    own direct MemoryStore dependency, Sprint 5.23) already constructed.

    **A real, disclosed deviation from this sprint file's own literal
    Expected Functions signature**: the spec names a single shared
    `sqlite_client: SqliteClient` parameter, but every other _construct_
    level*_modules() function in this file (Level 3/4/4B) instead builds
    a FRESH SqliteClient(database_config.sqlite_path) per store — never
    one shared instance across multiple store classes, even when they
    point at the identical database file (see _construct_level4_modules()'s
    own audit_sqlite_client/workflow_sqlite_client for the established
    precedent). Followed that established, repeatedly-reinforced
    convention here instead — usage_store/pattern_store each get their
    own SqliteClient — rather than the sprint file's own single-parameter
    signature, which conflicts with it.

    emotional_state_manager is typed | None to match the sprint file's
    own literal Expected Functions signature, but in real operation
    (main()'s own call site) is always a real object — _null_level5_modules()
    still constructs a genuine EmotionalStateManager even on a Level 5
    Part A construction failure (see that function's own docstring), so
    WellnessTracker's own optional stress-sensitivity input is never
    actually absent in practice."""
    database_config = config.database
    analytics_config = config.analytics
    wellness_config = config.wellness
    learning_config = config.learning

    usage_sqlite_client = SqliteClient(database_config.sqlite_path)
    usage_store = UsageStore(usage_sqlite_client, analytics_config)
    usage_tracker = UsageTracker(task_scheduler, usage_store, analytics_config)

    wellness_escalation_manager = WellnessEscalationManager(wellness_config)

    pattern_sqlite_client = SqliteClient(database_config.sqlite_path)
    pattern_store = PatternStore(pattern_sqlite_client)
    adaptive_wellness_adjuster = AdaptiveWellnessAdjuster(pattern_store, wellness_config)

    wellness_tracker = WellnessTracker(
        task_scheduler, wellness_config, emotional_state_manager, wellness_escalation_manager
    )

    dashboard_service = AnalyticsDashboardService(usage_store, analytics_config)
    pattern_recognizer = PatternRecognizer(
        usage_store, dashboard_service, pattern_store, learning_config
    )
    preference_learner = PreferenceLearner(memory_store, pattern_store, learning_config)
    recommendation_engine = RecommendationEngine(pattern_store, learning_config)

    return _Level5PartBModules(
        usage_store=usage_store,
        usage_tracker=usage_tracker,
        wellness_tracker=wellness_tracker,
        wellness_escalation_manager=wellness_escalation_manager,
        adaptive_wellness_adjuster=adaptive_wellness_adjuster,
        pattern_store=pattern_store,
        pattern_recognizer=pattern_recognizer,
        dashboard_service=dashboard_service,
        preference_learner=preference_learner,
        recommendation_engine=recommendation_engine,
    )


def _null_level5_part_b_modules() -> _Level5PartBModules:
    """Sprint 5.24's own fallback, used only when
    _construct_level5_part_b_modules() itself raised — mirrors Sprint
    5.15 scenario (e)'s "a broken subsystem must not take the rest of
    startup down with it" discipline, applied here with the simpler
    all-None shape _Level5PartBModules' own docstring explains (every
    downstream caller — CommunicationPipeline's new constructor
    parameters, this same file's own _register_level5_part_b_modules()
    below — already tolerates None for each of these ten fields)."""
    return _Level5PartBModules(
        usage_store=None,
        usage_tracker=None,
        wellness_tracker=None,
        wellness_escalation_manager=None,
        adaptive_wellness_adjuster=None,
        pattern_store=None,
        pattern_recognizer=None,
        dashboard_service=None,
        preference_learner=None,
        recommendation_engine=None,
        available=False,
    )


def _construct_pipeline(
    level2_modules: _Level2Modules,
    level3_modules: _Level3Modules,
    level4_modules: _Level4Modules,
    level4b_modules: _Level4PartBModules,
    level5_modules: _Level5Modules,
    level5b_modules: _Level5PartBModules,
    scheduler_config: SchedulerConfig,
    memory_config: MemoryConfig,
    learning_config: LearningConfig,
    wellness_config: WellnessConfig,
    runtime_manager: RuntimeManager,
    resource_monitor: ResourceMonitor,
    runtime_config: RuntimeConfig,
) -> CommunicationPipeline:
    """Built last, once every level's prerequisite objects exist —
    CommunicationPipeline is the one object that needs Level 2, 3, 4, 4B,
    5, AND 5B collaborators at once. scheduler_config/memory_config/
    learning_config/wellness_config are passed separately (rather than
    threaded through a *Modules bundle) since they're plain config
    slices, not constructed objects, matching how every other *_config
    value already reaches this function's own callers directly from
    AppConfig.

    Runtime Phase 9 (Runtime Refactor Sprint): runtime_manager is the
    SAME instance core_manager.runtime_manager() already exposes (the
    identical single-shared-instance precedent Runtime Phase 5's own
    _construct_level2_modules() established for LazySpeechToText/
    LazyTextToSpeech) — CommunicationPipeline's own new housekeeping job
    must act on the exact registry CoreManager populates, not a second,
    empty RuntimeManager of its own."""
    return CommunicationPipeline(
        mic=level2_modules.mic,
        wake_word_detector=level2_modules.wake_word_detector,
        session_manager=level2_modules.session_manager,
        quiet_mode_controller=level2_modules.quiet_mode_controller,
        conversation_store=level2_modules.conversation_store,
        context_manager=level2_modules.context_manager,
        persona_manager=level2_modules.persona_manager,
        turn_complete_relay=level2_modules.turn_complete_relay,
        session_ended_relay=level2_modules.session_ended_relay,
        intent_detector=level3_modules.intent_detector,
        context_analyzer=level3_modules.context_analyzer,
        response_generator=level3_modules.response_generator,
        memory_retrieval_engine=level3_modules.memory_retrieval_engine,
        priority_queue_manager=level3_modules.priority_queue_manager,
        authority_evaluator=level3_modules.authority_evaluator,
        short_term_memory=level3_modules.short_term_memory,
        confidence_scorer=level3_modules.confidence_scorer,
        memory_lifecycle_manager=level3_modules.memory_lifecycle_manager,
        action_registry=level4_modules.action_registry,
        workflow_store=level4_modules.workflow_store,
        workflow_executor=level4_modules.workflow_executor,
        task_scheduler=level4b_modules.task_scheduler,
        calendar_store=level4b_modules.calendar_store,
        reminder_engine=level4b_modules.reminder_engine,
        research_engine=level4b_modules.research_engine,
        source_validator=level4b_modules.source_validator,
        summarizer=level4b_modules.summarizer,
        action_audit_log=level4_modules.action_audit_log,
        scheduler_config=scheduler_config,
        memory_config=memory_config,
        emotion_detection_engine=level5_modules.emotion_detection_engine,
        emotional_state_manager=level5_modules.emotional_state_manager,
        emotional_memory=level5_modules.emotional_memory,
        presentation_controller=level5_modules.presentation_controller,
        adaptive_workspace_controller=level5_modules.adaptive_workspace_controller,
        gesture_engine=level5_modules.gesture_engine,
        voice_personality_modulator=level5_modules.voice_personality_modulator,
        lip_sync_driver=level5_modules.lip_sync_driver,
        companion_experience_engine=level5_modules.companion_experience_engine,
        jarvis_renderer=level5_modules.jarvis_renderer,
        avatar_renderer=level5_modules.avatar_renderer,
        wellness_tracker=level5b_modules.wellness_tracker,
        wellness_escalation_manager=level5b_modules.wellness_escalation_manager,
        adaptive_wellness_adjuster=level5b_modules.adaptive_wellness_adjuster,
        dashboard_service=level5b_modules.dashboard_service,
        usage_tracker=level5b_modules.usage_tracker,
        pattern_recognizer=level5b_modules.pattern_recognizer,
        recommendation_engine=level5b_modules.recommendation_engine,
        learning_config=learning_config,
        wellness_config=wellness_config,
        runtime_manager=runtime_manager,
        resource_monitor=resource_monitor,
        runtime_config=runtime_config,
    )


def _register_level4_part_b_early(
    core_manager: CoreManager, level4b_modules: _Level4PartBModules
) -> None:
    """Registers task_scheduler and calendar_store BEFORE every other
    module in the entire graph, including Level 2 — the one deliberate
    exception to this file's own "Level 3/4 register after
    communication_pipeline" ordering discipline (see
    _register_level3_modules()'s own docstring for that discipline's
    original reasoning).

    Why: CommunicationPipeline.start() (Sprint 4.18) calls
    task_scheduler.add_job() directly, for the proactive-reminder-
    announcement job and the three periodic maintenance passes —
    add_job() raises RuntimeError unless TaskScheduler.start() has
    already run (scheduler/task_scheduler.py's own _require_scheduler()
    guard). CoreManager.startup() calls every registered module's
    start() in registration order, so task_scheduler must be registered
    (and therefore started) before communication_pipeline is, or this
    would fail on every real application startup. calendar_store has no
    such ordering requirement of its own (nothing calls it from within
    another module's start()) but is grouped here for one clear "Part B
    storage/scheduling infrastructure, started first" registration
    step rather than splitting Part B's two ManagedModules across two
    separate registration calls for no real benefit.

    reminder_engine/research_engine/source_validator/summarizer are not
    registered here (or anywhere) — none are ManagedModules, per
    _Level4PartBModules' own docstring; reminder_engine.register()/
    .unregister() are called directly by CommunicationPipeline.start()/
    stop() instead (see voice/pipeline.py's own docstring)."""
    core_manager.register_module("task_scheduler", level4b_modules.task_scheduler)
    core_manager.register_module("calendar_store", level4b_modules.calendar_store)


def _register_level2_modules(
    core_manager: CoreManager, level2_modules: _Level2Modules, pipeline: CommunicationPipeline
) -> None:
    """Register every Level 2 ManagedModule plus the pipeline itself, in
    an order that satisfies CoreManager's own start()-in-registration-
    order contract (mic must be registered, and therefore started,
    before wake_word_detector — the only real start()-time ordering
    constraint across all of Level 2; see
    docs/sprint_book/sprint_2_12.md's Sprint Completion Report for why
    the rest of the graph has none).

    Runtime Phase 5 (Runtime Refactor Sprint): speech_to_text/
    text_to_speech register tier=ServiceTier.WARM, lazy=True — the real
    WhisperSpeechToText/CoquiTextToSpeech instances no longer load their
    model synchronously here; RuntimeManager decides when (background
    warm-up per Runtime Phase 4, or the first real transcribe()/speak()
    call via voice/speech_to_text.py's LazySpeechToText/voice/
    text_to_speech.py's LazyTextToSpeech, whichever comes first).

    Runtime Phase 9: both also register idle_timeout_seconds=core_manager.
    config().runtime.default_idle_timeout_seconds — reading it back off
    core_manager rather than threading a new `config` parameter through
    this function, the same "CoreManager already holds it, ask CoreManager"
    precedent config()/ui_config() already established for every other
    caller that needs a config slice post-construction."""
    core_manager.register_module("microphone", level2_modules.mic)
    default_idle_timeout = core_manager.config().runtime.default_idle_timeout_seconds
    core_manager.register_module(
        "speech_to_text",
        level2_modules.stt,
        tier=ServiceTier.WARM,
        lazy=True,
        idle_timeout_seconds=default_idle_timeout,
    )
    core_manager.register_module(
        "text_to_speech",
        level2_modules.tts,
        tier=ServiceTier.WARM,
        lazy=True,
        idle_timeout_seconds=default_idle_timeout,
    )
    core_manager.register_module("conversation_store", level2_modules.conversation_store)
    core_manager.register_module("persona_manager", level2_modules.persona_manager)
    core_manager.register_module("voice_session_manager", level2_modules.session_manager)
    core_manager.register_module("quiet_mode_controller", level2_modules.quiet_mode_controller)
    core_manager.register_module("wake_word_detector", level2_modules.wake_word_detector)
    core_manager.register_module("communication_pipeline", pipeline)


def _register_level3_modules(core_manager: CoreManager, level3_modules: _Level3Modules) -> None:
    """Register Level 3's ManagedModules with core_manager — called
    AFTER _register_level2_modules() (see main()), a deliberate ordering
    fix: registering Level 3 before Level 2's wake_word_detector/
    communication_pipeline pair (as an earlier version of this file did)
    widens the real gap between wake_word_detector.start() (which begins
    actively processing audio and can fire immediately) and
    communication_pipeline.start() (which wires the relays
    on_turn_complete/on_session_ended point through) by however long
    memory_store.start() takes to load Chroma's embedding model — long
    enough, concretely observed in tests/system's own short-timeout
    harness, for a session to time out and its on_session_ended callback
    to fire through a relay that isn't wired yet, silently dropping it
    (logged as "CallbackRelay invoked before wiring was established").
    Registering every Level 3 module after communication_pipeline instead
    keeps that Level 2 gap exactly as tight as it was before Level 3
    existed; only six of the constructed objects are ManagedModules and
    need registering at all — PersonaScopedMemory, EventMemory,
    ShortTermMemory, ConfidenceScorer, MemoryRetrievalEngine, and
    OllamaClient are all plain classes with no lifecycle of their own
    (each one's own sprint documented this explicitly), so they are
    never registered.

    Registration order among the six: memory_store must start before
    memory_lifecycle_manager, since its start() now queries memory_store
    directly (Sprint 3.12's startup-time cleanup/review invocation — see
    memory/lifecycle_manager.py's own docstring for why start() itself,
    not some other file, is where that one-time call lives). No other
    Level 3 module has a real start()-order dependency on another.

    Runtime Phase 6 (Runtime Refactor Sprint): memory_store/
    memory_lifecycle_manager now register tier=ServiceTier.WARM — moved
    off the synchronous startup path entirely, onto ui/app.py's own
    background warm-up thread (Runtime Phase 4). This docstring's own
    opening paragraph's original worry (memory_store.start() widening the
    wake_word_detector-to-communication_pipeline gap) is now structurally
    resolved rather than merely mitigated by registration order: Tier A
    (which includes wake_word_detector and communication_pipeline, both
    still untagged/ALWAYS_LOADED) finishes completely, synchronously,
    before the background thread even starts Tier B — the two can no
    longer race at all. memory_store additionally registers lazy=True
    (real_memory_store, not the LazyMemoryStore proxy threaded through
    every other Level 3/5/5B consumer — see that class's own docstring in
    memory/memory_store.py); memory_lifecycle_manager stays a plain
    ManagedModule, relying on same-tier same-relative-order sequencing
    (still preserved below) to guarantee real_memory_store.start() has
    already run by the time its own start() calls into it.

    Runtime Phase 9: also registers idle_timeout_seconds=core_manager.
    config().runtime.default_idle_timeout_seconds — the same "ask
    CoreManager for its own config" precedent _register_level2_modules()
    established for speech_to_text/text_to_speech."""
    core_manager.register_module(
        "memory_store",
        level3_modules.real_memory_store,
        tier=ServiceTier.WARM,
        lazy=True,
        idle_timeout_seconds=core_manager.config().runtime.default_idle_timeout_seconds,
    )
    core_manager.register_module(
        "memory_lifecycle_manager",
        level3_modules.memory_lifecycle_manager,
        tier=ServiceTier.WARM,
    )
    # Runtime Phase 7 (Runtime Refactor Sprint): intent_detector/
    # context_analyzer register tier=ServiceTier.WARM — their start()
    # (decision/intent_detector.py:63-79, decision/context_analyzer.py's
    # own mirror) only runs a bounded ~5s Ollama reachability probe purely
    # for health_check() reporting; detect()/analyze() never check that
    # flag before calling generate() themselves, already degrading
    # gracefully on any LlmError independent of whether start() ever
    # succeeded. No lazy=True and no code change to either file: moving
    # the probe onto the background warm-up thread (Runtime Phase 4) is
    # the whole win — there is no expensive "load" to gate behind
    # ensure_started(), unlike Whisper/Coqui/MemoryStore.
    core_manager.register_module(
        "intent_detector", level3_modules.intent_detector, tier=ServiceTier.WARM
    )
    core_manager.register_module(
        "context_analyzer", level3_modules.context_analyzer, tier=ServiceTier.WARM
    )
    core_manager.register_module(
        "priority_queue_manager", level3_modules.priority_queue_manager
    )
    core_manager.register_module("authority_evaluator", level3_modules.authority_evaluator)


def _register_level4_modules(core_manager: CoreManager, level4_modules: _Level4Modules) -> None:
    """Registered after every Level 2/3 module (see main()'s own
    ordering comment) to keep the wake_word_detector-to-
    communication_pipeline relay-wiring gap as tight as Level 3's own
    registration already keeps it — neither ActionAuditLog's nor
    WorkflowStore's own start() does anything as slow as Level 3's
    Chroma embedding-model load, but matching the established ordering
    exactly is the safer, most consistent choice.

    Only ActionAuditLog and WorkflowStore are real ManagedModules among
    everything Level 4 Part A constructs — ActionRegistry/PermissionGate/
    PermissionPolicyEngine/ConfirmationService/ActionResourceGate/
    ActionRecoveryManager and all four executors are plain, lifecycle-
    free classes (each one's own sprint documented this explicitly), so
    they are never registered, the same "only register what has a real
    lifecycle" discipline _register_level3_modules() already
    established."""
    # Runtime Phase 8 (Runtime Refactor Sprint): both register
    # tier=ServiceTier.WARM — each one's own start() is just a cheap
    # SQLite connect+CREATE TABLE (see workflow/workflow_store.py's and
    # device_control/action_log.py's own start()), the identical "no
    # expensive load to gate behind lazy=True" reasoning Runtime Phase 7
    # already established for usage_store/pattern_store. Moving both off
    # the synchronous Tier A path onto the background warm-up thread
    # (Runtime Phase 4) is the whole win; no code change to either file
    # itself.
    core_manager.register_module(
        "action_audit_log", level4_modules.action_audit_log, tier=ServiceTier.WARM
    )
    core_manager.register_module(
        "workflow_store", level4_modules.workflow_store, tier=ServiceTier.WARM
    )


def _register_level5_modules(core_manager: CoreManager, level5_modules: _Level5Modules) -> None:
    """Registered after every Level 2/3/4 module (see main()'s own
    ordering comment) — same "keep the wake_word_detector-to-
    communication_pipeline relay-wiring gap tight" discipline
    _register_level3_modules()/_register_level4_modules() already
    established. presentation_controller is registered last of the
    three: its own start() calls persona_manager.active_persona(),
    which requires persona_manager (Level 2, already started by this
    point in registration order) to already be running.

    Runtime Phase 8 (Runtime Refactor Sprint): all three register
    tier=ServiceTier.WARM — each one's own start() is a cheap in-memory
    flag flip or a single mount_renderer() call (see emotion/
    detection_engine.py's, emotion/state_manager.py's, and presentation/
    presentation_controller.py's own start()), no expensive load to gate
    behind lazy=True, the same reasoning Runtime Phase 7 already
    established. The persona_manager-must-already-be-running ordering
    requirement above still holds unconditionally under this tier move:
    persona_manager is Tier A (ALWAYS_LOADED), which always finishes
    starting synchronously before window.show() — and therefore before
    the background thread that starts any Tier B module even begins
    (Runtime Phase 4) — regardless of where presentation_controller
    itself falls within Tier B's own stable registration-order
    partition.

    Only PresentationController/EmotionDetectionEngine/EmotionalStateManager
    are real ManagedModules among everything Level 5 Part A constructs —
    every other object (EmotionalMemory, JarvisRenderer, MinieRenderer,
    avatar_renderer, GestureEngine, TransitionEngine,
    AdaptiveWorkspaceController, CompanionExperienceEngine,
    VoicePersonalityModulator, LipSyncDriver) is plain and lifecycle-free
    (each one's own originating sprint documented this explicitly), so
    they are never registered — the identical "only register what has a
    real lifecycle" discipline every prior level's own registration
    function already established. avatar_renderer's own mount()/unmount()
    (a Renderer-shaped lifecycle, not a ManagedModule one) happens
    indirectly, through MinieRenderer.mount()/unmount(), themselves
    called by PresentationController.mount_renderer() — never registered
    with CoreManager directly.

    Sprint 5.15, scenario (e): if level5_modules.available is False (the
    main()-level construction fallback fired), none of the three are
    registered at all — "no PresentationController registered" is this
    sprint's own literal Purpose text; CoreManager simply never learns
    these objects exist, matching every other un-registered plain object
    already listed above."""
    if not level5_modules.available:
        logger.info(
            "Level 5 Part A construction fallback is active; skipping CoreManager "
            "registration for emotion_detection_engine/emotional_state_manager/"
            "presentation_controller."
        )
        return
    core_manager.register_module(
        "emotion_detection_engine",
        level5_modules.emotion_detection_engine,
        tier=ServiceTier.WARM,
    )
    core_manager.register_module(
        "emotional_state_manager",
        level5_modules.emotional_state_manager,
        tier=ServiceTier.WARM,
    )
    core_manager.register_module(
        "presentation_controller", level5_modules.presentation_controller, tier=ServiceTier.WARM
    )


def _register_level5_part_b_modules(
    core_manager: CoreManager, level5b_modules: _Level5PartBModules
) -> None:
    """Registered after every Level 2/3/4/5 module (see main()'s own
    ordering comment) — same "keep the wake_word_detector-to-
    communication_pipeline relay-wiring gap tight" discipline every
    prior level's own registration function already established. Nothing
    here has any real start()-order dependency on the other four, so
    registration order among them just follows natural dependency
    locality (analytics foundation, then the learning layer built on top
    of it, then wellness last).

    Only usage_store/usage_tracker/pattern_store/pattern_recognizer/
    wellness_tracker are real ManagedModules among everything Level 5
    Part B constructs — wellness_escalation_manager/adaptive_wellness_
    adjuster/dashboard_service/preference_learner/recommendation_engine
    are all plain, lifecycle-free collaborators (each one's own
    originating sprint documented this explicitly), so they are never
    registered — the identical "only register what has a real lifecycle"
    discipline every prior level's own registration function already
    established.

    Sprint 5.24's own fallback: if level5b_modules.available is False
    (the main()-level construction fallback fired), none of the five are
    registered at all — CoreManager simply never learns these objects
    exist, matching every prior level's own scenario-(e)-style fallback."""
    if not level5b_modules.available:
        logger.info(
            "Level 5 Part B construction fallback is active; skipping CoreManager "
            "registration for usage_store/usage_tracker/pattern_store/pattern_recognizer/"
            "wellness_tracker."
        )
        return
    # available=True is only ever set by _construct_level5_part_b_modules()'s
    # own real return, which never leaves a field None — asserted here
    # purely to narrow the type checker's view of _Level5PartBModules'
    # own Type | None fields, not because this is a runtime possibility.
    assert level5b_modules.usage_store is not None
    assert level5b_modules.usage_tracker is not None
    assert level5b_modules.pattern_store is not None
    assert level5b_modules.pattern_recognizer is not None
    assert level5b_modules.wellness_tracker is not None
    # Runtime Phase 7 (Runtime Refactor Sprint): all five register
    # tier=ServiceTier.WARM — each one's own start() is either a cheap
    # SQLite connect+CREATE TABLE (usage_store, pattern_store) or just a
    # TaskScheduler.add_job() registration (usage_tracker, pattern_
    # recognizer, wellness_tracker; see each file's own start()) — no
    # expensive load to gate behind lazy=True/ensure_started(), and (per
    # this function's own docstring above) no real start()-order
    # dependency among them to protect either way. Moving all five off
    # the synchronous Tier A path onto the background warm-up thread
    # (Runtime Phase 4) is the whole win; no code change to any of the
    # five files themselves.
    core_manager.register_module(
        "usage_store", level5b_modules.usage_store, tier=ServiceTier.WARM
    )
    core_manager.register_module(
        "usage_tracker", level5b_modules.usage_tracker, tier=ServiceTier.WARM
    )
    core_manager.register_module(
        "pattern_store", level5b_modules.pattern_store, tier=ServiceTier.WARM
    )
    core_manager.register_module(
        "pattern_recognizer", level5b_modules.pattern_recognizer, tier=ServiceTier.WARM
    )
    core_manager.register_module(
        "wellness_tracker", level5b_modules.wellness_tracker, tier=ServiceTier.WARM
    )


if __name__ == "__main__":
    sys.exit(main())
