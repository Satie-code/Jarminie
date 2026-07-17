"""Shared fixtures and fakes for tests/integration/ — the real,
non-mocked exercise of Level 2's Communication Pipeline (Sprint 2.12) and
its hardened failure paths (Sprint 2.13), reused by
test_communication_pipeline.py (2.12/2.13's own file) and
test_voice_pipeline_integration.py (Sprint 2.14's expansion covering the
remaining hardened scenarios at integration level).

Fakes stand in only at the audio-hardware/ML boundary (AudioBackend,
WakeWordEngine, SpeechToText, TextToSpeech) — the same "fake only at the
seams that need real hardware/models" precedent every Level 2 unit-test
file already established since Sprint 2.1. Everything else is real:
MicrophoneManager, WakeWordDetector, VoiceSessionManager,
QuietModeController, a real SQLite file under tmp_path via SqliteClient/
ConversationSessionStore, ContextManager, JarvisPersona/MiniePersona,
PersonaManager, and CommunicationPipeline itself. No physical hardware
and no ML model downloads are required to run this suite — real Whisper/
Coqui/openWakeWord verification is done separately via one-off,
non-committed scratchpad smoke scripts (Sprint 2.12, 2.14).

Plain helper functions/classes can't be imported across files here
(tests/ has no __init__.py, by convention since Sprint 1.1), so shared
helpers are exposed as fixtures instead, same pattern as
tests/unit/voice/conftest.py.
"""

import threading
import time
from types import SimpleNamespace

import pytest

from config.schema import DatabaseConfig, VoiceConfig
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
    """Real hardware would block on read(); this returns instantly, which
    is exactly why WakeWordDetector's Sprint 2.12 pause-while-active fix
    (see voice/wake_word.py) matters here — without it, this backend's
    unthrottled reads would let the still-running wake-word thread starve
    the session's own utterance capture of every frame."""

    def __init__(self) -> None:
        self.is_open = False
        self.frame_queue: list[bytes] = []
        self.raise_on_read = False

    def open(self, device_index: int | None, sample_rate_hz: int) -> None:
        self.is_open = True

    def read(self, num_frames: int) -> bytes:
        if self.raise_on_read:
            raise RuntimeError("simulated device disconnect")
        if self.frame_queue:
            return self.frame_queue.pop(0)
        return b"\x00\x00" * num_frames

    def flush(self) -> None:
        """VoiceSessionManager.begin_session() calls this immediately
        after switching to ACTIVE_CAPTURE (post-release fix) — safe to
        genuinely clear frame_queue here since every test in this
        directory only calls push_utterance() after the session has
        already begun, never before."""
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
    """Returns queued transcripts in order, one per transcribe() call —
    lets a test script a multi-turn conversation. should_raise (Sprint
    2.14, scenario b at integration level) simulates a Whisper failure."""

    def __init__(self) -> None:
        self.pending_transcripts: list[str] = []
        self.calls: list[bytes] = []
        self.should_raise = False

    def transcribe(self, audio: bytes) -> TranscriptionResult:
        self.calls.append(audio)
        if self.should_raise:
            from voice.errors import SpeechToTextError

            raise SpeechToTextError("simulated Whisper transcription failure")
        text = self.pending_transcripts.pop(0) if self.pending_transcripts else ""
        return TranscriptionResult(text=text, average_confidence=0.9, duration_ms=1)


class FakeTextToSpeech:
    """should_raise (Sprint 2.14, scenario c at integration level)
    simulates a Coqui synthesis/playback failure."""

    def __init__(self) -> None:
        self.speak_calls: list[tuple[str, str]] = []
        self.spoken_event = threading.Event()
        self.should_raise = False

    def speak(self, text: str, voice_id: str) -> None:
        if self.should_raise:
            from voice.errors import TextToSpeechError

            raise TextToSpeechError("simulated Coqui synthesis failure")
        self.speak_calls.append((text, voice_id))
        self.spoken_event.set()


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
def pipeline_harness(tmp_path, voice_config):
    """Builds the real Communication Pipeline object graph, matching
    main.py's own composition order exactly (_register_level2_modules) —
    fakes only at the mic/wake-engine/STT/TTS boundary."""
    audio_backend = FakeAudioBackend()
    mic = MicrophoneManager(voice_config, audio_backend)

    stt = FakeSpeechToText()
    tts = FakeTextToSpeech()

    database_config = DatabaseConfig(sqlite_path=str(tmp_path / "conversations.db"))
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

    mic.start()
    conversation_store.start()
    persona_manager.start()
    session_manager.start()
    quiet_mode_controller.start()
    pipeline.start()
    wake_word_detector.start()

    harness = SimpleNamespace(
        mic=mic,
        audio_backend=audio_backend,
        stt=stt,
        tts=tts,
        wake_engine=wake_engine,
        wake_word_detector=wake_word_detector,
        conversation_store=conversation_store,
        persona_manager=persona_manager,
        session_manager=session_manager,
        quiet_mode_controller=quiet_mode_controller,
        pipeline=pipeline,
    )
    try:
        yield harness
    finally:
        wake_word_detector.stop()
        pipeline.stop()
        quiet_mode_controller.stop()
        session_manager.stop()
        persona_manager.stop()
        conversation_store.stop()
        mic.stop()


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
