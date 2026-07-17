"""Voice Session Manager — owns the lifecycle of one active voice
interaction, from the moment listening becomes active through however
many spoken turns occur, until silence or explicit end returns control to
Quiet Mode.

This is a turn-timing and lifecycle module, not a conversation-history
module: it tracks *that* turns are happening and *when* the last one
ended, not *what was said* beyond the single in-flight turn. Persisted
multi-turn history is Conversation Session Store's job (Sprint 2.7); this
module holds only ephemeral, in-memory timing state that vanishes when the
session ends. See docs/sprint_book/sprint_2_5.md.

State machine (one cycle per turn, repeating until the session ends):

    IDLE --begin_session()--> LISTENING --utterance boundary--> PROCESSING
      ^                                                              |
      |                                                    on_turn_complete fired
      |                                                              v
      +--end_session()-- SPEAKING <--speak_reply()-- AWAITING_NEXT_TURN

Two independent timing mechanisms, deliberately not conflated:
  - session_timeout_seconds (inter-turn): a background watchdog thread,
    running for this module's entire start()/stop() lifetime, ends the
    session if no activity (turn completed / reply spoken) has been
    recorded within the window — catches "the user walked away."
  - utterance_silence_ms (intra-utterance): energy-based silence
    detection within a single utterance capture — trailing silence past
    this duration (after some speech was already heard) marks the
    utterance's end, handed to Speech-to-Text. This is the sprint's own
    flagged "utterance-boundary detection" decision point, resolved here
    as simple RMS-threshold silence detection rather than a separate VAD
    model — proportionate to what a turn-taking voice assistant needs,
    consistent with Reliability-over-Intelligence.
"""

import math
import threading
import time
import uuid
from array import array
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from config.schema import VoiceConfig
from core.logging_setup import get_logger
from voice.errors import MicrophoneError, SessionError, SpeechToTextError, TextToSpeechError
from voice.microphone import MicrophoneManager, MicrophoneMode
from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech

logger = get_logger(__name__)

_WATCHDOG_POLL_SECONDS = 0.5
"""How often the inter-turn timeout watchdog checks for staleness. Small
relative to session_timeout_seconds so the timeout fires promptly without
busy-looping."""

_THREAD_JOIN_TIMEOUT_SECONDS = 5.0


class SessionState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    AWAITING_NEXT_TURN = "awaiting_next_turn"


class SessionEndReason(Enum):
    SILENCE_TIMEOUT = "silence_timeout"
    EXPLICIT_END = "explicit_end"
    ERROR = "error"


@dataclass
class VoiceSession:
    """Ephemeral session metadata — never written to disk by this module
    (contrast with Conversation Session Store, Sprint 2.7)."""

    session_id: str
    started_at: datetime
    last_activity_at: datetime = field(default=None)
    turn_count: int = 0

    def __post_init__(self) -> None:
        if self.last_activity_at is None:
            self.last_activity_at = self.started_at


def _rms(frame: bytes) -> float:
    """Normalized (0-1) root-mean-square amplitude of an int16 PCM frame.
    Pure stdlib (array/math), no numpy dependency for this module."""
    if not frame:
        return 0.0
    samples = array("h")
    samples.frombytes(frame)
    if not samples:
        return 0.0
    mean_sq = sum(s * s for s in samples) / len(samples)
    return math.sqrt(mean_sq) / 32768.0


class VoiceSessionManager:
    """Orchestrates one active voice session's turn cycle.

    Constructor DI per 03_Engineering_Standards.md: receives the
    MicrophoneManager/SpeechToText/TextToSpeech instances it depends on,
    plus callbacks, rather than constructing any of them itself.
    """

    def __init__(
        self,
        mic: MicrophoneManager,
        stt: SpeechToText,
        tts: TextToSpeech,
        voice_config: VoiceConfig,
        on_turn_complete: Callable[[str, str], None],
        on_session_ended: Callable[[SessionEndReason], None],
    ) -> None:
        self._mic = mic
        self._stt = stt
        self._tts = tts
        self._voice_config = voice_config
        self._on_turn_complete = on_turn_complete
        self._on_session_ended = on_session_ended

        self._session: VoiceSession | None = None
        self._state = SessionState.IDLE
        self._ended = False
        self._end_lock = threading.Lock()

        self._listen_thread: threading.Thread | None = None
        self._stop_listening = threading.Event()
        self._reply_ready = threading.Event()

        self._watchdog_thread: threading.Thread | None = None
        self._watchdog_stop = threading.Event()

    def start(self) -> None:
        """Launch the inter-turn timeout watchdog. Does not itself start
        a session — that's begin_session()'s job, called by Quiet Mode
        Controller (Sprint 2.6) on wake-word detection."""
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="voice-session-watchdog", daemon=True
        )
        self._watchdog_thread.start()
        logger.info("Voice session watchdog started.")

    def stop(self) -> None:
        """Stop the watchdog and end any active session."""
        self._watchdog_stop.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
            self._watchdog_thread = None
        if self.is_active():
            self.end_session(SessionEndReason.EXPLICIT_END)
        logger.info("Voice session watchdog stopped.")

    def health_check(self) -> bool:
        return self._watchdog_thread is not None and self._watchdog_thread.is_alive()

    def is_active(self) -> bool:
        return self._session is not None

    def begin_session(self) -> VoiceSession:
        """Begin a new session: switch the mic to active capture and
        start listening for the first utterance."""
        now = datetime.now(UTC)
        session = VoiceSession(session_id=str(uuid.uuid4()), started_at=now, last_activity_at=now)
        self._session = session
        self._ended = False
        self._state = SessionState.LISTENING
        self._mic.set_mode(MicrophoneMode.ACTIVE_CAPTURE)
        self._stop_listening.clear()
        self._reply_ready.clear()
        self._listen_thread = threading.Thread(
            target=self._session_loop, name="voice-session-listener", daemon=True
        )
        self._listen_thread.start()
        logger.info("Voice session begun: %s", session.session_id)
        return session

    def end_session(self, reason: SessionEndReason) -> None:
        """End the current session, idempotently — only the first call
        (per session) takes effect, guarding against the double-fire risk
        flagged in this sprint's spec (e.g. a reply finishing to speak at
        the same moment the inter-turn timeout expires)."""
        with self._end_lock:
            if self._ended or self._session is None:
                return
            self._ended = True
            session_id = self._session.session_id

        self._stop_listening.set()
        self._reply_ready.set()
        try:
            self._mic.set_mode(MicrophoneMode.PASSIVE_LISTENING)
        except MicrophoneError:
            logger.exception("Failed to return microphone to passive mode while ending session.")

        self._state = SessionState.IDLE
        self._session = None
        logger.info("Voice session ended: %s (%s)", session_id, reason.value)
        self._on_session_ended(reason)

    def speak_reply(self, text: str, voice_id: str) -> None:
        """Speak a composed reply, then re-arm listening for the next
        turn. Called once a persona reply exists (Sprint 2.9+)."""
        if self._session is None:
            raise SessionError("Cannot speak a reply outside an active session.")
        self._session.last_activity_at = datetime.now(UTC)
        self._state = SessionState.SPEAKING
        try:
            self._tts.speak(text, voice_id)
        except TextToSpeechError:
            logger.exception("Failed to speak reply.")
            self.end_session(SessionEndReason.ERROR)
            return
        if self._session is not None:
            self._session.last_activity_at = datetime.now(UTC)
            self._state = SessionState.LISTENING
        self._reply_ready.set()

    def _watchdog_loop(self) -> None:
        timeout = self._voice_config.session_timeout_seconds
        while not self._watchdog_stop.wait(timeout=_WATCHDOG_POLL_SECONDS):
            session = self._session
            if session is None:
                continue
            idle_for = (datetime.now(UTC) - session.last_activity_at).total_seconds()
            if idle_for >= timeout:
                self.end_session(SessionEndReason.SILENCE_TIMEOUT)

    def _session_loop(self) -> None:
        while not self._stop_listening.is_set():
            try:
                audio = self._capture_one_utterance()
            except MicrophoneError:
                logger.exception("Microphone failure during utterance capture.")
                self.end_session(SessionEndReason.ERROR)
                return
            if audio is None or self._stop_listening.is_set():
                return

            self._state = SessionState.PROCESSING
            self._on_utterance_ready(audio)
            if self._stop_listening.is_set():
                return

            self._state = SessionState.AWAITING_NEXT_TURN
            self._reply_ready.wait()
            self._reply_ready.clear()
            if self._stop_listening.is_set():
                return

    def _capture_one_utterance(self) -> bytes | None:
        """Buffer frames until trailing silence (utterance_silence_ms)
        follows detected speech, or max_utterance_seconds is reached as a
        safety cap against unbounded buffering. Returns None if listening
        was stopped mid-capture (session ending)."""
        frames: list[bytes] = []
        has_spoken = False
        silence_started_at: float | None = None
        started_at = time.monotonic()
        silence_limit = self._voice_config.utterance_silence_ms / 1000
        max_duration = self._voice_config.max_utterance_seconds

        while not self._stop_listening.is_set():
            frame = self._mic.read_frame()
            frames.append(frame)

            if _rms(frame) >= self._voice_config.utterance_silence_threshold:
                has_spoken = True
                silence_started_at = None
            elif has_spoken:
                if silence_started_at is None:
                    silence_started_at = time.monotonic()
                elif (time.monotonic() - silence_started_at) >= silence_limit:
                    return b"".join(frames)

            if (time.monotonic() - started_at) >= max_duration:
                logger.warning("Utterance capture hit max_utterance_seconds safety cap.")
                return b"".join(frames)
        return None

    def _on_utterance_ready(self, audio: bytes) -> None:
        session = self._session
        if session is None:
            return
        try:
            result = self._stt.transcribe(audio)
        except SpeechToTextError:
            logger.exception("Transcription failed.")
            self.end_session(SessionEndReason.ERROR)
            return

        session.turn_count += 1
        session.last_activity_at = datetime.now(UTC)
        self._on_turn_complete(result.text, session.session_id)
