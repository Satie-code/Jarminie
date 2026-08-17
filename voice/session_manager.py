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
from voice.speech_to_text import SpeechToText, TranscriptionResult
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

        # Sprint 4.7 (Permission & Confirmation System): lets
        # capture_and_transcribe_reply() intercept the next utterance
        # this session's own _session_loop() thread captures, routing it
        # to a waiting caller instead of the normal on_turn_complete
        # callback — see that method's own docstring.
        self._pending_reply_event = threading.Event()
        self._pending_reply_text: str | None = None
        self._awaiting_external_reply = False

        # Sprint 5.14: exposes this session's own internal turn-phase/
        # transcription state to CommunicationPipeline for real Presentation
        # Layer wiring (EmotionDetectionEngine.collect_signals() needs the
        # full TranscriptionResult, not just its .text; JarvisRenderer's
        # per-phase RingState needs the real SessionState) — see
        # current_session_state()/last_transcription_result() below. Both
        # are read-only accessors over state this class already tracks
        # internally; neither adds a new state dimension of its own.
        self._last_transcription_result: TranscriptionResult | None = None

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
        """Stop the watchdog and end any active session.

        Sprint 6.17 (Async Background Task Audit) hardening: also joins
        _listen_thread ("voice-session-listener"), which every prior
        sprint left unjoined — asymmetric with its own _watchdog_thread
        sibling three lines above, joined since this class's original
        Sprint 2.5 implementation. Confirmed as the direct root cause of
        backlog/technical_debt.md item 50's real, measured 1750+-thread
        full-suite accumulation: end_session() (called here, or earlier
        by the watchdog/the listener thread itself) signals
        _stop_listening but stop() previously returned immediately
        without confirming _session_loop() actually observed it and
        exited, so a fixture's next setup could already be constructing
        a fresh VoiceSessionManager (and fresh threads) while the prior
        test's own listener was still winding down — across thousands of
        tests in one process, straggling not-yet-exited listener threads
        compound (heavier GIL contention makes each successive straggler
        take longer to get scheduled), a real, self-reinforcing
        accumulation, not merely a cosmetic delay. Joined AFTER
        end_session() (not inside it): end_session() can itself run on
        this very listener thread (_session_loop()'s own MicrophoneError/
        SpeechToTextError paths), where joining would be a same-thread
        self-join — safe only from stop()'s own external caller."""
        self._watchdog_stop.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
            self._watchdog_thread = None
        if self.is_active():
            self.end_session(SessionEndReason.EXPLICIT_END)
        if self._listen_thread is not None:
            self._listen_thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
            if self._listen_thread.is_alive():
                logger.error("Voice session listener thread did not stop within timeout.")
            self._listen_thread = None
        logger.info("Voice session watchdog stopped.")

    def health_check(self) -> bool:
        return self._watchdog_thread is not None and self._watchdog_thread.is_alive()

    def is_active(self) -> bool:
        return self._session is not None

    def current_session_state(self) -> SessionState:
        """Sprint 5.14: the real, current SessionState (LISTENING/
        PROCESSING/SPEAKING/etc.) — CommunicationPipeline's own real
        caller threads this into JarvisRenderer's per-phase RingState,
        closing the granularity gap Sprint 5.7 named explicitly. A plain
        read of state this class already tracks internally; adds no new
        state."""
        return self._state

    def last_transcription_result(self) -> TranscriptionResult | None:
        """Sprint 5.14: the most recent utterance's full TranscriptionResult
        (not just its .text) — EmotionDetectionEngine.collect_signals()'s
        own real caller needs duration_ms/no_speech_probability, which the
        on_turn_complete callback's plain (text, session_id) signature
        never carried. None before any utterance has been transcribed."""
        return self._last_transcription_result

    def begin_session(self, announce_first: tuple[str, str] | None = None) -> VoiceSession:
        """Begin a new session: switch the mic to active capture and
        start listening for the first utterance.

        Post-release fix (found via real end-to-end testing after Level 2
        shipped): flush_stale_audio() immediately after the mode switch
        discards whatever's already buffered — typically the just-spoken
        wake phrase itself, since wake-word detection has inherent lag
        (the model needs a window of audio context before it can
        recognize a phrase) and the underlying stream never actually
        pauses (see MicrophoneManager's own docstring). Without this, the
        wake phrase's own audio was the first thing Whisper transcribed,
        e.g. "hey jarvis" being echoed back as if it were the command.

        announce_first (Sprint 4.18, additive — None preserves every
        existing caller's exact prior behavior) is a (text, voice_id)
        pair spoken via TTS BEFORE the utterance-capture thread starts,
        for JARMINEI-initiated sessions (a proactive reminder
        announcement, QuietModeController.activate(SCHEDULED_ALERT))
        where the correct order is speak-first-then-listen, the reverse
        of every wake-word-triggered session. Speaking before the
        capture thread exists is deliberate, not incidental: starting
        capture first would let the announcement's own TTS playback be
        picked up by the still-active microphone concurrently with
        _session_loop()'s own utterance capture — a real, previously
        unseen risk (JARMINEI's own voice mistaken for user speech, or a
        premature "utterance complete" firing on captured silence) this
        project has never had to guard against before, since every prior
        session's own first spoken reply always followed a real captured
        user utterance rather than preceding one. A TTS failure during
        this pre-listen announcement is NOT swallowed — the session is
        torn back down (mic returned to passive, self._session cleared)
        and the exception re-raised, so QuietModeController.activate()'s
        own existing try/except (already rolling back to DORMANT on any
        begin_session() failure) keeps its own state and this class's
        state in agreement; health_check() would otherwise see a
        DORMANT-with-still-active-session mismatch."""
        now = datetime.now(UTC)
        session = VoiceSession(session_id=str(uuid.uuid4()), started_at=now, last_activity_at=now)
        self._session = session
        self._ended = False
        self._state = SessionState.LISTENING
        self._mic.set_mode(MicrophoneMode.ACTIVE_CAPTURE)
        self._mic.flush_stale_audio()
        self._stop_listening.clear()
        self._reply_ready.clear()

        if announce_first is not None:
            text, voice_id = announce_first
            self._state = SessionState.SPEAKING
            try:
                self._tts.speak(text, voice_id)
            except TextToSpeechError:
                self._session = None
                self._state = SessionState.IDLE
                try:
                    self._mic.set_mode(MicrophoneMode.PASSIVE_LISTENING)
                except MicrophoneError:
                    logger.exception(
                        "Failed to return microphone to passive mode after a failed "
                        "pre-listen announcement."
                    )
                raise
            self._state = SessionState.LISTENING
            session.last_activity_at = datetime.now(UTC)

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
        # Unblocks anyone currently waiting inside
        # capture_and_transcribe_reply() immediately, rather than
        # leaving them to discover the session ended only once their
        # own timeout eventually expires.
        self._pending_reply_event.set()
        try:
            self._mic.set_mode(MicrophoneMode.PASSIVE_LISTENING)
        except MicrophoneError:
            logger.exception("Failed to return microphone to passive mode while ending session.")

        self._state = SessionState.IDLE
        self._session = None
        logger.info("Voice session ended: %s (%s)", session_id, reason.value)
        self._on_session_ended(reason)

    def capture_and_transcribe_reply(self, timeout_seconds: float) -> str | None:
        """Synchronously waits for the next utterance this session's own
        background loop (_session_loop()) captures and transcribes,
        returning its text instead of routing it to on_turn_complete —
        added for security.confirmation_service.VoiceConfirmationService
        (Sprint 4.7) to intercept a yes/no confirmation reply using the
        exact same capture machinery a normal turn uses, without a
        second, concurrent mic-reading path (which would risk
        reintroducing the exact class of frame-stealing bug Sprint
        2.12's own wake-word/session fix resolved once already).

        Returns None if no session is active, or if no utterance is
        transcribed within timeout_seconds (including because the
        session ended while waiting) — never raises, never hangs past
        the given timeout.

        Intended call sequence: speak_reply(prompt, voice_id) — which
        itself re-arms the session's own loop to start capturing the
        next utterance — immediately followed by this method. The tiny
        window between speak_reply() re-arming the loop and this method
        setting its own "a caller is waiting" flag is a real but
        practically negligible race: _capture_one_utterance() itself
        cannot complete faster than genuine mic silence/speech timing
        allows, which is far slower than the handful of Python bytecode
        instructions between the two calls.
        """
        if self._session is None:
            return None
        self._pending_reply_event.clear()
        self._pending_reply_text = None
        self._awaiting_external_reply = True
        try:
            received = self._pending_reply_event.wait(timeout=timeout_seconds)
            return self._pending_reply_text if received else None
        finally:
            self._awaiting_external_reply = False

    def speak_reply(
        self,
        text: str,
        voice_id: str,
        on_audio_ready: Callable[[bytes, int], None] | None = None,
    ) -> None:
        """Speak a composed reply, then re-arm listening for the next
        turn. Called once a persona reply exists (Sprint 2.9+).
        on_audio_ready (Sprint 5.14, additive — None preserves every
        existing caller's exact prior behavior) is forwarded straight
        through to TextToSpeech.speak() — see that module's own
        docstring for what it does and why."""
        if self._session is None:
            raise SessionError("Cannot speak a reply outside an active session.")
        self._session.last_activity_at = datetime.now(UTC)
        self._state = SessionState.SPEAKING
        try:
            self._tts.speak(text, voice_id, on_audio_ready=on_audio_ready)
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
            if self._stop_listening.is_set():
                return
            if audio is None:
                # Sprint 6.18 (Stress & Recovery Testing) hardening: a
                # None here (distinct from the stop_listening case just
                # above) means _capture_one_utterance()'s own safety cap
                # fired on pure silence — no real speech was ever heard,
                # so there is no utterance to process. Loop back and keep
                # listening rather than treating this as a completed turn
                # — see _capture_one_utterance()'s own docstring for the
                # real livelock this closes.
                continue

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
        was stopped mid-capture (session ending), or if the safety cap
        fires without any real speech ever detected (has_spoken stays
        False) — pure ambient silence, nothing to transcribe.

        Sprint 6.18 (Stress & Recovery Testing) hardening: this second
        None case is a real, found-directly fix, not a defensive
        addition — before it, a pure-silence capture still returned the
        (all-silent) buffered frames, which _on_utterance_ready() then
        unconditionally treated as real activity (refreshing
        session.last_activity_at) and routed through a full phantom
        empty-transcript turn. Because _session_loop() re-enters this
        method immediately after every turn for as long as the session
        stays active, a session with no further real speech coming in
        (the exact shape of every tests/system/ scenario driving a
        single turn, and — per this project's own already-disclosed
        backlog item 9 — a real, reachable production shape too, since
        WhisperSpeechToText already produces empty transcripts for
        near-silent real audio) re-stamped last_activity_at roughly
        every max_utterance_seconds forever, making _watchdog_loop()'s
        own session_timeout_seconds idle threshold structurally
        unreachable — a real livelock, not merely a slow path. Callers
        must not conflate this return with the stop_listening case
        above — see _session_loop()'s own two now-separate checks."""
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
                if not has_spoken:
                    logger.debug(
                        "Utterance capture hit max_utterance_seconds with no speech "
                        "detected; treating as ambient silence, not a phantom turn."
                    )
                    return None
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

        session.last_activity_at = datetime.now(UTC)
        self._last_transcription_result = result
        if self._awaiting_external_reply:
            # A confirmation reply, not a normal conversation turn —
            # doesn't count toward turn_count, and is routed to
            # capture_and_transcribe_reply()'s own waiting caller
            # instead of on_turn_complete. See that method's docstring.
            self._pending_reply_text = result.text
            self._pending_reply_event.set()
            return

        session.turn_count += 1
        self._on_turn_complete(result.text, session.session_id)
