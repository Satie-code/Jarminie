"""Communication Pipeline — wires every Level 2 (Communication) module
built across Sprints 2.1-2.11 into one real, end-to-end conversation
loop: wake phrase -> listening -> transcription -> persona selection ->
reply composition -> persistence -> spoken reply -> back to Quiet Mode.

This class owns *only* wiring — no new business logic, no new state
beyond what wiring requires (Single Responsibility, matching every prior
Level 2 sprint's own discipline). See docs/sprint_book/sprint_2_12.md.

Wiring diagram (matches the sprint file's own Data Flow):

    Microphone (passive)
          |
    WakeWordDetector --on_detected--> QuietModeController.activate(WAKE_WORD)
          |
    Microphone (active) + VoiceSessionManager.begin_session()
          |
    WhisperSpeechToText.transcribe() -> transcript
          |
    PersonaManager.detect_explicit_selection / detect_context_heuristic -> select()
          |
    ContextManager.current_context()
          |
    active_persona.compose_reply(transcript, context) -> reply text
          |
    ConversationSessionStore.record_turn(...)
          |
    VoiceSessionManager.speak_reply(reply, persona.voice_id) -> CoquiTextToSpeech.speak()
          |
    (silence timeout) -> end_session() -> QuietModeController.deactivate()
          |
    Microphone (passive) -- back to Quiet Mode

Resolving a real circular-construction problem (a call this sprint's own
spec left implicit, not literally addressed): WakeWordDetector.on_detected
and VoiceSessionManager.on_turn_complete/on_session_ended are all fixed at
*their own* constructor time (Sprint 2.2/2.5's design, unchanged by this
sprint's own empty "Files to Modify" for those files). WakeWordDetector's
target (QuietModeController) can be, and is, constructed first in the
composition root (main.py), so it needs no indirection. But
VoiceSessionManager must be constructed before QuietModeController (whose
own constructor needs a built VoiceSessionManager) and long before this
class (whose constructor needs a built QuietModeController) — so
on_turn_complete's real target (this class's own _handle_turn_complete)
and on_session_ended's real target (QuietModeController._on_session_ended)
cannot exist yet when VoiceSessionManager is constructed. CallbackRelay
resolves this: main.py passes a relay in VoiceSessionManager's constructor
in place of the real target; this class's start() points each relay at
its real target once the full graph exists, and stop() clears it again —
which is also what makes health_check()'s "each wired callback still
points where expected" a real, checkable claim rather than an assumption.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.logging_setup import get_logger
from personas.persona_manager import PersonaManager, SwitchReason
from voice.context_manager import ContextManager
from voice.conversation_store import ConversationSessionStore, ConversationTurn
from voice.microphone import MicrophoneManager
from voice.quiet_mode import QuietModeController
from voice.session_manager import VoiceSessionManager
from voice.wake_word import WakeWordDetector

logger = get_logger(__name__)


class CallbackRelay:
    """A composition-root indirection for a callback whose real target is
    constructed after the callable itself must already exist — see this
    module's docstring. Invoking it before wiring is established is
    logged and ignored rather than raised, since no real caller can reach
    that state once CoreManager.startup() has run start() on every
    registered module in order."""

    def __init__(self) -> None:
        self.target: Callable[..., None] | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        if self.target is None:
            logger.warning("CallbackRelay invoked before wiring was established; ignoring.")
            return
        self.target(*args, **kwargs)


class CommunicationPipeline:
    """Constructor DI per 03_Engineering_Standards.md: receives every
    already-built Level 2 module it wires together, plus the two
    CallbackRelay instances main.py threaded through VoiceSessionManager's
    constructor in place of this class's own (not-yet-existing) methods.
    """

    def __init__(
        self,
        mic: MicrophoneManager,
        wake_word_detector: WakeWordDetector,
        session_manager: VoiceSessionManager,
        quiet_mode_controller: QuietModeController,
        conversation_store: ConversationSessionStore,
        context_manager: ContextManager,
        persona_manager: PersonaManager,
        turn_complete_relay: CallbackRelay,
        session_ended_relay: CallbackRelay,
    ) -> None:
        self._mic = mic
        self._wake_word_detector = wake_word_detector
        self._session_manager = session_manager
        self._quiet_mode_controller = quiet_mode_controller
        self._conversation_store = conversation_store
        self._context_manager = context_manager
        self._persona_manager = persona_manager
        self._turn_complete_relay = turn_complete_relay
        self._session_ended_relay = session_ended_relay
        self._wired = False

    def start(self) -> None:
        """Connect the callback chain: point both relays at their real
        targets. WakeWordDetector.on_detected needs no relay — it already
        points directly at quiet_mode_controller._on_wake_word_detected,
        wired at construction time in main.py."""
        self._turn_complete_relay.target = self._handle_turn_complete
        self._session_ended_relay.target = self._quiet_mode_controller._on_session_ended
        self._wired = True
        logger.info("Communication Pipeline wiring connected.")

    def stop(self) -> None:
        """Disconnect the callback chain."""
        self._turn_complete_relay.target = None
        self._session_ended_relay.target = None
        self._wired = False
        logger.info("Communication Pipeline wiring disconnected.")

    def health_check(self) -> bool:
        """Deliberately shallow: confirms the wiring itself is intact
        (each relay still points where expected) — each individual
        module's own health_check() already covers its internal
        correctness."""
        return (
            self._wired
            and self._turn_complete_relay.target == self._handle_turn_complete
            and self._session_ended_relay.target == self._quiet_mode_controller._on_session_ended
        )

    def _handle_turn_complete(self, transcript: str, session_id: str) -> None:
        """The real conversation turn: persona selection -> context ->
        reply composition -> persistence -> spoken reply. Wired as
        VoiceSessionManager's on_turn_complete callback (via relay)."""
        explicit = self._persona_manager.detect_explicit_selection(transcript)
        if explicit is not None:
            self._persona_manager.select(explicit, SwitchReason.EXPLICIT_SELECTION)
        else:
            heuristic = self._persona_manager.detect_context_heuristic(transcript)
            if heuristic is not None:
                self._persona_manager.select(heuristic, SwitchReason.CONTEXT_DETECTION)

        persona = self._persona_manager.active_persona()
        context = self._context_manager.current_context(session_id, persona.name)
        reply = persona.compose_reply(transcript, context)

        self._conversation_store.record_turn(
            ConversationTurn(
                session_id=session_id,
                persona_name=persona.name,
                timestamp=datetime.now(UTC),
                user_text=transcript,
                response_text=reply,
            )
        )
        self._session_manager.speak_reply(reply, persona.voice_id)
