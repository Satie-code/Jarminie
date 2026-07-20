"""Shared fixtures for tests/system/ — full-application system tests that
go through a real CoreManager.startup()/shutdown() with the entire Level
2 AND Level 3 module graph registered, the same way main.py's own
_register_level2_modules()/_register_level3_modules() (Sprint 3.12) do.
This is what distinguishes this tier from tests/integration/: those
tests start each module individually in a hand-picked order via the
pipeline_harness fixture; this tier instead proves CoreManager's
registration/startup/shutdown-order guarantees themselves hold for the
real, full graph.

Fakes stand in only at the audio-hardware/ML boundary (mic, wake engine,
STT, TTS, and now the Ollama-backed LanguageModelClient), same as
tests/integration/conftest.py — kept self-contained rather than shared
across test tiers, matching this project's existing per-directory
conftest convention (tests/unit/voice/conftest.py and
tests/unit/personas/conftest.py are likewise independent of each other).
Chroma/SQLite are real, matching every Level 3 unit test's own
established convention.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config.schema import AppConfig, DatabaseConfig, MemoryConfig, VoiceConfig
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
from database.sqlite_client import SqliteClient
from decision.authority import AuthorityEvaluator
from decision.context_analyzer import ContextAnalyzer
from decision.intent_detector import IntentDetector
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
from voice.context_manager import ContextManager
from voice.conversation_store import ConversationSessionStore
from voice.microphone import MicrophoneManager, MicrophoneMode
from voice.pipeline import CallbackRelay, CommunicationPipeline
from voice.quiet_mode import OperatingMode, QuietModeController
from voice.session_manager import VoiceSessionManager
from voice.speech_to_text import TranscriptionResult
from voice.wake_word import WakeWordDetector

WAIT_TIMEOUT = 5.0

LOUD_FRAME = b"\xff\x7f" * 480
QUIET_FRAME = b"\x00\x00" * 480


class FakeAudioBackend:
    def __init__(self) -> None:
        self.is_open = False
        self.frame_queue: list[bytes] = []

    def open(self, device_index: int | None, sample_rate_hz: int) -> None:
        self.is_open = True

    def read(self, num_frames: int) -> bytes:
        if self.frame_queue:
            return self.frame_queue.pop(0)
        return b"\x00\x00" * num_frames

    def flush(self) -> None:
        """VoiceSessionManager.begin_session() calls this immediately
        after switching to ACTIVE_CAPTURE (post-release fix) — safe to
        genuinely clear frame_queue here since this test only calls
        push_utterance() after the session has already begun."""
        self.frame_queue.clear()

    def close(self) -> None:
        self.is_open = False


class FakeWakeWordEngine:
    def __init__(self, match_on_call: int, match_phrase: str = "hey_jarvis") -> None:
        self.calls = 0
        self.match_on_call = match_on_call
        self.match_phrase = match_phrase

    def process(self, frame: bytes) -> str | None:
        call_index = self.calls
        self.calls += 1
        if call_index == self.match_on_call:
            return self.match_phrase
        return None


class FakeSpeechToText:
    def __init__(self) -> None:
        self.pending_transcripts: list[str] = []

    def transcribe(self, audio: bytes) -> TranscriptionResult:
        text = self.pending_transcripts.pop(0) if self.pending_transcripts else ""
        return TranscriptionResult(text=text, average_confidence=0.9, duration_ms=1)


class FakeTextToSpeech:
    def __init__(self) -> None:
        self.speak_calls: list[tuple[str, str]] = []
        self.spoken_event = threading.Event()

    def speak(self, text: str, voice_id: str) -> None:
        self.speak_calls.append((text, voice_id))
        self.spoken_event.set()


class FakeLanguageModelClient:
    """Fakes only the Ollama boundary IntentDetector/ContextAnalyzer
    depend on — see this module's own docstring. Dispatches on prompt
    content: IntentDetector's own prompt always instructs a "CATEGORY:"
    line; ContextAnalyzer's never does.

    should_raise (Sprint 3.14, re-confirming Sprint 3.13's scenario (a)
    at the system level) simulates Ollama being entirely unreachable —
    same convention as tests/integration/conftest.py's own fake."""

    def __init__(self) -> None:
        self.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
        self.context_response = (
            "TOPIC: general\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
            "PERSONA: NONE\nSENTIMENT: NEUTRAL"
        )
        self.should_raise = False

    def generate(self, prompt: str, timeout_seconds: float) -> str:
        if self.should_raise:
            from decision.llm_client import LlmError

            raise LlmError("simulated Ollama connection failure")
        if "CATEGORY:" in prompt:
            return self.intent_response
        return self.context_response


class _StartStopWrapper:
    """FakeSpeechToText/FakeTextToSpeech need no real load/release step,
    unlike the real WhisperSpeechToText/CoquiTextToSpeech they stand in
    for — this thin ManagedModule adapter is what main.py's real
    _register_level2_modules() doesn't need (the real classes already
    implement start()/stop()/health_check() themselves) but this fake-
    based harness does, purely so CoreManager.startup()/shutdown() has
    something to call."""

    def __init__(self, fake) -> None:
        self._fake = fake
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def health_check(self) -> bool:
        return self._started

    def __getattr__(self, name):
        return getattr(self._fake, name)


@pytest.fixture
def voice_config() -> VoiceConfig:
    """session_timeout_seconds=3.0 (was 0.8 before Sprint 3.12): this
    tier drives startup through a real CoreManager.startup(), which
    starts every registered module in registration order — including,
    now, Level 3's memory/decision modules — before returning control to
    the test. With FakeWakeWordEngine(match_on_call=2) configured to
    match almost immediately once frames start flowing, a too-short
    session_timeout_seconds risks the entire wake -> active -> timeout
    -> passive cycle completing during fixture setup itself, before the
    test's own wait_for_active_capture() polling loop ever starts —
    concretely reproduced (mic observed already back in
    PASSIVE_LISTENING for the whole 5s poll window) once Level 3's added
    startup latency (~1-1.5s for MemoryStore's Chroma embedding-model
    load) was introduced. 3.0s leaves comfortable margin against that
    startup cost while still safely fitting within wait_for_dormant()'s
    own 5.0s poll window at the end of the test. tests/integration/
    conftest.py's pipeline_harness fixture never had this risk — it
    starts wake_word_detector last, by hand, after every other module
    including communication_pipeline.

    max_utterance_seconds=10.0 (was 2.0): the same early-wake-match issue
    means the session's utterance-capture clock can start ticking during
    fixture setup, well before the test calls push_utterance() — a
    max_utterance_seconds too close to the realistic setup-to-first-push
    gap let the safety cap force an empty "utterance complete" before the
    test's real pushed audio was ever read, concretely reproduced
    (first spoken reply was the empty-transcript fallback, not the
    scripted transcript) once Level 3's added startup latency widened
    that gap. 10.0s leaves comfortable margin; the silence-based
    utterance-end detection (utterance_silence_ms/threshold) still
    completes each real pushed utterance almost immediately regardless,
    so this only changes how long a truly-silent session can run before
    the safety cap intervenes, not real per-turn latency."""
    return VoiceConfig(
        mic_sample_rate_hz=16000,
        utterance_silence_ms=30,
        utterance_silence_threshold=0.02,
        max_utterance_seconds=10.0,
        session_timeout_seconds=3.0,
    )


@pytest.fixture
def app_harness(tmp_path, voice_config):
    """Builds the real Level 2 + Level 3 module graph exactly as main.py's
    _register_level2_modules()/_register_level3_modules() do, registers
    every ManagedModule with a real CoreManager, and drives it through
    startup()/shutdown() — fakes only at the mic/wake-engine/STT/TTS/
    Ollama boundary."""
    config = AppConfig(
        voice=voice_config,
        database=DatabaseConfig(
            sqlite_path=str(tmp_path / "conversations.db"),
            chroma_path=str(tmp_path / "chroma"),
        ),
        memory=MemoryConfig(chroma_collection_prefix="app_harness"),
    )
    resource_monitor = ResourceMonitor(config.resources)
    core_manager = CoreManager(config, resource_monitor, config_loader=MagicMock())

    audio_backend = FakeAudioBackend()
    mic = MicrophoneManager(config.voice, audio_backend)
    stt = FakeSpeechToText()
    tts = FakeTextToSpeech()

    sqlite_client = SqliteClient(config.database.sqlite_path)
    conversation_store = ConversationSessionStore(sqlite_client, config.database)
    context_manager = ContextManager(conversation_store)

    jarvis = JarvisPersona(config.voice)
    minie = MiniePersona(config.voice)
    persona_manager = PersonaManager(jarvis, minie, config.voice)

    turn_complete_relay = CallbackRelay()
    session_ended_relay = CallbackRelay()
    session_manager = VoiceSessionManager(
        mic, stt, tts, config.voice, turn_complete_relay, session_ended_relay
    )
    quiet_mode_controller = QuietModeController(session_manager)

    wake_engine = FakeWakeWordEngine(match_on_call=2)
    wake_word_detector = WakeWordDetector(
        mic, wake_engine, quiet_mode_controller._on_wake_word_detected
    )

    memory_sqlite_client = SqliteClient(config.database.sqlite_path)
    chroma_client = ChromaMemoryClient(config.memory, config.database)
    memory_store = MemoryStore(memory_sqlite_client, chroma_client)
    persona_scoped_memory = PersonaScopedMemory(memory_store)
    event_memory = EventMemory(memory_store)
    short_term_memory = ShortTermMemory(memory_store, config.memory)
    confidence_scorer = ConfidenceScorer(config.memory)
    memory_lifecycle_manager = MemoryLifecycleManager(
        memory_store, confidence_scorer, config.memory
    )
    memory_retrieval_engine = MemoryRetrievalEngine(
        persona_scoped_memory, event_memory, short_term_memory, confidence_scorer, config.memory
    )

    llm_client = FakeLanguageModelClient()
    intent_detector = IntentDetector(llm_client, config.models)
    context_analyzer = ContextAnalyzer(llm_client, config.models)
    priority_queue_manager = PriorityQueueManager(resource_monitor)
    authority_evaluator = AuthorityEvaluator()

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
        intent_detector=intent_detector,
        context_analyzer=context_analyzer,
        memory_retrieval_engine=memory_retrieval_engine,
        priority_queue_manager=priority_queue_manager,
        authority_evaluator=authority_evaluator,
        short_term_memory=short_term_memory,
        confidence_scorer=confidence_scorer,
        memory_lifecycle_manager=memory_lifecycle_manager,
    )

    core_manager.register_module("microphone", mic)
    core_manager.register_module("speech_to_text", _StartStopWrapper(stt))
    core_manager.register_module("text_to_speech", _StartStopWrapper(tts))
    core_manager.register_module("conversation_store", conversation_store)
    core_manager.register_module("persona_manager", persona_manager)
    core_manager.register_module("voice_session_manager", session_manager)
    core_manager.register_module("quiet_mode_controller", quiet_mode_controller)
    core_manager.register_module("wake_word_detector", wake_word_detector)
    # communication_pipeline is registered immediately after
    # wake_word_detector, BEFORE any Level 3 module — a deliberate
    # ordering (see main.py's own _register_level3_modules() docstring
    # for the full reasoning): CoreManager.startup() calls start() in
    # registration order, and wake_word_detector's background thread can
    # fire as soon as its own start() runs. If a slower Level 3 start()
    # (memory_store's Chroma embedding-model load) sat between
    # wake_word_detector and communication_pipeline, a session could
    # complete/time out and route through on_session_ended/on_turn_
    # complete's relays before communication_pipeline.start() has wired
    # them — concretely observed as a real, reproducible failure in this
    # exact fixture (short session_timeout_seconds) before this fix.
    core_manager.register_module("communication_pipeline", pipeline)
    core_manager.register_module("memory_store", memory_store)
    core_manager.register_module("memory_lifecycle_manager", memory_lifecycle_manager)
    core_manager.register_module("intent_detector", intent_detector)
    core_manager.register_module("context_analyzer", context_analyzer)
    core_manager.register_module("priority_queue_manager", priority_queue_manager)
    core_manager.register_module("authority_evaluator", authority_evaluator)

    core_manager.startup()

    harness = SimpleNamespace(
        core_manager=core_manager,
        mic=mic,
        audio_backend=audio_backend,
        stt=stt,
        tts=tts,
        wake_engine=wake_engine,
        conversation_store=conversation_store,
        persona_manager=persona_manager,
        session_manager=session_manager,
        quiet_mode_controller=quiet_mode_controller,
        # Sprint 3.14 (Level 3 Acceptance Pass) additions — every Level 3
        # collaborator already constructed above, now exposed so the new
        # system test can exercise memory/confidence/lifecycle/priority
        # behavior directly, not just observe it indirectly through a
        # spoken reply.
        memory_store=memory_store,
        persona_scoped_memory=persona_scoped_memory,
        event_memory=event_memory,
        short_term_memory=short_term_memory,
        confidence_scorer=confidence_scorer,
        memory_lifecycle_manager=memory_lifecycle_manager,
        memory_retrieval_engine=memory_retrieval_engine,
        llm_client=llm_client,
        intent_detector=intent_detector,
        context_analyzer=context_analyzer,
        priority_queue_manager=priority_queue_manager,
        authority_evaluator=authority_evaluator,
        resource_monitor=resource_monitor,
    )
    try:
        yield harness
    finally:
        core_manager.shutdown()


@pytest.fixture
def wait_for_active_capture():
    def _wait(mic, timeout: float = WAIT_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if mic.current_mode() is MicrophoneMode.ACTIVE_CAPTURE:
                return
            time.sleep(0.02)
        raise AssertionError("Timed out waiting for the microphone to enter ACTIVE_CAPTURE.")

    return _wait


@pytest.fixture
def wait_for_dormant():
    def _wait(quiet_mode_controller, timeout: float = WAIT_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if quiet_mode_controller.current_mode() is OperatingMode.DORMANT:
                return
            time.sleep(0.02)
        raise AssertionError("Timed out waiting for Quiet Mode Controller to return to DORMANT.")

    return _wait


@pytest.fixture
def push_utterance():
    def _push(audio_backend, loud_frames: int = 5, quiet_frames: int = 5) -> None:
        audio_backend.frame_queue.extend([LOUD_FRAME] * loud_frames)
        audio_backend.frame_queue.extend([QUIET_FRAME] * quiet_frames)

    return _push
