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
        SCHEDULER -> _handle_scheduler_turn(trace)
            -> parse a resolvable relative time from the transcript
            -> CalendarStore.save(ScheduledItem) -> reply text (Sprint 4.18)
        INTERNET_AGENT -> _handle_internet_agent_turn(trace)
            -> ResearchEngine.research() -> SourceValidator.validate()
            -> Summarizer.summarize() -> reply text (Sprint 4.18)
        else -> _compose_conversational_reply(transcript, context, decision_trace, persona.name)
            -> ResponseGenerator.generate(...) -> a real, persona-toned,
               memory-grounded reply -> reply text; degrades to
               PersonaManager.compose_reply_safely(...) (the Level 2
               templated acknowledgement) only on an empty transcript or
               an LlmError -- see _compose_conversational_reply()'s own
               docstring. This is the real Response Generation stage
               02_System_Architecture.md's own pipeline diagram names,
               reversing Sprint 3.12's original "compose_reply() IS
               Response Generation" decision at the user's explicit
               request (docs/changelog/0.4.2-conversational-response-
               generation.md).
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

Sprint 4.18 (Scheduler & Internet Agent Integration) adds a SECOND,
entirely independent wiring diagram — this project's first genuinely
PROACTIVE (JARMINEI-initiated, not turn-triggered) behavior, registered
as a TaskScheduler job from start() rather than triggered by any
conversation turn:

    (background, every scheduler_config.poll_interval_seconds)
    _check_and_announce_due_reminder():
        QuietModeController.current_mode() is DORMANT?  -- no -> return
        (a live session is active; Part 2's own "Queued" language for
        Scheduled Reminders means this due item simply waits for the
        next poll, it never interrupts)
          | yes
        PriorityQueueManager.peek_next() names a SCHEDULED_REMINDER? -- no -> return
          | yes
        PriorityQueueManager.pop_next() -> ScheduledItem
          |
        QuietModeController.activate(SCHEDULED_ALERT,
            announce_first=(item.title, persona.voice_id))
            -> VoiceSessionManager.begin_session(announce_first=...)
               speaks the reminder BEFORE utterance capture starts,
               then re-arms listening exactly like any other session
               (see voice/session_manager.py's own docstring for why
               that ordering matters)

start() also registers four more TaskScheduler jobs, closing
backlog/technical_debt.md items 11/15's still-open recurring-cadence
half for the first time in this project's history (each was
previously only invoked once, at its own module's start()):
ReminderEngine.register() (its own due-item poll, Sprint 4.15),
MemoryLifecycleManager.run_cleanup_pass()/run_monthly_review(), and
ConversationSessionStore.purge_older_than()/ActionAuditLog.
purge_older_than() (both zero-arg-callable via their own configured-
retention defaults) — all on scheduler_config.maintenance_interval_
seconds. See this class's own start()/stop() for the exact job_ids.

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

Sprint 5.14 (Presentation Layer Integration) wires the entire Level 5
Part A graph (Sprints 5.1-5.13) into this same per-turn flow, in
_handle_turn_complete()'s own existing shape, without restructuring it:

    _run_decision_pipeline()  (existing, unchanged)
          |
    _run_presentation_pipeline(context, context_analysis)  <-- NEW
          | EmotionDetectionEngine.collect_signals()/.estimate() (5.1)
          | EmotionalStateManager.decay_toward_baseline()/.apply_estimate() (5.2)
          | EmotionalMemory.record_significant_moment() (5.3, conditional)
          | PresentationController.refresh() -> mounted Renderer.render_state() (5.6)
          | AdaptiveWorkspaceController.select_profile()/.should_switch() (5.12, Jarvis-only)
          | GestureEngine.trigger_event(TURN_END, ...) (5.9)
          |
    persona selection (existing) -- on_switch now really fires
          | TransitionEngine.transition() (5.10), via PersonaManager's on_switch
          |
    reply composed (existing four branches, PLUS new EMOTION_SUPPORT
    branch: compose_reply_safely(..., emotional_state) directly, since
    EMOTION_SUPPORT selects a tone, not a subsystem — decision/authority.py's
    own docstring)
          |
    record_turn() / promote_from_turn() / apply_user_override() (existing, unchanged)
          |
    VoicePersonalityModulator.shape_pacing(reply, voice_warmth) (5.11)
          |
    speak_reply(paced_reply, persona.voice_id, on_audio_ready=...) --
        on_audio_ready drives LipSyncDriver.drive_from_audio() (5.11)
        alongside playback whenever Minie's AvatarRenderer is mounted
          |
    real per-phase JarvisRenderer.apply_turn_phase() calls (THINKING at
    turn start, SPEAKING before speak_reply(), LISTENING after) close
    the ring-state granularity gap Sprint 5.7 named explicitly, threading
    voice/session_manager.py's own real SessionState through without
    adding new state to that module (see current_session_state()'s own
    docstring there)

Separately, a new session's own first turn checks CompanionExperienceEngine
(5.13) for a greeting/celebration moment (_maybe_prepare_companion_moment()),
folding its content into that turn's own reply as a plain-text prefix —
Persona.compose_reply()'s own signature is outside this sprint's Files to
Modify, so phrasing happens here rather than through a persona template;
a disclosed, narrower implementation of the Sprint Book's own "folded
into the next reply's own content input" language, not a silent gap.

CommunicationPipeline gains twelve new constructor dependencies for all
of this — every one an already-built Level 5 Part A class from Sprints
5.1-5.13, wired for the first time here, per this sprint's own "no new
architecture, real work is threading the callers" Engineering Rationale.
"""

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from config.schema import MemoryConfig, SchedulerConfig
from core.logging_setup import get_logger
from decision.authority import AuthorityEvaluator, DecisionTrace, EngineSelection
from decision.context_analyzer import ContextAnalysis, ContextAnalyzer
from decision.intent_detector import IntentDetector
from decision.llm_client import LlmError
from decision.priority_queue import PriorityLevel, PriorityQueueManager
from decision.response_generator import ResponseGenerator
from device_control.action_engine import (
    ActionContext,
    ActionRegistry,
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)
from device_control.action_log import ActionAuditLog
from emotion.detection_engine import EmotionDetectionEngine
from emotion.state_manager import EmotionalStateManager
from internet.research_engine import ResearchEngine
from internet.source_validator import SourceValidator
from internet.summarizer import Summarizer
from memory.confidence_scorer import ConfidenceScorer
from memory.emotional_memory import EmotionalMemory, _score_significance
from memory.lifecycle_manager import MemoryLifecycleManager
from memory.models import MemoryType
from memory.retrieval_engine import MemoryRetrievalEngine
from memory.short_term_memory import ShortTermMemory
from personas.persona_manager import PersonaManager, SwitchReason
from presentation.adaptive_workspace import AdaptiveWorkspaceController, WorkspaceProfile
from presentation.avatar_renderer import AvatarRenderer
from presentation.companion_experience import (
    CompanionExperienceEngine,
    CompanionMoment,
    CompanionMomentType,
)
from presentation.gesture_engine import GestureEngine, GestureTrigger
from presentation.jarvis_renderer import JarvisRenderer
from presentation.lip_sync import LipSyncDriver
from presentation.presentation_controller import PresentationController
from presentation.voice_personality import VoicePersonalityModulator
from presentation.widgets.segmented_ring_widget import RingState
from scheduler.calendar_store import CalendarStore
from scheduler.reminder_engine import ReminderEngine
from scheduler.scheduler_model import ItemType, ScheduledItem
from scheduler.task_scheduler import TaskScheduler
from security.confirmation_service import ConfirmationOutcome
from voice.context_manager import ContextManager, ConversationContext
from voice.conversation_store import ConversationSessionStore, ConversationTurn
from voice.microphone import MicrophoneManager
from voice.quiet_mode import ActivationReason, OperatingMode, QuietModeController
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

_RELATIVE_TIME_PATTERN = re.compile(
    r"in\s+(\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs)\b", re.IGNORECASE
)
"""The REAL relative-time parser (Sprint 4.18) — computes the actual
timestamp, distinct from decision/authority.py's own
_RELATIVE_TIME_HINT_PATTERN, which only checks presence for routing
purposes. Deliberately duplicated rather than shared/imported: routing
is cheap and lives in the Decision Engine's own dependency-light
module; real resolution happens here, downstream, the same split
_resolve_action_engine()'s own docstring already established for
DEVICE_CONTROL/WORKFLOW."""

_MAINTENANCE_JOB_IDS: tuple[str, ...] = (
    "memory_lifecycle_cleanup_pass",
    "memory_lifecycle_monthly_review",
    "conversation_store_purge",
    "action_audit_log_purge",
)
_REMINDER_ANNOUNCEMENT_JOB_ID = "proactive_reminder_announcement"


def _parse_relative_time(transcript: str, now: datetime) -> datetime | None:
    """Deliberately narrow, matching this sprint's own Architecture
    Notes: only "in N minutes"/"in N hours" phrasing resolves — no
    absolute date/time parsing ("tomorrow at 5pm") exists. Returns None
    (never raises) when nothing resolvable is found."""
    match = _RELATIVE_TIME_PATTERN.search(transcript)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    delta = timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount)
    return now + delta


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
        response_generator: ResponseGenerator,
        memory_retrieval_engine: MemoryRetrievalEngine,
        priority_queue_manager: PriorityQueueManager,
        authority_evaluator: AuthorityEvaluator,
        short_term_memory: ShortTermMemory,
        confidence_scorer: ConfidenceScorer,
        memory_lifecycle_manager: MemoryLifecycleManager,
        action_registry: ActionRegistry,
        workflow_store: WorkflowStore,
        workflow_executor: WorkflowExecutor,
        task_scheduler: TaskScheduler,
        calendar_store: CalendarStore,
        reminder_engine: ReminderEngine,
        research_engine: ResearchEngine,
        source_validator: SourceValidator,
        summarizer: Summarizer,
        action_audit_log: ActionAuditLog,
        scheduler_config: SchedulerConfig,
        memory_config: MemoryConfig,
        emotion_detection_engine: EmotionDetectionEngine,
        emotional_state_manager: EmotionalStateManager,
        emotional_memory: EmotionalMemory,
        presentation_controller: PresentationController,
        adaptive_workspace_controller: AdaptiveWorkspaceController,
        gesture_engine: GestureEngine,
        voice_personality_modulator: VoicePersonalityModulator,
        lip_sync_driver: LipSyncDriver,
        companion_experience_engine: CompanionExperienceEngine,
        jarvis_renderer: JarvisRenderer,
        avatar_renderer: AvatarRenderer,
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
        self._response_generator = response_generator
        self._memory_retrieval_engine = memory_retrieval_engine
        self._priority_queue_manager = priority_queue_manager
        self._authority_evaluator = authority_evaluator
        self._short_term_memory = short_term_memory
        self._confidence_scorer = confidence_scorer
        self._memory_lifecycle_manager = memory_lifecycle_manager
        self._action_registry = action_registry
        self._workflow_store = workflow_store
        self._workflow_executor = workflow_executor
        self._task_scheduler = task_scheduler
        self._calendar_store = calendar_store
        self._reminder_engine = reminder_engine
        self._research_engine = research_engine
        self._source_validator = source_validator
        self._summarizer = summarizer
        self._action_audit_log = action_audit_log
        self._scheduler_config = scheduler_config
        self._turn_complete_relay = turn_complete_relay
        self._session_ended_relay = session_ended_relay
        self._memory_config = memory_config
        self._emotion_detection_engine = emotion_detection_engine
        self._emotional_state_manager = emotional_state_manager
        self._emotional_memory = emotional_memory
        self._presentation_controller = presentation_controller
        self._adaptive_workspace_controller = adaptive_workspace_controller
        self._gesture_engine = gesture_engine
        self._voice_personality_modulator = voice_personality_modulator
        self._lip_sync_driver = lip_sync_driver
        self._companion_experience_engine = companion_experience_engine
        self._jarvis_renderer = jarvis_renderer
        self._avatar_renderer = avatar_renderer
        self._wired = False

        # Sprint 5.14's own new, genuinely-this-sprint's-own state (Sprint
        # 5.12's AdaptiveWorkspaceController.should_switch() deliberately
        # leaves ownership of the running debounce count to the
        # integration sprint — see that module's own docstring):
        self._current_workspace_profile = WorkspaceProfile.GENERAL
        self._pending_workspace_candidate: WorkspaceProfile | None = None
        self._workspace_consecutive_match_count = 0

        # A session_id is added here on its own first turn only — see
        # _maybe_prepare_companion_moment()'s own docstring.
        self._greeted_session_ids: set[str] = set()

        # EmotionalStateManager.decay_toward_baseline() needs the real
        # elapsed time since the previous turn; None on the very first
        # turn this process has ever handled (decay_toward_baseline()
        # itself treats a zero/negative elapsed_seconds as a no-op).
        self._last_emotion_update_at: datetime | None = None

    def start(self) -> None:
        """Connect the callback chain: point both relays at their real
        targets. WakeWordDetector.on_detected needs no relay — it already
        points directly at quiet_mode_controller._on_wake_word_detected,
        wired at construction time in main.py.

        Sprint 4.18: also registers every Level 4 Part B TaskScheduler
        job — ReminderEngine's own due-item poll, the three periodic
        maintenance passes, and the proactive-announcement idle-check.
        This REQUIRES task_scheduler to already be started (main.py's
        own registration order puts task_scheduler before
        communication_pipeline specifically so this holds — see
        main.py's own docstring for the full reasoning); calling
        add_job() before TaskScheduler.start() has run raises
        RuntimeError, which would surface immediately as a real
        CoreManager module-start failure, not a silent no-op."""
        self._turn_complete_relay.target = self._handle_turn_complete
        self._session_ended_relay.target = self._quiet_mode_controller._on_session_ended
        self._wired = True

        self._reminder_engine.register()
        self._task_scheduler.add_job(
            self._memory_lifecycle_manager.run_cleanup_pass,
            self._scheduler_config.maintenance_interval_seconds,
            job_id=_MAINTENANCE_JOB_IDS[0],
        )
        self._task_scheduler.add_job(
            self._memory_lifecycle_manager.run_monthly_review,
            self._scheduler_config.maintenance_interval_seconds,
            job_id=_MAINTENANCE_JOB_IDS[1],
        )
        self._task_scheduler.add_job(
            self._conversation_store.purge_older_than,
            self._scheduler_config.maintenance_interval_seconds,
            job_id=_MAINTENANCE_JOB_IDS[2],
        )
        self._task_scheduler.add_job(
            self._action_audit_log.purge_older_than,
            self._scheduler_config.maintenance_interval_seconds,
            job_id=_MAINTENANCE_JOB_IDS[3],
        )
        self._task_scheduler.add_job(
            self._check_and_announce_due_reminder,
            self._scheduler_config.poll_interval_seconds,
            job_id=_REMINDER_ANNOUNCEMENT_JOB_ID,
        )
        logger.info("Communication Pipeline wiring connected.")

    def stop(self) -> None:
        """Disconnect the callback chain and every TaskScheduler job
        registered in start(). Assumes task_scheduler is still running
        at this point — main.py's reverse-shutdown-order guarantee
        (task_scheduler registered/started before communication_pipeline
        means it stops AFTER communication_pipeline) keeps this true in
        real operation; see main.py's own docstring."""
        self._task_scheduler.remove_job(_REMINDER_ANNOUNCEMENT_JOB_ID)
        for job_id in _MAINTENANCE_JOB_IDS:
            self._task_scheduler.remove_job(job_id)
        self._reminder_engine.unregister()

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
        ContextAnalysis.

        Sprint 5.14: _run_presentation_pipeline() runs in its own narrow
        exception boundary too (same reasoning as _run_decision_pipeline()'s
        above — a presentation failure must degrade to "doesn't update
        this turn," never abort the spoken reply). _apply_turn_phase()
        calls thread real turn-phase signals into JarvisRenderer at the
        three real transition points this method already has: THINKING
        at turn start, SPEAKING immediately before speak_reply(), LISTENING
        immediately after (see this module's own docstring)."""
        try:
            persona_before = self._persona_manager.active_persona()
            context = self._context_manager.current_context(session_id, persona_before.name)
            self._apply_turn_phase(RingState.THINKING)
            companion_moment = self._maybe_prepare_companion_moment(context, session_id)

            try:
                decision_trace = self._run_decision_pipeline(transcript, context, session_id)
            except Exception:
                logger.exception(
                    "Decision Engine pipeline failed for this turn; continuing with "
                    "decision_trace=None (a degraded, Level-2-quality reply) rather "
                    "than ending the session."
                )
                decision_trace = None

            context_analysis = (
                decision_trace.context_analysis if decision_trace is not None else None
            )

            try:
                self._run_presentation_pipeline(context, context_analysis)
            except Exception:
                logger.exception(
                    "Presentation pipeline failed for this turn; continuing without a "
                    "presentation update."
                )

            explicit = self._persona_manager.detect_explicit_selection(transcript)
            if explicit is not None:
                self._persona_manager.select(explicit, SwitchReason.EXPLICIT_SELECTION)
            else:
                self._persona_manager.select_from_context(context_analysis, transcript)

            persona = self._persona_manager.active_persona()
            selected_engine = (
                decision_trace.selected_engine if decision_trace is not None else None
            )
            emotional_state = self._emotional_state_manager.current_state()

            if selected_engine is EngineSelection.DEVICE_CONTROL:
                reply = self._handle_device_control_turn(decision_trace, session_id, persona.name)
            elif selected_engine is EngineSelection.WORKFLOW:
                reply = self._handle_workflow_turn(decision_trace, session_id, persona.name)
            elif selected_engine is EngineSelection.SCHEDULER:
                reply = self._handle_scheduler_turn(decision_trace)
            elif selected_engine is EngineSelection.INTERNET_AGENT:
                reply = self._handle_internet_agent_turn(decision_trace)
            elif selected_engine is EngineSelection.EMOTION_SUPPORT:
                # EMOTION_SUPPORT selects a tone within compose_reply_safely()'s
                # own template path, not a distinct subsystem — see
                # decision/authority.py's own docstring and Sprint 5.4's
                # Engineering Rationale.
                reply = self._persona_manager.compose_reply_safely(
                    transcript, context, decision_trace, emotional_state
                )
            else:
                reply = self._compose_conversational_reply(
                    transcript, context, decision_trace, persona.name
                )

            if companion_moment is not None:
                reply = _prefix_companion_moment(reply, companion_moment)

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

            presentation_state = self._presentation_controller.last_state_for(persona.name)
            voice_warmth = (
                presentation_state.voice_warmth if presentation_state is not None else 0.5
            )
            paced_reply = self._voice_personality_modulator.shape_pacing(reply, voice_warmth)

            self._apply_turn_phase(RingState.SPEAKING)
            self._session_manager.speak_reply(
                paced_reply, persona.voice_id, on_audio_ready=self._drive_lip_sync_if_avatar_mounted
            )
            self._apply_turn_phase(RingState.LISTENING)
        except Exception:
            logger.exception(
                "Unexpected failure while handling a completed turn; ending the session "
                "rather than leaving it stuck."
            )
            self._session_manager.end_session(SessionEndReason.ERROR)

    def _run_presentation_pipeline(
        self, context: ConversationContext, context_analysis: ContextAnalysis | None
    ) -> None:
        """Per real turn: EmotionDetectionEngine.collect_signals()/
        .estimate() -> EmotionalStateManager.decay_toward_baseline(elapsed)
        then .apply_estimate(estimate) -> (conditionally, per Sprint 5.3's
        own significance threshold) EmotionalMemory.record_significant_
        moment() -> PresentationController.refresh() ->
        AdaptiveWorkspaceController.select_profile()/.should_switch()
        (Jarvis-only path) -> GestureEngine.trigger_event(TURN_END, ...).
        Called from within its own narrow exception boundary in
        _handle_turn_complete() — see that method's own docstring.

        last_transcription_result() (voice/session_manager.py, Sprint
        5.14) can honestly be None only before this process's very first
        transcribed utterance, which can never reach a turn-complete
        callback in practice (on_turn_complete only fires after a real
        transcription exists) — guarded here anyway as a defensive,
        never-crash floor rather than assumed impossible."""
        transcription = self._session_manager.last_transcription_result()
        if transcription is None:
            return

        signals = self._emotion_detection_engine.collect_signals(
            transcription, context_analysis, context
        )
        estimate = self._emotion_detection_engine.estimate(signals)

        now = datetime.now(UTC)
        elapsed = (
            (now - self._last_emotion_update_at).total_seconds()
            if self._last_emotion_update_at is not None
            else 0.0
        )
        self._emotional_state_manager.decay_toward_baseline(elapsed)
        state = self._emotional_state_manager.apply_estimate(estimate)
        self._last_emotion_update_at = now

        # _score_significance() is memory/emotional_memory.py's own
        # private significance formula — imported directly here rather
        # than duplicated, the same reuse tests/unit/memory/
        # test_emotional_memory.py itself already relies on, so this
        # sprint's own "record only when genuinely significant" gate
        # cannot drift from EmotionalMemory's own definition of
        # significant.
        if _score_significance(state) >= self._memory_config.emotional_moment_recall_threshold:
            active_persona = self._persona_manager.active_persona()
            memory_type = (
                MemoryType.JARVIS if active_persona.name == "jarvis" else MemoryType.MINIE
            )
            category = (
                context_analysis.primary_topic if context_analysis else ""
            ) or "conversation"
            self._emotional_memory.record_significant_moment(
                content=transcription.text,
                memory_type=memory_type,
                category=category,
                state=state,
            )

        self._presentation_controller.refresh()

        active_persona = self._persona_manager.active_persona()
        if active_persona.name == "jarvis":
            self._update_workspace_profile(context_analysis)

        event = self._gesture_engine.trigger_event(GestureTrigger.TURN_END, active_persona.name)
        if event is not None:
            self._presentation_controller.dispatch_gesture(event)

    def _update_workspace_profile(self, context_analysis: ContextAnalysis | None) -> None:
        """Jarvis-only: tracks AdaptiveWorkspaceController.should_switch()'s
        own caller-owned running consecutive-match count (Sprint 5.12
        deliberately left ownership of it to this integration sprint) and
        applies a real dashboard rearrangement via JarvisRenderer.
        apply_workspace_profile() once the debounce threshold is met."""
        candidate = self._adaptive_workspace_controller.select_profile(context_analysis)
        if candidate == self._current_workspace_profile:
            self._pending_workspace_candidate = None
            self._workspace_consecutive_match_count = 0
            return

        if candidate == self._pending_workspace_candidate:
            self._workspace_consecutive_match_count += 1
        else:
            self._pending_workspace_candidate = candidate
            self._workspace_consecutive_match_count = 1

        if self._adaptive_workspace_controller.should_switch(
            self._current_workspace_profile, candidate, self._workspace_consecutive_match_count
        ):
            self._jarvis_renderer.apply_workspace_profile(candidate)
            self._current_workspace_profile = candidate
            self._pending_workspace_candidate = None
            self._workspace_consecutive_match_count = 0

    def _maybe_prepare_companion_moment(
        self, context: ConversationContext, session_id: str
    ) -> CompanionMoment | None:
        """CompanionExperienceEngine's own real session-start trigger
        (Sprint 5.13's own "no live caller yet" gap): a session_id is
        checked (and recorded) here exactly once, on its own first turn
        — idle_duration_seconds reuses ConversationContext.last_activity_at,
        the real gap since the previous session's own last activity,
        already flowing through this pipeline (EmotionDetectionEngine's
        own pause_before_turn_seconds signal reads the identical field).
        Never raises — CompanionExperienceEngine's own methods already
        promise never to, guarded here anyway as defense in depth,
        matching this class's own established discipline."""
        if session_id in self._greeted_session_ids:
            return None
        self._greeted_session_ids.add(session_id)
        try:
            idle_duration = max(
                0.0, (datetime.now(UTC) - context.last_activity_at).total_seconds()
            )
            moment = self._companion_experience_engine.check_for_greeting(idle_duration)
            if moment is None:
                moment = self._companion_experience_engine.check_for_celebration()
            return moment
        except Exception:
            logger.exception(
                "Companion Experience session-start check failed; continuing without one."
            )
            return None

    def _apply_turn_phase(self, phase: RingState) -> None:
        """Threads voice/session_manager.py's own real turn-phase concept
        into JarvisRenderer without adding new state to that module (see
        VoiceSessionManager.current_session_state()'s own docstring) —
        never raises; a renderer-side failure must not affect the
        turn's own spoken reply."""
        try:
            self._jarvis_renderer.apply_turn_phase(phase)
        except Exception:
            logger.exception("apply_turn_phase(%s) failed; continuing.", phase.value)

    def _drive_lip_sync_if_avatar_mounted(self, audio: bytes, sample_rate_hz: int) -> None:
        """speak_reply()'s own on_audio_ready callback (Sprint 5.14):
        drives LipSyncDriver.drive_from_audio() — which itself spawns a
        non-blocking background thread — only when Minie's AvatarRenderer
        is the currently mounted renderer, matching this sprint's own
        "when the mounted renderer is an AvatarRenderer" wording. Checked
        via PresentationController.mounted_persona_name rather than
        active_persona() — the mounted renderer, not merely the active
        persona, is what's actually about to be driven (see
        PresentationController's own "mounted renderer is a deliberately
        separate concept from active persona" docstring)."""
        if self._presentation_controller.mounted_persona_name == "minie":
            self._lip_sync_driver.drive_from_audio(audio, sample_rate_hz, self._avatar_renderer)

    def _compose_conversational_reply(
        self,
        transcript: str,
        context: ConversationContext,
        decision_trace: DecisionTrace | None,
        persona_name: str,
    ) -> str:
        """The real Response Generation stage (see this module's own
        docstring) for the common case: a plain question, a casual
        remark, or anything else that isn't a device-control/workflow/
        scheduler/internet-search request. Degrades to
        PersonaManager.compose_reply_safely() — the Level 2 templated
        acknowledgement — in exactly two cases, both honest, not
        silently masking a failure:

        1. An empty/whitespace-only transcript (e.g. Whisper's own
           no-speech threshold forcing text="", backlog/technical_debt.md
           item 9): skips the LLM call entirely rather than asking a
           model to respond to nothing — compose_reply_safely() already
           returns the correct "I didn't catch anything" reply for this
           case.
        2. ResponseGenerator.generate() raises LlmError (Ollama
           unreachable, a timeout, an unpulled model): the same
           "narrower catch degrades this one turn rather than the coarse
           outer catch ending the whole session" reasoning
           _handle_scheduler_turn()'s own Sprint 4.19 hardening already
           established for calendar_store.save()."""
        if not transcript.strip():
            return self._persona_manager.compose_reply_safely(transcript, context, decision_trace)
        try:
            return self._response_generator.generate(
                transcript, context, decision_trace, persona_name
            )
        except LlmError:
            logger.warning(
                "Response Generator call failed; falling back to the templated reply.",
                exc_info=True,
            )
            return self._persona_manager.compose_reply_safely(transcript, context, decision_trace)

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

    def _handle_scheduler_turn(self, trace: DecisionTrace) -> str:
        """Sprint 4.18. Deliberately narrow, matching
        _handle_device_control_turn()'s own precedent: creates a NEW
        reminder only when the transcript names a resolvable relative
        time ("in N minutes"/"in N hours" — AuthorityEvaluator's own
        routing already confirmed one exists via _is_schedulable_
        reminder_request() before selecting SCHEDULER at all, but this
        method re-parses it here to get the actual computed timestamp,
        the same "routing is cheap, real resolution happens downstream"
        split _resolve_action_engine() established for DEVICE_CONTROL/
        WORKFLOW).

        Two real gaps, named not hidden (see sprint_4_18.md's own
        Architecture Notes): no absolute date/time parsing ("tomorrow
        at 5pm", "next Monday"), and no postpone/acknowledge of an
        EXISTING reminder from a live turn — there is no "which
        reminder do you mean" disambiguation mechanism this project
        has, unlike a workflow's own by-name lookup. ReminderEngine.
        postpone()/reschedule()/acknowledge() remain real, tested, and
        callable with no live turn-based caller yet — the same
        "implemented, tested in isolation, no live caller" shape this
        project already tracks elsewhere (backlog/technical_debt.md
        item 24's own precedent).

        Sprint 4.19 hardening (scenario e): calendar_store.save() is
        deliberately left unwrapped by CalendarStore itself (see that
        module's own docstring) — the narrow try/except below is what
        gives a real SQLite failure here an honest degraded reply
        instead of two worse alternatives: silently claiming "Done" when
        nothing was actually saved (if save() swallowed its own
        failure), or falling through to _handle_turn_complete()'s outer
        catch, which would speak no reply at all and abruptly end the
        whole session — coarser than necessary for a failure scoped to
        this one turn, the same "a narrower catch beats the coarse outer
        one once a failure mode is specific enough to degrade instead of
        aborting" reasoning _run_decision_pipeline()'s own Sprint 3.13
        hardening already established."""
        now = datetime.now(UTC)
        scheduled_at = _parse_relative_time(trace.intent.raw_transcript, now)
        if scheduled_at is None:
            return "I couldn't tell when to remind you."

        title = trace.context_analysis.primary_topic.strip() or trace.intent.raw_transcript.strip()
        item = ScheduledItem(
            item_id=str(uuid.uuid4()),
            item_type=ItemType.EVENT,
            title=title,
            scheduled_at=scheduled_at,
            created_at=now,
        )
        try:
            self._calendar_store.save(item)
        except Exception:
            logger.exception("Failed to save scheduled item %r; reporting honestly.", title)
            return "I'm sorry, I couldn't save that reminder right now."
        return f"Done — I'll remind you about {title} at {scheduled_at.strftime('%H:%M')}."

    def _handle_internet_agent_turn(self, trace: DecisionTrace) -> str:
        """Sprint 4.18. ResearchEngine.research() already degrades to []
        (never raises) on any real search failure (Sprint 4.16); this
        method short-circuits on that empty result rather than still
        calling Summarizer — asking an LLM to "summarize" zero real
        search results risks a worse, entirely ungrounded hallucination
        than the honest "couldn't find anything" this returns instead."""
        query = trace.context_analysis.primary_topic.strip() or trace.intent.raw_transcript.strip()
        results = self._research_engine.research(query)
        if not results:
            return f"I couldn't find anything for {query}."

        citations = self._source_validator.validate(results)
        summary = self._summarizer.summarize(query, results, citations)
        corroborated_count = sum(1 for c in summary.citations if c.is_corroborated)
        return (
            f"{summary.summary_text} (Based on {len(summary.citations)} source(s), "
            f"{corroborated_count} corroborated.)"
        )

    def _check_and_announce_due_reminder(self) -> None:
        """Sprint 4.18. TaskScheduler job body (registered in start(),
        on scheduler_config.poll_interval_seconds) — this project's
        first genuinely PROACTIVE (JARMINEI-initiated, not turn-
        triggered) behavior. See this module's own docstring for the
        full wiring diagram and Architecture Notes for the real
        concurrency discipline this method's own call ordering exists
        to satisfy.

        Part 2's own Priority Queue language for Scheduled Reminders is
        explicit: "Queued" — a due item found while a session is
        already ACTIVE is left untouched in the queue (peek_next(), not
        popped) rather than interrupting; the next poll checks again.
        peek_next() before pop_next() also means a future, still-
        unhandled PriorityItem type (anything other than
        SCHEDULED_REMINDER — no other live source exists yet, see
        backlog/technical_debt.md item 17) is never silently consumed
        by this method without understanding it."""
        if self._quiet_mode_controller.current_mode() is not OperatingMode.DORMANT:
            return
        peeked = self._priority_queue_manager.peek_next()
        if peeked is None or peeked.priority is not PriorityLevel.SCHEDULED_REMINDER:
            return

        item = self._priority_queue_manager.pop_next()
        scheduled_item: ScheduledItem = item.payload
        persona = self._persona_manager.active_persona()
        self._quiet_mode_controller.activate(
            ActivationReason.SCHEDULED_ALERT,
            announce_first=(scheduled_item.title, persona.voice_id),
        )


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


def _prefix_companion_moment(reply: str, moment: CompanionMoment) -> str:
    """Folds a CompanionMoment's own content into a reply as a plain-text
    prefix (Sprint 5.14) — Persona.compose_reply()'s own signature has no
    CompanionMoment parameter, and extending it is outside this sprint's
    own Files to Modify (personas/base.py, personas/jarvis.py,
    personas/minie.py are none of them), so phrasing happens here rather
    than through a persona template — a disclosed, narrower
    implementation of the Sprint Book's own "folded into the next
    reply's own content input" language (mirrors _describe_action_result()'s/
    _describe_workflow_result()'s own precedent of composing confirmation
    text directly in this class rather than through Persona.compose_reply()
    for the identical reason). CompanionMoment.referenced_content is
    always the stored MemoryRecord.content verbatim (CompanionExperienceEngine's
    own "decide the moment, not the phrasing" contract) — folded in as
    plain, honest attribution, never presented as a fact JARMINEI is
    newly asserting."""
    if moment.moment_type is CompanionMomentType.GREETING:
        prefix = (
            f"Welcome back — last time we talked you mentioned {moment.referenced_content}. "
            if moment.referenced_content
            else "Welcome back. "
        )
    else:
        prefix = f"By the way — {moment.referenced_content}. That's worth celebrating! "
    return prefix + reply
