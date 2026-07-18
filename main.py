"""JARMINEI application entrypoint — the sole composition root.

Constructs concrete subsystem instances and wires them together via
dependency injection; no other file in the codebase should construct
these directly. See docs/sprint_book/sprint_1_5.md, sprint_1_6.md,
sprint_2_12.md (Level 2's Communication Pipeline Integration), and
sprint_3_12.md (Level 3's Decision Engine Integration).

Startup happens inside ui.app.run_app(); shutdown happens inside
MainWindow.closeEvent() when the user closes the window — the Qt event
loop (app.exec()) is what keeps the process alive between the two.
"""

import sys
from dataclasses import dataclass

from config import ConfigLoader
from config.schema import AppConfig
from core import configure_logging
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
from database.sqlite_client import SqliteClient
from decision.authority import AuthorityEvaluator
from decision.context_analyzer import ContextAnalyzer
from decision.intent_detector import IntentDetector
from decision.llm_client import OllamaClient
from decision.priority_queue import PriorityQueueManager
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
from ui.app import run_app
from voice.context_manager import ContextManager
from voice.conversation_store import ConversationSessionStore
from voice.microphone import MicrophoneManager, SoundDeviceAudioBackend
from voice.pipeline import CallbackRelay, CommunicationPipeline
from voice.quiet_mode import QuietModeController
from voice.session_manager import VoiceSessionManager
from voice.speech_to_text import WhisperSpeechToText
from voice.text_to_speech import CoquiTextToSpeech, SoundDeviceAudioOutput
from voice.wake_word import OpenWakeWordEngine, WakeWordDetector


@dataclass
class _Level3Modules:
    """Bundles every Level 3 object _register_level2_modules() (to build
    CommunicationPipeline) and _register_level3_modules() (to register
    the ManagedModules among them) need — private to this file, matching
    the composition-root's own "only this file constructs concrete
    subsystem instances" rule (Sprint 1.5)."""

    intent_detector: IntentDetector
    context_analyzer: ContextAnalyzer
    memory_retrieval_engine: MemoryRetrievalEngine
    priority_queue_manager: PriorityQueueManager
    authority_evaluator: AuthorityEvaluator
    short_term_memory: ShortTermMemory
    confidence_scorer: ConfidenceScorer
    memory_lifecycle_manager: MemoryLifecycleManager
    memory_store: MemoryStore


def main() -> int:
    config_loader = ConfigLoader()
    config = config_loader.load()
    configure_logging(config.logging)

    resource_monitor = ResourceMonitor(config.resources)
    core_manager = CoreManager(config, resource_monitor, config_loader)

    # Level 3 objects are CONSTRUCTED before Level 2's registration (so
    # CommunicationPipeline's constructor can receive them), but Level 3's
    # own ManagedModules are not REGISTERED (and therefore not started)
    # until after every Level 2 module is registered — see
    # _register_level3_modules()'s own docstring for why this ordering,
    # not just construction order, matters.
    level3_modules = _construct_level3_modules(config, resource_monitor)
    _register_level2_modules(core_manager, config, level3_modules)
    _register_level3_modules(core_manager, level3_modules)

    return run_app(core_manager)


def _register_level2_modules(
    core_manager: CoreManager, config: AppConfig, level3_modules: _Level3Modules
) -> None:
    """Construct every Level 2 (Communication) subsystem via DI and
    register each ManagedModule with core_manager, in an order that
    satisfies two kinds of dependency: real object-graph construction
    order (a class needs its dependencies to already exist), and
    CoreManager's own start()-in-registration-order contract (mic must be
    registered, and therefore started, before wake_word_detector — the
    only real start()-time ordering constraint across all of Level 2; see
    docs/sprint_book/sprint_2_12.md's Sprint Completion Report for why the
    rest of the graph has none).

    VoiceSessionManager.on_turn_complete/on_session_ended cannot yet point
    at their real targets when VoiceSessionManager itself is constructed
    (QuietModeController and CommunicationPipeline, which own those
    targets, are built later in this same function) — CallbackRelay
    (voice/pipeline.py) stands in for both until CommunicationPipeline's
    own start() aims them at the real methods.

    level3_modules (Sprint 3.12) is built by _register_level3_modules()
    first (see main()) and threaded through here purely because
    CommunicationPipeline — constructed in this function — is the one
    object that needs both Level 2 and Level 3 collaborators at once.
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

    pipeline = CommunicationPipeline(
        mic=mic,
        wake_word_detector=wake_word_detector,
        session_manager=session_manager,
        quiet_mode_controller=quiet_mode_controller,
        conversation_store=conversation_store,
        context_manager=context_manager,
        persona_manager=persona_manager,
        turn_complete_relay=turn_complete_relay,
        session_ended_relay=session_ended_relay,
        intent_detector=level3_modules.intent_detector,
        context_analyzer=level3_modules.context_analyzer,
        memory_retrieval_engine=level3_modules.memory_retrieval_engine,
        priority_queue_manager=level3_modules.priority_queue_manager,
        authority_evaluator=level3_modules.authority_evaluator,
        short_term_memory=level3_modules.short_term_memory,
        confidence_scorer=level3_modules.confidence_scorer,
        memory_lifecycle_manager=level3_modules.memory_lifecycle_manager,
    )

    core_manager.register_module("microphone", mic)
    core_manager.register_module("speech_to_text", stt)
    core_manager.register_module("text_to_speech", tts)
    core_manager.register_module("conversation_store", conversation_store)
    core_manager.register_module("persona_manager", persona_manager)
    core_manager.register_module("voice_session_manager", session_manager)
    core_manager.register_module("quiet_mode_controller", quiet_mode_controller)
    core_manager.register_module("wake_word_detector", wake_word_detector)
    core_manager.register_module("communication_pipeline", pipeline)


def _construct_level3_modules(
    config: AppConfig, resource_monitor: ResourceMonitor
) -> _Level3Modules:
    """Construct every Level 3 (Memory Engine, Dynamic Memory, Decision
    Engine) subsystem via DI — construction only, no CoreManager
    registration (see _register_level3_modules() below for why the two
    are deliberately separate calls, made at different points in
    main()). Called before _register_level2_modules() so
    CommunicationPipeline — built inside that function — can receive the
    Level 3 objects it needs to hold a reference to.
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

    priority_queue_manager = PriorityQueueManager(resource_monitor)
    authority_evaluator = AuthorityEvaluator()

    return _Level3Modules(
        intent_detector=intent_detector,
        context_analyzer=context_analyzer,
        memory_retrieval_engine=memory_retrieval_engine,
        priority_queue_manager=priority_queue_manager,
        authority_evaluator=authority_evaluator,
        short_term_memory=short_term_memory,
        confidence_scorer=confidence_scorer,
        memory_lifecycle_manager=memory_lifecycle_manager,
        memory_store=memory_store,
    )


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


if __name__ == "__main__":
    sys.exit(main())
