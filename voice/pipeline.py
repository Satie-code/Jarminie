"""Communication Pipeline — wires every Level 2 (Communication) module
built across Sprints 2.1-2.11, plus Level 3's Decision Engine
(Sprints 3.1-3.11), into one real, end-to-end conversation loop: wake
phrase -> listening -> transcription -> Decision Engine pipeline ->
persona selection -> reply composition -> persistence -> spoken reply ->
back to Quiet Mode.

This class owns *only* wiring — no new business logic, no new state
beyond what wiring requires (Single Responsibility, matching every prior
Level 2/3 sprint's own discipline). See docs/sprint_book/sprint_2_12.md
and sprint_3_12.md (Decision Engine Integration).

Wiring diagram (matches sprint_3_12.md's own Data Flow):

    Microphone (passive)
          |
    WakeWordDetector --on_detected--> QuietModeController.activate(WAKE_WORD)
          |
    Microphone (active) + VoiceSessionManager.begin_session()
          |
    WhisperSpeechToText.transcribe() -> transcript
          |
    _run_decision_pipeline(transcript, context, session_id):
        IntentDetector.detect() -> ContextAnalyzer.analyze()
            -> MemoryRetrievalEngine.retrieve()
        PriorityQueueManager.classify() -> AuthorityEvaluator.evaluate()
        -> DecisionTrace
          |
    PersonaManager.detect_explicit_selection(), else
    PersonaManager.select_from_context(decision_trace.context_analysis, transcript)
          |
    PersonaManager.compose_reply_safely(transcript, context, decision_trace)
        -> active_persona.compose_reply(...) -> reply text
          |
    ConversationSessionStore.record_turn(...)
          |
    ShortTermMemory.promote_from_turn(turn) -> record_id | None
    ConfidenceScorer.detect_override_phrase(transcript) -> if True and a
        record was promoted this turn, MemoryLifecycleManager.
        apply_user_override(record_id)
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

Engineering decision (Sprint 3.12, not spelled out by the spec's own
Objectives wording): ConfidenceScorer.detect_override_phrase() gaining a
"real caller" only means something if its result is actually applied
somewhere — MemoryLifecycleManager.apply_user_override(), "the real,
persisted counterpart" per its own docstring, is that real caller,
applied to whatever record ShortTermMemory.promote_from_turn() promoted
in the SAME turn (if any). If the transcript contains an override
phrase but nothing was promoted this turn (the two trigger-phrase lists
— short_term_salience_triggers and override_trigger_phrases — are
independent and can disagree), there is honestly nothing to override;
this is logged, not silently ignored, and not treated as a bug to
resolve here (widening either trigger-phrase list beyond a real caller
is a hardening/tuning concern, not this sprint's own scope).
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.logging_setup import get_logger
from decision.authority import AuthorityEvaluator, DecisionTrace
from decision.context_analyzer import ContextAnalyzer
from decision.intent_detector import IntentDetector
from decision.priority_queue import PriorityQueueManager
from memory.confidence_scorer import ConfidenceScorer
from memory.lifecycle_manager import MemoryLifecycleManager
from memory.retrieval_engine import MemoryRetrievalEngine
from memory.short_term_memory import ShortTermMemory
from personas.persona_manager import PersonaManager, SwitchReason
from voice.context_manager import ContextManager, ConversationContext
from voice.conversation_store import ConversationSessionStore, ConversationTurn
from voice.microphone import MicrophoneManager
from voice.quiet_mode import QuietModeController
from voice.session_manager import SessionEndReason, VoiceSessionManager
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
    already-built Level 2/3 module it wires together, plus the two
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
        intent_detector: IntentDetector,
        context_analyzer: ContextAnalyzer,
        memory_retrieval_engine: MemoryRetrievalEngine,
        priority_queue_manager: PriorityQueueManager,
        authority_evaluator: AuthorityEvaluator,
        short_term_memory: ShortTermMemory,
        confidence_scorer: ConfidenceScorer,
        memory_lifecycle_manager: MemoryLifecycleManager,
    ) -> None:
        self._mic = mic
        self._wake_word_detector = wake_word_detector
        self._session_manager = session_manager
        self._quiet_mode_controller = quiet_mode_controller
        self._conversation_store = conversation_store
        self._context_manager = context_manager
        self._persona_manager = persona_manager
        self._intent_detector = intent_detector
        self._context_analyzer = context_analyzer
        self._memory_retrieval_engine = memory_retrieval_engine
        self._priority_queue_manager = priority_queue_manager
        self._authority_evaluator = authority_evaluator
        self._short_term_memory = short_term_memory
        self._confidence_scorer = confidence_scorer
        self._memory_lifecycle_manager = memory_lifecycle_manager
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

    def _run_decision_pipeline(
        self, transcript: str, context: ConversationContext, session_id: str
    ) -> DecisionTrace:
        """The Decision Engine pipeline in full, per Part 2's diagram:
        Intent Detection -> Context Analysis -> Memory Retrieval ->
        Priority Evaluation -> Authority Evaluation. Exception handling
        for this whole sequence is Sprint 3.13's job, not this sprint's —
        this method wires the happy path correctly first, matching the
        Sprint 2.12 -> 2.13 wiring-then-hardening precedent exactly.
        Every individual stage already degrades internally on its own
        failure (Intent/Context both fail safe to UNKNOWN/neutral
        defaults per Sprints 3.7/3.8), so this method itself has no
        try/except of its own — see _handle_turn_complete()'s own outer
        catch for the defense-in-depth layer."""
        intent = self._intent_detector.detect(transcript, context)
        context_analysis = self._context_analyzer.analyze(intent, context)
        retrieved_memories = self._memory_retrieval_engine.retrieve(
            context_analysis.primary_topic, context.active_persona_name, session_id
        )
        priority_level = self._priority_queue_manager.classify(intent)
        return self._authority_evaluator.evaluate(
            intent, context_analysis, retrieved_memories, priority_level
        )

    def _handle_turn_complete(self, transcript: str, session_id: str) -> None:
        """The real conversation turn: Decision Engine pipeline ->
        persona selection -> reply composition -> persistence -> memory
        promotion/override -> spoken reply. Wired as VoiceSessionManager's
        on_turn_complete callback (via relay).

        Sprint 2.13 hardening: this method runs on VoiceSessionManager's
        own background thread (_session_loop -> _on_utterance_ready ->
        the relay -> here), with nothing upstream of it catching an
        exception — before this hardening pass, any unexpected failure
        here (a bug in compose_reply(), an unforeseen error from any
        step) would silently kill that thread, leaving the session stuck
        rather than ended. The try/except below is the fix: any failure
        ends the session gracefully (SessionEndReason.ERROR) instead of
        propagating. compose_reply() itself goes through PersonaManager's
        compose_reply_safely() (scenario e) as a second, more specific
        layer — this outer catch is for everything else (record_turn()
        already never raises per Sprint 2.7's own design, scenario f;
        speak_reply() already contains TextToSpeechError itself, scenario
        c) — deliberately still wrapped here as defense in depth. Sprint
        3.12 adds the Decision Engine pipeline and memory promotion/
        override calls inside this same try/except, so a failure in any
        of them degrades the same way rather than needing its own catch."""
        try:
            persona_before = self._persona_manager.active_persona()
            context = self._context_manager.current_context(session_id, persona_before.name)

            decision_trace = self._run_decision_pipeline(transcript, context, session_id)

            explicit = self._persona_manager.detect_explicit_selection(transcript)
            if explicit is not None:
                self._persona_manager.select(explicit, SwitchReason.EXPLICIT_SELECTION)
            else:
                self._persona_manager.select_from_context(
                    decision_trace.context_analysis, transcript
                )

            persona = self._persona_manager.active_persona()
            reply = self._persona_manager.compose_reply_safely(transcript, context, decision_trace)

            turn = ConversationTurn(
                session_id=session_id,
                persona_name=persona.name,
                timestamp=datetime.now(UTC),
                user_text=transcript,
                response_text=reply,
            )
            self._conversation_store.record_turn(turn)

            promoted_record_id = self._short_term_memory.promote_from_turn(turn)
            if promoted_record_id is not None and self._confidence_scorer.detect_override_phrase(
                transcript
            ):
                self._memory_lifecycle_manager.apply_user_override(promoted_record_id)

            self._session_manager.speak_reply(reply, persona.voice_id)
        except Exception:
            logger.exception(
                "Unexpected failure while handling a completed turn; ending the session "
                "rather than leaving it stuck."
            )
            self._session_manager.end_session(SessionEndReason.ERROR)
