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
"""

import sys
from dataclasses import dataclass, replace

from config import ConfigLoader
from config.schema import AppConfig, SchedulerConfig
from core import configure_logging
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
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
from internet.research_engine import ResearchEngine
from internet.search_provider_registry import create_search_provider_with_fallback
from internet.source_validator import SourceValidator
from internet.summarizer import Summarizer
from memory.chroma_client import ChromaMemoryClient
from memory.confidence_scorer import ConfidenceScorer
from memory.event_memory import EventMemory
from memory.lifecycle_manager import MemoryLifecycleManager
from memory.memory_store import MemoryStore
from memory.persona_scoped_memory import PersonaScopedMemory
from memory.retrieval_engine import MemoryRetrievalEngine
from memory.short_term_memory import ShortTermMemory
from personas.jarvis import JarvisPersona
from personas.minie import MiniePersona
from personas.persona_manager import PersonaManager
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
from voice.speech_to_text import WhisperSpeechToText
from voice.text_to_speech import CoquiTextToSpeech, SoundDeviceAudioOutput
from voice.wake_word import OpenWakeWordEngine, WakeWordDetector
from workflow.workflow_executor import WorkflowExecutor
from workflow.workflow_store import WorkflowStore


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
    memory_store: MemoryStore


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
    config_loader = ConfigLoader()
    config = config_loader.load()
    configure_logging(config.logging)

    resource_monitor = ResourceMonitor(config.resources)
    core_manager = CoreManager(config, resource_monitor, config_loader)

    # Construction order: Level 3 first (no dependency on Level 2/4),
    # then Level 2 (VoiceConfirmationService, built inside Level 4,
    # needs its session_manager/persona_manager), then Level 4 Part A
    # (needs both Level 2 and Level 3 objects), then Level 4 Part B
    # (needs Level 3's priority_queue_manager), then the pipeline itself
    # (needs all four). Registration order is intentionally different —
    # see _register_level4_part_b_early()'s, _register_level3_modules()'s,
    # and _register_level4_modules()'s own docstrings for the two
    # distinct ordering constraints this project now balances: Level 3/4
    # Part A/4B's remaining registrations all happen AFTER
    # communication_pipeline (keeping the wake_word_detector-to-pipeline
    # relay-wiring gap tight), while task_scheduler/calendar_store are
    # the one deliberate exception, registered FIRST, before even Level
    # 2 — CommunicationPipeline.start() (Sprint 4.18) calls
    # task_scheduler.add_job() directly, which requires task_scheduler
    # to already be started.
    level3_modules = _construct_level3_modules(config, resource_monitor)
    level2_modules = _construct_level2_modules(config)
    level4_modules = _construct_level4_modules(
        config, resource_monitor, level3_modules, level2_modules
    )
    level4b_modules = _construct_level4_part_b_modules(config, level3_modules)
    pipeline = _construct_pipeline(
        level2_modules, level3_modules, level4_modules, level4b_modules, config.scheduler
    )

    _register_level4_part_b_early(core_manager, level4b_modules)
    _register_level2_modules(core_manager, level2_modules, pipeline)
    _register_level3_modules(core_manager, level3_modules)
    _register_level4_modules(core_manager, level4_modules)

    # _prewarm_tts_before_pyside6() must run before this import — see its
    # own docstring. ui.app is deliberately imported here, locally,
    # rather than at this module's own top level, precisely so this
    # ordering is achievable — a module-level import here would already
    # be too late relative to everything else this file also imports at
    # module level.
    _prewarm_tts_before_pyside6()
    from ui.app import run_app

    return run_app(core_manager)


def _construct_level2_modules(config: AppConfig) -> _Level2Modules:
    """Construct every Level 2 (Communication) subsystem via DI except
    CommunicationPipeline itself — see _Level2Modules' own docstring for
    why. VoiceSessionManager.on_turn_complete/on_session_ended cannot yet
    point at their real targets when VoiceSessionManager itself is
    constructed (QuietModeController and CommunicationPipeline, which own
    those targets, are built later) — CallbackRelay (voice/pipeline.py)
    stands in for both until CommunicationPipeline's own start() aims
    them at the real methods.
    """
    voice_config = config.voice
    model_config = config.models
    database_config = config.database

    mic = MicrophoneManager(voice_config, SoundDeviceAudioBackend())
    stt = WhisperSpeechToText(model_config)
    tts = CoquiTextToSpeech(model_config, SoundDeviceAudioOutput())

    sqlite_client = SqliteClient(database_config.sqlite_path)
    conversation_store = ConversationSessionStore(sqlite_client, database_config)
    context_manager = ContextManager(conversation_store)

    jarvis = JarvisPersona(voice_config)
    minie = MiniePersona(voice_config)
    persona_manager = PersonaManager(jarvis, minie, voice_config)

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
        stt=stt,
        tts=tts,
        conversation_store=conversation_store,
        context_manager=context_manager,
        persona_manager=persona_manager,
        session_manager=session_manager,
        quiet_mode_controller=quiet_mode_controller,
        wake_word_detector=wake_word_detector,
        turn_complete_relay=turn_complete_relay,
        session_ended_relay=session_ended_relay,
    )


def _construct_level3_modules(
    config: AppConfig, resource_monitor: ResourceMonitor
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
    """
    database_config = config.database
    memory_config = config.memory
    model_config = config.models

    sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)
    memory_store = MemoryStore(sqlite_client, chroma_client)

    persona_scoped_memory = PersonaScopedMemory(memory_store)
    event_memory = EventMemory(memory_store)
    short_term_memory = ShortTermMemory(memory_store, memory_config)
    confidence_scorer = ConfidenceScorer(memory_config)
    memory_lifecycle_manager = MemoryLifecycleManager(
        memory_store, confidence_scorer, memory_config
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


def _construct_pipeline(
    level2_modules: _Level2Modules,
    level3_modules: _Level3Modules,
    level4_modules: _Level4Modules,
    level4b_modules: _Level4PartBModules,
    scheduler_config: SchedulerConfig,
) -> CommunicationPipeline:
    """Built last, once every level's prerequisite objects exist —
    CommunicationPipeline is the one object that needs Level 2, 3, 4,
    AND 4B collaborators at once. scheduler_config is passed separately
    (rather than threaded through _Level4PartBModules) since it's a
    plain config slice, not a constructed object, matching how every
    other *_config value already reaches this function's own callers
    directly from AppConfig."""
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
    the rest of the graph has none)."""
    core_manager.register_module("microphone", level2_modules.mic)
    core_manager.register_module("speech_to_text", level2_modules.stt)
    core_manager.register_module("text_to_speech", level2_modules.tts)
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
    """
    core_manager.register_module("memory_store", level3_modules.memory_store)
    core_manager.register_module(
        "memory_lifecycle_manager", level3_modules.memory_lifecycle_manager
    )
    core_manager.register_module("intent_detector", level3_modules.intent_detector)
    core_manager.register_module("context_analyzer", level3_modules.context_analyzer)
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
    core_manager.register_module("action_audit_log", level4_modules.action_audit_log)
    core_manager.register_module("workflow_store", level4_modules.workflow_store)


if __name__ == "__main__":
    sys.exit(main())
