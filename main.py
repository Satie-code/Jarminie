"""JARMINEI application entrypoint — the sole composition root.

Constructs concrete subsystem instances and wires them together via
dependency injection; no other file in the codebase should construct
these directly. See docs/sprint_book/sprint_1_5.md, sprint_1_6.md, and
sprint_2_12.md (Level 2's Communication Pipeline Integration).

Startup happens inside ui.app.run_app(); shutdown happens inside
MainWindow.closeEvent() when the user closes the window — the Qt event
loop (app.exec()) is what keeps the process alive between the two.
"""

import sys

from config import ConfigLoader
from config.schema import AppConfig
from core import configure_logging
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
from database.sqlite_client import SqliteClient
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


def main() -> int:
    config_loader = ConfigLoader()
    config = config_loader.load()
    configure_logging(config.logging)

    resource_monitor = ResourceMonitor(config.resources)
    core_manager = CoreManager(config, resource_monitor, config_loader)
    _register_level2_modules(core_manager, config)

    return run_app(core_manager)


def _register_level2_modules(core_manager: CoreManager, config: AppConfig) -> None:
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


if __name__ == "__main__":
    sys.exit(main())
