"""Shared fixtures for tests/system/ — full-application system tests that
go through a real CoreManager.startup()/shutdown() with the entire Level 2
module graph registered, the same way main.py's own
_register_level2_modules() does. This is what distinguishes this tier
from tests/integration/: those tests start each module individually in a
hand-picked order via the pipeline_harness fixture; this tier instead
proves CoreManager's registration/startup/shutdown-order guarantees
themselves hold for the real Level 2 graph.

Fakes stand in only at the audio-hardware/ML boundary, same as
tests/integration/conftest.py — kept self-contained rather than shared
across test tiers, matching this project's existing per-directory
conftest convention (tests/unit/voice/conftest.py and
tests/unit/personas/conftest.py are likewise independent of each other).
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config.schema import AppConfig, DatabaseConfig, VoiceConfig
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
from database.sqlite_client import SqliteClient
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
    return VoiceConfig(
        mic_sample_rate_hz=16000,
        utterance_silence_ms=30,
        utterance_silence_threshold=0.02,
        max_utterance_seconds=2.0,
        session_timeout_seconds=0.8,
    )


@pytest.fixture
def app_harness(tmp_path, voice_config):
    """Builds the real Level 2 module graph exactly as main.py's
    _register_level2_modules() does, registers every ManagedModule with a
    real CoreManager, and drives it through startup()/shutdown() — fakes
    only at the mic/wake-engine/STT/TTS boundary."""
    config = AppConfig(
        voice=voice_config,
        database=DatabaseConfig(sqlite_path=str(tmp_path / "conversations.db")),
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
    core_manager.register_module("speech_to_text", _StartStopWrapper(stt))
    core_manager.register_module("text_to_speech", _StartStopWrapper(tts))
    core_manager.register_module("conversation_store", conversation_store)
    core_manager.register_module("persona_manager", persona_manager)
    core_manager.register_module("voice_session_manager", session_manager)
    core_manager.register_module("quiet_mode_controller", quiet_mode_controller)
    core_manager.register_module("wake_word_detector", wake_word_detector)
    core_manager.register_module("communication_pipeline", pipeline)

    core_manager.startup()

    harness = SimpleNamespace(
        core_manager=core_manager,
        mic=mic,
        audio_backend=audio_backend,
        stt=stt,
        tts=tts,
        conversation_store=conversation_store,
        persona_manager=persona_manager,
        session_manager=session_manager,
        quiet_mode_controller=quiet_mode_controller,
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
