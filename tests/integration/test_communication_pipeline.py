"""Integration tests for voice.pipeline.CommunicationPipeline — the first
real, end-to-end exercise of every Level 2 (Communication) module wired
together (Sprint 2.12).

Fakes stand in only at the audio-hardware/ML boundary (AudioBackend,
WakeWordEngine, SpeechToText, TextToSpeech) — the same "fake only at the
seams that need real hardware/models" precedent every Level 2 unit-test
file already established since Sprint 2.1. Everything else is real:
MicrophoneManager, WakeWordDetector, VoiceSessionManager,
QuietModeController, a real SQLite file under tmp_path via SqliteClient/
ConversationSessionStore, ContextManager, JarvisPersona/MiniePersona,
PersonaManager, and CommunicationPipeline itself. No physical hardware
and no ML model downloads are required to run this suite, matching this
sprint's own Risks about CI feasibility of "real" models — real Whisper/
Coqui/openWakeWord verification was done separately via a one-off,
non-committed scratchpad smoke script during this sprint's
implementation.
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

_WAIT_TIMEOUT = 5.0

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

    def open(self, device_index: int | None, sample_rate_hz: int) -> None:
        self.is_open = True

    def read(self, num_frames: int) -> bytes:
        if self.frame_queue:
            return self.frame_queue.pop(0)
        return b"\x00\x00" * num_frames

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
    lets a test script a multi-turn conversation."""

    def __init__(self) -> None:
        self.pending_transcripts: list[str] = []
        self.calls: list[bytes] = []

    def transcribe(self, audio: bytes) -> TranscriptionResult:
        self.calls.append(audio)
        text = self.pending_transcripts.pop(0) if self.pending_transcripts else ""
        return TranscriptionResult(text=text, average_confidence=0.9, duration_ms=1)


class FakeTextToSpeech:
    def __init__(self) -> None:
        self.speak_calls: list[tuple[str, str]] = []
        self.spoken_event = threading.Event()

    def speak(self, text: str, voice_id: str) -> None:
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


def _wait_for_active_capture(mic, timeout: float = _WAIT_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if mic.current_mode() is MicrophoneMode.ACTIVE_CAPTURE:
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for the microphone to enter ACTIVE_CAPTURE.")


def _wait_for_dormant(quiet_mode_controller, timeout: float = _WAIT_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if quiet_mode_controller.current_mode() is OperatingMode.DORMANT:
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for Quiet Mode Controller to return to DORMANT.")


def _push_utterance(audio_backend, loud_frames: int = 5, quiet_frames: int = 5) -> None:
    audio_backend.frame_queue.extend([LOUD_FRAME] * loud_frames)
    audio_backend.frame_queue.extend([QUIET_FRAME] * quiet_frames)


def test_full_wake_to_reply_round_trip(pipeline_harness):
    """Demonstrates Phase 2.1/2.2/2.3's acceptance criteria together in
    one real run: wake phrase activates JARMINEI, speech recognition
    functions, a persona composes and speaks a reply, the turn is
    persisted, and the session returns cleanly to Quiet Mode afterward."""
    h = pipeline_harness

    # Wake phrase activates JARMINEI.
    _wait_for_active_capture(h.mic)
    assert h.quiet_mode_controller.current_mode() is OperatingMode.ACTIVE
    assert h.session_manager.is_active()
    session_id = h.session_manager._session.session_id

    # Speech recognition + persona reply + voice response. Deliberately a
    # transcript with no overlap with either of PersonaManager's crude
    # context-heuristic keyword lists (voice/persona_manager.py) — this
    # test is about the basic round trip, not persona-switching, which
    # test_explicit_minie_selection_switches_voice_for_next_reply covers.
    h.stt.pending_transcripts.append("what time is it right now")
    _push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)

    reply_text, voice_id = h.tts.speak_calls[0]
    assert "what time is it right now" in reply_text
    assert h.persona_manager.active_persona().name == "jarvis"  # default, unswitched
    assert voice_id == h.persona_manager.active_persona().voice_id
    assert h.persona_manager.health_check() is True  # exactly one persona active

    # The turn was actually persisted through the real Conversation
    # Session Store (2.7), not just spoken.
    recent_turns = h.conversation_store.get_recent_turns(session_id, limit=10)
    assert len(recent_turns) == 1
    assert recent_turns[0].user_text == "what time is it right now"
    assert recent_turns[0].persona_name == "jarvis"

    # Silence timeout ends the session and returns to Quiet Mode.
    _wait_for_dormant(h.quiet_mode_controller)
    assert h.mic.current_mode() is MicrophoneMode.PASSIVE_LISTENING
    assert not h.session_manager.is_active()


def test_explicit_minie_selection_switches_voice_for_next_reply(pipeline_harness):
    """Testing Checklist: 'an explicit "talk to Minie" utterance
    mid-conversation actually switches the active voice for the next
    reply.'"""
    h = pipeline_harness

    _wait_for_active_capture(h.mic)
    assert h.persona_manager.active_persona().name == "jarvis"

    # Turn 1: ordinary utterance, default Jarvis persona replies.
    h.stt.pending_transcripts.append("what's the weather like")
    _push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)
    _, first_voice_id = h.tts.speak_calls[0]
    assert h.persona_manager.active_persona().name == "jarvis"
    assert first_voice_id == h.persona_manager.active_persona().voice_id

    # Turn 2: an explicit selection utterance switches persona and voice.
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("talk to minie please")
    _push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)

    assert h.persona_manager.active_persona().name == "minie"
    _, second_voice_id = h.tts.speak_calls[1]
    assert second_voice_id == h.persona_manager.active_persona().voice_id
    assert second_voice_id != first_voice_id
    assert h.persona_manager.health_check() is True
