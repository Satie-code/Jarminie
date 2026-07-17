"""Quiet Mode Controller — single source of truth for whether JARMINEI is
dormant or actively listening/conversing.

Wake Word Detector (2.2) owns the *mechanism* of detecting a phrase;
Microphone Manager (2.1) owns the *mechanism* of switching capture modes.
Neither owns the *policy* of what those events mean at the system level —
that policy lives here, keeping Single Responsibility intact rather than
letting dormant/active state logic leak into either lower-level module.
See docs/sprint_book/sprint_2_6.md.

Part 2's full activation-priority list (02_System_Architecture.md),
highest priority first, exactly as ActivationReason orders its members:

1. Critical emergency — reserved for Level 3's Authority System (Sprint
   3.10); no caller exists yet, not wired.
2. Explicit user selection — NOT a Quiet Mode concern; this is Persona
   Switching (Sprint 2.11), which operates *within* an already-active
   session rather than causing a dormant-to-active transition.
3. Context detection — out of scope; no context-detection subsystem
   exists yet.
4. Daily routine — reserved for Level 4's Scheduler; no caller exists
   yet, not wired.

Only the wake-phrase trigger (ActivationReason.WAKE_WORD) has a real
caller in Level 2. The other reasons are named now so the state machine
doesn't need reshaping later, but each is explicitly unwired, not
implemented.

Wiring note: WakeWordDetector.on_detected and VoiceSessionManager's
on_session_ended are both plain callables fixed at *their own*
construction time (03_Engineering_Standards.md's Dependency Injection
rule) — this sprint's Files to Modify is deliberately empty, so neither
gains a post-construction setter. The actual Python-level wiring (passing
this controller's _on_wake_word_detected/_on_session_ended bound methods
into those constructors) happens where WakeWordDetector and
VoiceSessionManager are themselves assembled — Sprint 2.12 (Communication
Pipeline Integration), which owns all such main.py/CoreManager wiring by
design. What start()/stop() control here is whether this controller reacts
to those callbacks at all: a callback firing while stopped is logged and
ignored rather than transitioning state, so "start() attaches / stop()
detaches" holds even though the callable references themselves exist for
the controller's whole lifetime.
"""

from enum import Enum

from core.logging_setup import get_logger
from voice.session_manager import SessionEndReason, VoiceSessionManager

logger = get_logger(__name__)


class OperatingMode(Enum):
    DORMANT = "dormant"
    ACTIVE = "active"


class ActivationReason(Enum):
    """Ordered to mirror Part 2's stated activation priority (critical
    emergency first), even though only WAKE_WORD has a real caller in
    Level 2 — see this module's docstring."""

    EXPLICIT_EMERGENCY = "explicit_emergency"
    WAKE_WORD = "wake_word"
    SCHEDULED_ALERT = "scheduled_alert"


class QuietModeController:
    """Holds the single source of truth for OperatingMode and enforces the
    Microphone Rule structurally: the only path from DORMANT to ACTIVE is a
    successful wake-word detection (in Level 2); the only path back is a
    Voice Session Manager session-end event.

    Constructor DI per 03_Engineering_Standards.md: receives the
    VoiceSessionManager it depends on rather than constructing it itself.
    """

    def __init__(self, session_manager: VoiceSessionManager) -> None:
        self._session_manager = session_manager
        self._mode = OperatingMode.DORMANT
        self._started = False

    def start(self) -> None:
        """Begin reacting to wake-word/session-end callbacks. Mode starts
        (or remains) DORMANT — this method does not itself trigger
        activation."""
        self._started = True
        logger.info("Quiet Mode Controller started (mode=%s).", self._mode.value)

    def stop(self) -> None:
        """Stop reacting to callbacks. Does not force an ACTIVE session to
        end — VoiceSessionManager.stop() already owns ending its own active
        session on shutdown."""
        self._started = False
        logger.info("Quiet Mode Controller stopped.")

    def health_check(self) -> bool:
        """Healthy iff started AND the mode is consistent with whether a
        session is actually running (e.g. ACTIVE with no running session,
        or DORMANT with one still running, both indicate a bug)."""
        if not self._started:
            return False
        session_active = self._session_manager.is_active()
        if self._mode is OperatingMode.ACTIVE and not session_active:
            return False
        if self._mode is OperatingMode.DORMANT and session_active:
            return False
        return True

    def current_mode(self) -> OperatingMode:
        return self._mode

    def activate(self, reason: ActivationReason) -> None:
        """Transition DORMANT -> ACTIVE and begin a voice session. A no-op
        (logged) if already ACTIVE — activations cannot stack, matching
        "only one session at a time"."""
        if self._mode is OperatingMode.ACTIVE:
            logger.info("activate(%s) ignored — already ACTIVE.", reason.value)
            return
        self._mode = OperatingMode.ACTIVE
        logger.info("Activating (%s): DORMANT -> ACTIVE.", reason.value)
        self._session_manager.begin_session()

    def deactivate(self) -> None:
        """Transition ACTIVE -> DORMANT. Called internally when the wired
        on_session_ended callback fires."""
        if self._mode is OperatingMode.DORMANT:
            return
        self._mode = OperatingMode.DORMANT
        logger.info("Deactivating: ACTIVE -> DORMANT.")

    def _on_wake_word_detected(self, phrase: str) -> None:
        """Wired as WakeWordDetector's on_detected callback (Sprint 2.12).
        Ignored (logged) while the controller isn't started."""
        if not self._started:
            logger.warning(
                "Wake word '%s' detected while Quiet Mode Controller not started; ignoring.",
                phrase,
            )
            return
        logger.info("Wake word detected: %s", phrase)
        self.activate(ActivationReason.WAKE_WORD)

    def _on_session_ended(self, reason: SessionEndReason) -> None:
        """Wired as VoiceSessionManager's on_session_ended callback
        (Sprint 2.12). Ignored while the controller isn't started."""
        if not self._started:
            return
        logger.info("Session ended (%s); returning to DORMANT.", reason.value)
        self.deactivate()
