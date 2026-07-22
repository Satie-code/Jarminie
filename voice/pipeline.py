"""Communication Pipeline — wires every Level 2 (Communication) module
built across Sprints 2.1-2.11, plus Level 3's Decision Engine
(Sprints 3.1-3.11), into one real, end-to-end conversation loop: wake
phrase -> listening -> transcription -> Decision Engine pipeline ->
persona selection -> reply composition -> persistence -> spoken reply ->
back to Quiet Mode.

This class owns *only* wiring — no new business logic, no new state
beyond what wiring requires (Single Responsibility, matching every prior
Level 2/3 sprint's own discipline). See docs/sprint_book/sprint_2_12.md,
sprint_3_12.md (Decision Engine Integration), and sprint_3_13.md (Error
Handling & Recovery Hardening — the Decision Engine pipeline call inside
_handle_turn_complete() now has its own narrower exception boundary, see
that method's own docstring).

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
    decision_trace.selected_engine ?
        DEVICE_CONTROL -> _handle_device_control_turn(trace, session_id, persona.name)
            -> ActionRequest(LAUNCH_APPLICATION) -> ActionRegistry.dispatch()
            -> ActionResult -> reply text (Sprint 4.11)
        WORKFLOW -> _handle_workflow_turn(trace, session_id, persona.name)
            -> WorkflowStore lookup by name -> WorkflowExecutor.run()
            -> WorkflowRunResult -> reply text (Sprint 4.11)
        else -> PersonaManager.compose_reply_safely(transcript, context, decision_trace)
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

Sprint 4.11 (Workflow & Device Control Integration) adds two new
terminal branches after the Decision Engine pipeline produces a
DecisionTrace, without restructuring the pipeline itself: when
decision_trace.selected_engine is DEVICE_CONTROL, _handle_device_control_
turn() builds an ActionRequest from the trace's own ContextAnalysis
entities and dispatches it through action_registry — the same
ActionRegistry.dispatch() any other caller uses, never a privileged
bypass; when it is WORKFLOW, _handle_workflow_turn() resolves the named
workflow by name against workflow_store and runs it via
workflow_executor. Both return a plain reply string describing the real
outcome ("Done — I've opened notepad.exe.", "I couldn't find a workflow
named 'X'.", etc.) that flows into the exact same downstream steps every
other reply does — record_turn(), promote_from_turn()/apply_user_
override(), speak_reply() — so persistence and memory promotion behave
identically regardless of which branch produced the reply. This composes
the confirmation text directly in this class rather than through
Persona.compose_reply() (personas/base.py's own signature has no
ActionResult/WorkflowRunResult parameter, and extending it is outside
this sprint's own Files to Modify) — "via the active persona" therefore
means spoken through persona.voice_id (VoiceSessionManager.speak_reply()),
not literally through Persona.compose_reply().
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.logging_setup import get_logger
from decision.authority import AuthorityEvaluator, DecisionTrace, EngineSelection
from decision.context_analyzer import ContextAnalyzer
from decision.intent_detector import IntentDetector
from decision.priority_queue import PriorityQueueManager
from device_control.action_engine import (
    ActionContext,
    ActionRegistry,
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)
from memory.confidence_scorer import ConfidenceScorer
from memory.lifecycle_manager import MemoryLifecycleManager
from memory.retrieval_engine import MemoryRetrievalEngine
from memory.short_term_memory import ShortTermMemory
from personas.persona_manager import PersonaManager, SwitchReason
from security.confirmation_service import ConfirmationOutcome
from voice.context_manager import ContextManager, ConversationContext
from voice.conversation_store import ConversationSessionStore, ConversationTurn
from voice.microphone import MicrophoneManager
from voice.quiet_mode import QuietModeController
from voice.session_manager import SessionEndReason, VoiceSessionManager
from voice.wake_word import WakeWordDetector
from workflow.workflow_executor import WorkflowExecutor, WorkflowRunResult
from workflow.workflow_store import WorkflowStore

logger = get_logger(__name__)

_DEVICE_CONTROL_REQUESTED_BY = "voice_turn"
_DEFAULT_EXECUTABLE_EXTENSION = ".exe"
"""Windows-only normalization: a bare application name spoken by the
user ("open notepad") is treated as an executable name with the
platform's own default extension appended when the entity itself has
none — matching this project's Windows-locked tech stack (Part 3). A
name that already looks like a path/filename (contains a dot) is passed
through unchanged."""


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
        action_registry: ActionRegistry,
        workflow_store: WorkflowStore,
        workflow_executor: WorkflowExecutor,
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
        self._action_registry = action_registry
        self._workflow_store = workflow_store
        self._workflow_executor = workflow_executor
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
        of them degrades the same way rather than needing its own catch.

        Sprint 3.13 hardening (scenario f): _run_decision_pipeline() gets
        its OWN, narrower try/except, distinct from the outer one above.
        Every individual stage already fails safe internally (Intent/
        Context degrade to UNKNOWN/neutral, Chroma failures degrade to
        empty retrieval, Authority Evaluator itself now fails safe-down
        per scenario e) — this inner catch is for whatever isn't already
        covered by one of those (an unexpected bug in any stage). Before
        this hardening, such a failure fell through to the outer catch,
        which ends the whole session (SessionEndReason.ERROR) — coarser
        than necessary, since the rest of a turn (persona reply,
        persistence, spoken response) can still proceed just fine without
        a DecisionTrace. Catching it here instead degrades to
        decision_trace=None and lets the turn finish normally — exactly
        the case Persona.compose_reply()'s decision_trace: DecisionTrace
        | None signature (Sprint 3.12) was designed to tolerate, and the
        same failure-triggered fallback PersonaManager.select_from_
        context() already documented (Sprint 3.12) for a missing
        ContextAnalysis."""
        try:
            persona_before = self._persona_manager.active_persona()
            context = self._context_manager.current_context(session_id, persona_before.name)

            try:
                decision_trace = self._run_decision_pipeline(transcript, context, session_id)
            except Exception:
                logger.exception(
                    "Decision Engine pipeline failed for this turn; continuing with "
                    "decision_trace=None (a degraded, Level-2-quality reply) rather "
                    "than ending the session."
                )
                decision_trace = None

            explicit = self._persona_manager.detect_explicit_selection(transcript)
            if explicit is not None:
                self._persona_manager.select(explicit, SwitchReason.EXPLICIT_SELECTION)
            else:
                context_analysis = (
                    decision_trace.context_analysis if decision_trace is not None else None
                )
                self._persona_manager.select_from_context(context_analysis, transcript)

            persona = self._persona_manager.active_persona()
            selected_engine = (
                decision_trace.selected_engine if decision_trace is not None else None
            )

            if selected_engine is EngineSelection.DEVICE_CONTROL:
                reply = self._handle_device_control_turn(decision_trace, session_id, persona.name)
            elif selected_engine is EngineSelection.WORKFLOW:
                reply = self._handle_workflow_turn(decision_trace, session_id, persona.name)
            else:
                reply = self._persona_manager.compose_reply_safely(
                    transcript, context, decision_trace
                )

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

    def _handle_device_control_turn(
        self, trace: DecisionTrace, session_id: str, persona_name: str
    ) -> str:
        """Builds a LAUNCH_APPLICATION ActionRequest from trace's own
        ContextAnalysis (the first mentioned entity is the target — the
        same first-entity tie-break AuthorityEvaluator._resolve_action_
        engine() already used to route here) and dispatches it through
        action_registry.dispatch() exactly as any other caller would —
        the full PermissionGate/ActionResourceGate/ActionAuditLog stack
        still applies, no bypass. Deliberately narrow to application
        launch only for this sprint (matching sprint_4_11.md's own
        Acceptance Criteria, which names only "application launch" as
        the concrete verified case) — file/folder/window/command
        routing would need real parameter extraction (source/
        destination, which operation) that a bare entities list cannot
        honestly provide without real NLU, explicitly out of scope per
        this sprint's own Architecture Notes."""
        entities = trace.context_analysis.mentioned_entities
        target = entities[0] if entities else None
        if not target:
            return "I couldn't tell what application to open."

        executable_path = (
            target if "." in target else f"{target}{_DEFAULT_EXECUTABLE_EXTENSION}"
        )
        request = ActionRequest(
            action_type=ActionType.LAUNCH_APPLICATION,
            parameters={"operation": "launch", "executable_path": executable_path},
            context=ActionContext(
                requested_by=_DEVICE_CONTROL_REQUESTED_BY,
                persona_name=persona_name,
                session_id=session_id,
                decision_trace=trace,
            ),
            requested_at=datetime.now(UTC),
        )
        result = self._action_registry.dispatch(request)
        return _describe_action_result(result, executable_path)

    def _handle_workflow_turn(
        self, trace: DecisionTrace, session_id: str, persona_name: str
    ) -> str:
        """Resolves the named workflow (the first mentioned entity) by
        name against workflow_store — real existence/enabled-state
        checking happens here, for real, not in AuthorityEvaluator's own
        routing guess — then runs it via workflow_executor.run(), which
        itself dispatches every step through the same ActionRegistry."""
        entities = trace.context_analysis.mentioned_entities
        spoken_name = entities[0] if entities else None
        if not spoken_name:
            return "I couldn't tell which workflow to run."

        resolved = self._resolve_workflow_by_name(spoken_name)
        if resolved is None:
            return f"I couldn't find a workflow named '{spoken_name}'."
        workflow_id, display_name = resolved

        context = ActionContext(
            requested_by=_DEVICE_CONTROL_REQUESTED_BY,
            persona_name=persona_name,
            session_id=session_id,
            decision_trace=trace,
        )
        run_result = self._workflow_executor.run(workflow_id, context)
        return _describe_workflow_result(run_result, display_name)

    def _resolve_workflow_by_name(self, name: str) -> tuple[str, str] | None:
        """Linear scan over list_all() rather than a new WorkflowStore
        query method — workflow_store.py is outside this sprint's own
        Files to Modify, and max_steps_per_workflow-bounded stores are
        small enough that this is a cheap, honest choice, not a
        performance shortcut that will bite later. Returns the stored
        definition's own (workflow_id, name) — its real, proper-cased
        name, not necessarily the same casing/wording ContextAnalysis
        happened to extract from the spoken transcript — so a spoken
        confirmation names the workflow the way it was actually saved."""
        lowered = name.strip().lower()
        for definition in self._workflow_store.list_all():
            if definition.name.strip().lower() == lowered:
                return definition.workflow_id, definition.name
        return None


def _describe_action_result(result: ActionResult, target: str) -> str:
    """Folds an ActionResult into a plain, spoken confirmation —
    honestly reflecting SUCCEEDED/DENIED/anything-else, never
    optimistic, matching the Explainability Rule applied to a live
    device-control turn."""
    if result.status is ActionStatus.SUCCEEDED:
        return f"Done — I've opened {target}."
    if result.status is ActionStatus.DENIED:
        return f"I'm not able to do that: {result.error_message}"
    return f"That didn't work: {result.error_message}"


def _describe_workflow_result(run_result: WorkflowRunResult, name: str) -> str:
    """Folds a WorkflowRunResult into a plain, spoken confirmation —
    distinguishes a declined/timed-out whole-workflow confirmation, a
    disabled workflow (zero step_results with no confirmation prompt
    either — the only other way to reach zero steps, since a
    nonexistent workflow is already ruled out by the caller's own
    by-name resolution before run() is ever called), a partial run, and
    a full success."""
    if run_result.whole_workflow_confirmation in (
        ConfirmationOutcome.DECLINED,
        ConfirmationOutcome.TIMED_OUT,
    ):
        return f"I didn't run the '{name}' workflow since it wasn't confirmed."
    if not run_result.step_results:
        return f"The '{name}' workflow is currently disabled."
    if run_result.aborted_early:
        return f"I ran part of the '{name}' workflow, but a step failed partway through."
    return f"Done — I've run the '{name}' workflow."
