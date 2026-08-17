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
conversation turn. Sprint 5.24 (Companion Intelligence Integration)
renames and widens it from a single-source reminder check into a real,
exhaustive three-source dispatcher — see _check_and_announce_priority_item()'s
own docstring for the full per-PriorityLevel dispatch table:

    (background, every scheduler_config.poll_interval_seconds)
    _check_and_announce_priority_item():
        _maybe_enqueue_wellness_prompt() (5.24) -- WellnessTracker.
            evaluate_triggers(interval_overrides=AdaptiveWellnessAdjuster.
            compute_overrides()) -> a real WellnessPrompt, deduplicated
            per still-crossed trigger type, enqueued as PriorityLevel.WELLNESS
          |
        QuietModeController.current_mode() is DORMANT?  -- no -> return
        (a live session is active; Part 2's own "Queued" language for
        Scheduled Reminders/Wellness/General Suggestions alike means a
        due item simply waits for the next poll, it never interrupts)
          | yes
        PriorityQueueManager.peek_next() -- None -> return
          | a PriorityItem
        dispatch on peeked.priority (SCHEDULED_REMINDER/WELLNESS/
        GENERAL_SUGGESTION each have their own real handler; an
        unrecognized PriorityLevel logs a warning and leaves the item
        queued rather than popping and discarding it):
            SCHEDULED_REMINDER -> QuietModeController.activate(SCHEDULED_ALERT,
                announce_first=(item.title, persona.voice_id)) -- unchanged
                since Sprint 4.18
            WELLNESS -> PersonaManager.select("minie", SwitchReason.WELLNESS)
                -> QuietModeController.activate(SCHEDULED_ALERT,
                announce_first=(prompt.message, "minie")) -> PersonaManager.
                resume_previous() immediately after the (synchronous)
                announcement completes -> WellnessEscalationManager.
                register_prompt_shown()
            GENERAL_SUGGESTION -> QuietModeController.activate(SCHEDULED_ALERT,
                announce_first=(recommendation.text, persona.voice_id)) --
                through whichever persona is already active, no switch
          |
        QuietModeController.activate(...)
            -> VoiceSessionManager.begin_session(announce_first=...)
               speaks the item BEFORE utterance capture starts, then
               re-arms listening exactly like any other session (see
               voice/session_manager.py's own docstring for why that
               ordering matters)

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

Sprint 5.24 adds up to three more TaskScheduler jobs (each guarded by a
None-check on its own dependency, so a Level 5 Part B construction
fallback — see main.py's own _null_level5_part_b_modules() — simply
skips registering it, never crashing start() itself): a wellness-prompt
detection/enqueue job on wellness_config.idle_check_interval_seconds
(_maybe_enqueue_wellness_prompt(), a real, disclosed addition beyond
this sprint's own literal five-job Data Flow list — WellnessTracker
itself has no PriorityQueueManager dependency and is outside this
sprint's own Files to Modify, so this class is the only place the
WellnessTracker.evaluate_triggers() -> PriorityQueueManager.enqueue()
step described in that Data Flow can actually live), plus
PatternRecognizer.run_detection_pass()/RecommendationEngine.
generate_recommendations() on learning_config.pattern_detection_
interval_seconds/recommendation_generation_interval_seconds
respectively — mirroring ReminderEngine.register()'s own "the source
class owns its own enqueue job" precedent as closely as each collaborator's
own Files-to-Modify scope allows.

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

from analytics.dashboard_data import AnalyticsDashboardService
from analytics.usage_store import UsageStore
from analytics.usage_tracker import UsageTracker
from config.schema import (
    InternetConfig,
    LearningConfig,
    MemoryConfig,
    RuntimeConfig,
    SchedulerConfig,
    WellnessConfig,
)
from context.context_engine import ContextEngine
from core.logging_setup import get_logger
from core.resource_monitor import ResourceMonitor
from core.runtime_manager import RuntimeManager
from decision.adaptive_prioritizer import AdaptivePrioritizer, PrioritizationDecision
from decision.authority import AuthorityEvaluator, DecisionTrace, EngineSelection
from decision.context_analyzer import ContextAnalysis, ContextAnalyzer
from decision.intent_detector import IntentDetector
from decision.llm_client import LlmError
from decision.priority_queue import PriorityItem, PriorityLevel, PriorityQueueManager
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
from knowledge.knowledge_graph_store import KnowledgeGraphStore
from learning.pattern_recognizer import PatternRecognizer
from learning.recommendation import RecommendationEngine
from memory.confidence_scorer import ConfidenceScorer
from memory.emotional_memory import EmotionalMemory, _score_significance
from memory.errors import MemoryStoreError
from memory.lifecycle_manager import MemoryLifecycleManager
from memory.models import MemoryType
from memory.retrieval_engine import MemoryRetrievalEngine
from memory.short_term_memory import ShortTermMemory
from personas.base import Persona
from personas.persona_manager import PersonaManager, SwitchReason
from planning.planning_engine import PlanningEngine
from planning.planning_model import Goal, PlanningStatus, Task
from planning.self_evaluator import SelfEvaluator
from planning.task_graph import TaskGraph
from planning.task_graph_store import TaskGraphStore
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
from reasoning.explainability import ExplainabilityLayer, ExplanationRequest
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
from wellness.adaptive_wellness import AdaptiveWellnessAdjuster
from wellness.escalation import WellnessEscalationManager
from wellness.wellness_model import WellnessPrompt, WellnessTriggerType
from wellness.wellness_tracker import WellnessTracker
from workflow.session_resumption import SessionResumption
from workflow.task_graph_adapter import TaskGraphWorkflowAdapter
from workflow.workflow_executor import WorkflowExecutor, WorkflowRunResult
from workflow.workflow_store import WorkflowStore

logger = get_logger(__name__)

_DEVICE_CONTROL_REQUESTED_BY = "voice_turn"
_PLANNING_REQUESTED_BY = "planning_turn"
_MOST_RECENT_TRACE_SUBJECT_ID = "most_recent_turn"
"""ExplainabilityLayer's own decision_trace_lookup callable (Sprint
6.11) ignores subject_id entirely once wired to
lookup_last_decision_trace() (this class tracks only the single most
recent DecisionTrace, never a keyed history) — this constant exists so
every call site passes the identical, self-documenting placeholder
rather than an arbitrary string."""

_ACCEPTANCE_WORDS = frozenset({"yes", "yeah", "yep", "accept", "confirm", "approved"})
_ACCEPTANCE_PHRASES: tuple[str, ...] = ("go ahead", "do it", "sounds good")
_REJECTION_WORDS = frozenset({"no", "nope", "cancel", "reject", "discard"})
_REJECTION_PHRASES: tuple[str, ...] = ("never mind", "nevermind", "forget it")
"""Sprint 6.13's own accept/reject vocabulary for a pending plan
proposal. Deliberately checks the transcript's own FIRST WORD against
the short, ambiguous single-word sets (never a bare substring match —
"yesterday" must never match "yes") while still allowing the longer,
low-collision multi-word phrases to match anywhere in the transcript.
See CommunicationPipeline._handle_planning_turn()'s own docstring for
why this lives here, as conversational state, rather than as a
decision/authority.py keyword-routing gate."""

_RUN_PLAN_KEYWORDS: tuple[str, ...] = ("run my plan", "start my plan", "execute my plan")
_RESUME_SESSION_KEYWORDS: tuple[str, ...] = (
    "resume my session",
    "resume my previous session",
    "resume session",
)
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
_PRIORITY_ITEM_ANNOUNCEMENT_JOB_ID = "proactive_priority_item_announcement"
"""Renamed from _REMINDER_ANNOUNCEMENT_JOB_ID (Sprint 5.24) — the job
itself now dispatches three priority sources, not just SCHEDULED_REMINDER
(see _check_and_announce_priority_item()'s own docstring), the same
"correct a name once its own scope has genuinely grown" precedent Sprint
4.1's own Application Control -> Application Manager rename already
established."""
_WELLNESS_ENQUEUE_JOB_ID = "wellness_prompt_enqueue"
_PATTERN_DETECTION_JOB_ID = "pattern_detection_pass"
_RECOMMENDATION_GENERATION_JOB_ID = "recommendation_generation"
_RUNTIME_HOUSEKEEPING_JOB_ID = "runtime_housekeeping"
"""Runtime Phase 9 (Runtime Refactor Sprint) — the one real periodic
caller of RuntimeManager.sweep_idle_services()/evict_least_recently_used(),
unconditional (unlike the Level 5 Part B jobs above, none of this job's
own collaborators are ever None)."""
_KNOWLEDGE_GRAPH_PURGE_JOB_ID = "knowledge_graph_purge"
_USAGE_STORE_PURGE_JOB_ID = "usage_store_purge"
"""Sprint 6.21 (Privacy Verification) — the fourth and fifth real
instance of backlog/technical_debt.md items 11/15/24's own established
"add the caller, register the job" resolution pattern, closing the same
gap for KnowledgeGraphStore/UsageStore that ConversationSessionStore/
ActionAuditLog/MemoryStore already had closed. Both None-guarded in
start() (Level 6 Part A/Level 5 Part B collaborators, either can be
None) and resource_sensitive=True (neither has real user-facing
lateness cost, the same classification Sprint 6.19 already gave the
maintenance passes/pattern detection/recommendation generation jobs)."""


def _is_acceptance_phrase(transcript: str) -> bool:
    lowered = transcript.strip().lower()
    if not lowered:
        return False
    first_word = lowered.split(" ", 1)[0].rstrip(".!,")
    if first_word in _ACCEPTANCE_WORDS:
        return True
    return any(phrase in lowered for phrase in _ACCEPTANCE_PHRASES)


def _is_rejection_phrase(transcript: str) -> bool:
    lowered = transcript.strip().lower()
    if not lowered:
        return False
    first_word = lowered.split(" ", 1)[0].rstrip(".!,")
    if first_word in _REJECTION_WORDS:
        return True
    return any(phrase in lowered for phrase in _REJECTION_PHRASES)


def _mentions_run_plan_keywords(transcript: str) -> bool:
    lowered = transcript.lower()
    return any(keyword in lowered for keyword in _RUN_PLAN_KEYWORDS)


def _mentions_resume_session_keywords(transcript: str) -> bool:
    lowered = transcript.lower()
    return any(keyword in lowered for keyword in _RESUME_SESSION_KEYWORDS)


def _describe_proposed_goal(goal: Goal) -> str:
    milestone_count = len(goal.milestones)
    task_count = sum(len(milestone.tasks) for milestone in goal.milestones)
    milestone_titles = "; ".join(milestone.title for milestone in goal.milestones)
    return (
        f'Here\'s my plan for "{goal.statement}": {milestone_count} milestone(s), '
        f"{task_count} task(s) — {milestone_titles}. "
        'Say "yes" to accept it, or "no" to discard it.'
    )


def _extract_announcement_text(payload: object) -> str:
    """Sprint 6.13. A GENERAL_SUGGESTION/IMPORTANT_ALERT PriorityItem's
    own payload can genuinely be a Recommendation (.text,
    learning/recommendation.py) or a ProactivePrompt (.message,
    proactive/proactive_model.py) — two real producers, two different
    attribute names, neither one wrong. Checked mechanically rather than
    isinstance-branched, the same "message-or-text" precedent decision/
    adaptive_prioritizer.py's own _describe_payload() already established
    for the identical real ambiguity (Sprint 6.12)."""
    for attribute_name in ("message", "text"):
        value = getattr(payload, attribute_name, None)
        if isinstance(value, str) and value:
            return value
    return "You have a new item to review."


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


class DecisionTraceLookupRelay:
    """Sprint 6.13's own widened sibling of CallbackRelay, for the one
    real circular-construction case CallbackRelay's own fire-and-forget
    shape cannot serve: ExplainabilityLayer's own decision_trace_lookup
    constructor parameter (Sprint 6.11) needs a real DecisionTrace | None
    value BACK from its target, which CallbackRelay's own __call__
    always discards (it returns None unconditionally, by design, since
    turn_complete_relay/session_ended_relay's own real targets never
    return anything their caller reads). main.py constructs this before
    ExplainabilityLayer exists, then points target at
    CommunicationPipeline.lookup_last_decision_trace once the pipeline
    itself exists — the identical indirection main.py's own
    persona_switch_relay already established for the same "constructed
    before its real target can exist" problem (see this module's own
    docstring)."""

    def __init__(self) -> None:
        self.target: Callable[[str], DecisionTrace | None] | None = None

    def __call__(self, subject_id: str) -> DecisionTrace | None:
        if self.target is None:
            return None
        return self.target(subject_id)


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
        internet_config: InternetConfig,
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
        wellness_tracker: WellnessTracker | None,
        wellness_escalation_manager: WellnessEscalationManager | None,
        adaptive_wellness_adjuster: AdaptiveWellnessAdjuster | None,
        dashboard_service: AnalyticsDashboardService | None,
        usage_tracker: UsageTracker | None,
        usage_store: UsageStore | None,
        pattern_recognizer: PatternRecognizer | None,
        recommendation_engine: RecommendationEngine | None,
        learning_config: LearningConfig,
        wellness_config: WellnessConfig,
        runtime_manager: RuntimeManager,
        resource_monitor: ResourceMonitor,
        runtime_config: RuntimeConfig,
        task_graph_store: TaskGraphStore | None,
        knowledge_graph_store: KnowledgeGraphStore | None,
        planning_engine: PlanningEngine | None,
        context_engine: ContextEngine | None,
        explainability_layer: ExplainabilityLayer | None,
        adaptive_prioritizer: AdaptivePrioritizer | None,
        task_graph_workflow_adapter: TaskGraphWorkflowAdapter | None,
        session_resumption: SessionResumption | None,
        self_evaluator: SelfEvaluator | None,
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
        self._internet_config = internet_config
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
        # Sprint 5.24 — Level 5 Part B (Companion Intelligence). All six
        # are optional, matching main.py's own _null_level5_part_b_modules()
        # fallback (a genuine Part B construction failure passes literal
        # None for each, per this sprint's own Files to Modify text — a
        # simpler fallback shape than Part A's own always-real-but-inert
        # objects, since none of these six ever get called unconditionally
        # the way Part A's presentation objects do every single turn).
        # usage_tracker itself has no direct call site in this class (it
        # self-schedules via CoreManager, and dashboard_service already
        # wraps usage_store directly) — accepted and stored anyway per
        # this sprint's own explicit constructor-DI-growth list, the same
        # "kept for symmetry/future use" precedent action_recovery_manager
        # already established (_Level4Modules' own docstring). usage_store
        # itself, unlike usage_tracker, DOES gain a real, direct call site
        # as of Sprint 6.21 (Privacy Verification) — its own new
        # purge_older_than() TaskScheduler job, registered in start()
        # below, the identical treatment action_audit_log/conversation_store
        # already receive.
        self._wellness_tracker = wellness_tracker
        self._wellness_escalation_manager = wellness_escalation_manager
        self._adaptive_wellness_adjuster = adaptive_wellness_adjuster
        self._dashboard_service = dashboard_service
        self._usage_tracker = usage_tracker
        self._usage_store = usage_store
        self._pattern_recognizer = pattern_recognizer
        self._recommendation_engine = recommendation_engine
        self._learning_config = learning_config
        self._wellness_config = wellness_config
        # Runtime Phase 9 (Runtime Refactor Sprint) — always real,
        # unconditional (unlike the six Level 5 Part B collaborators
        # above): every one of runtime_manager/resource_monitor exists
        # regardless of any construction-fallback path in main.py, the
        # same "no null-fallback needed" shape scheduler_config/
        # memory_config already have.
        self._runtime_manager = runtime_manager
        self._resource_monitor = resource_monitor
        self._runtime_config = runtime_config
        # Sprint 6.13 — Level 6 Part A (Autonomous Intelligence)
        # Integration. All are optional, matching main.py's own
        # _null_level6_part_a_modules() fallback — a genuine Level 6
        # Part A construction failure passes literal None for each, the
        # same simpler-than-Part-A-presentation fallback shape Level 5
        # Part B's own six collaborators already established (Sprint
        # 5.24), since none of these are called unconditionally on every
        # single turn either. knowledge_graph_store joins the other eight
        # here as of Sprint 6.21 (Privacy Verification), for its own new
        # purge_older_than() TaskScheduler job below — Sprint 6.13 itself
        # never threaded it into this constructor since this class had no
        # direct call site for it until now (SessionResumption/
        # ProactiveAssistant hold their own separate references).
        self._task_graph_store = task_graph_store
        self._knowledge_graph_store = knowledge_graph_store
        self._planning_engine = planning_engine
        self._context_engine = context_engine
        self._explainability_layer = explainability_layer
        self._adaptive_prioritizer = adaptive_prioritizer
        self._task_graph_workflow_adapter = task_graph_workflow_adapter
        self._session_resumption = session_resumption
        self._self_evaluator = self_evaluator
        # A Goal PlanningEngine.decompose_goal() has proposed but the user
        # has not yet accepted or rejected — the real conversational state
        # _handle_planning_turn()'s own propose/accept two-step flow needs
        # across turns (this sprint's own Potential Risks flagged this
        # exact need). Cleared on acceptance, rejection, or overwritten by
        # a fresh proposal; otherwise persists across intervening turns
        # until explicitly responded to — a real, disclosed limitation
        # (no expiry timeout), not a bug.
        self._pending_proposed_goal: Goal | None = None
        # The most recent NON-EXPLANATION turn's own DecisionTrace —
        # ExplainabilityLayer's own decision_trace_lookup real target
        # (via DecisionTraceLookupRelay, wired in main.py once this
        # pipeline exists). Deliberately excludes an explanation turn's
        # own trace so asking "why?" twice in a row still explains the
        # original subject, not the previous explanation turn's own
        # routing decision — see _handle_turn_complete()'s own docstring.
        self._last_decision_trace: DecisionTrace | None = None
        # ContextEngine.build() needs a real session_id; _check_and_
        # announce_priority_item() runs with no live session of its own
        # (only ever while QuietModeController is DORMANT), so it reuses
        # whatever the most recent real turn's own session_id was. The
        # sentinel default is harmless if ever queried before any turn
        # has happened this process — ConversationSessionStore.
        # get_recent_turns() for an unknown session_id just returns [].
        self._last_session_id: str = "no-session-yet"
        # In-memory dedup, mirroring ReminderEngine._enqueued_item_ids'
        # own identical precedent: evaluate_triggers() is a pure read with
        # no "already enqueued" memory of its own, so without this a
        # still-crossed trigger would be re-enqueued as a fresh duplicate
        # PriorityItem on every single poll until it's actually announced.
        self._pending_wellness_trigger_types: set[WellnessTriggerType] = set()
        # generate_recommendations() is stateless/idempotent (learning/
        # recommendation.py's own docstring) — re-running it against
        # unchanged PatternStore data reproduces the same recommendations,
        # keyed by based_on_pattern_id (stable across calls, unlike each
        # call's own fresh recommendation_id) rather than by text, so a
        # pattern whose confidence/description later changes is still
        # recognized as "already surfaced," not silently re-enqueued.
        self._enqueued_recommendation_pattern_ids: set[str] = set()
        # Sprint 5.24 — _check_and_announce_priority_item()'s own dispatch
        # table, exhaustive over every PriorityLevel this Sprint Book gives
        # a real producer to. Built here (bound methods, not a class-level
        # dict of unbound references) since the methods themselves are
        # defined later in this same class body. Sprint 6.13 adds
        # IMPORTANT_ALERT — ProactiveAssistant's own three hard triggers
        # (UPCOMING_DEADLINE/BATTERY_CRITICAL/FORGOTTEN_REMINDER, Sprint
        # 6.8) finally get an announcement path, closing backlog/
        # technical_debt.md item 17 in full; this dict is now exhaustive
        # over all five PriorityLevel members, CRITICAL_EMERGENCY's own
        # real handling living entirely in decision/authority.py's own
        # Authority Evaluation stage instead (never queued at all).
        self._priority_item_handlers: dict[PriorityLevel, Callable[[PriorityItem], None]] = {
            PriorityLevel.SCHEDULED_REMINDER: self._announce_scheduled_reminder,
            PriorityLevel.WELLNESS: self._announce_wellness,
            PriorityLevel.GENERAL_SUGGESTION: self._announce_general_suggestion,
            PriorityLevel.IMPORTANT_ALERT: self._announce_important_alert,
        }
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
        CoreManager module-start failure, not a silent no-op.

        Sprint 5.24: also registers up to three Level 5 Part B jobs
        (wellness-prompt enqueue, pattern detection, recommendation
        generation), each guarded by a None-check on its own dependency
        — see this class's own module docstring for the full reasoning."""
        self._turn_complete_relay.target = self._handle_turn_complete
        self._session_ended_relay.target = self._quiet_mode_controller._on_session_ended
        self._wired = True

        self._reminder_engine.register()
        # resource_sensitive=True below (Sprint 6.19 — Resource
        # Protection & Fail-Gracefully Verification) is deliberately
        # NOT applied to every job in this method — only the genuinely
        # deferrable ones this sprint's own Objectives name explicitly
        # (memory lifecycle passes, pattern detection, recommendation
        # generation; usage sampling and the wellness idle-check are
        # marked at their own owning class instead). Never applied to
        # conversation_store_purge/action_audit_log_purge (not named),
        # _check_and_announce_priority_item or wellness_prompt_enqueue
        # (real user-facing announcement lateness cost), or
        # runtime_housekeeping (below — it IS the resource-pressure
        # relief mechanism; gating it on the same pressure it exists to
        # relieve would be self-defeating).
        self._task_scheduler.add_job(
            self._memory_lifecycle_manager.run_cleanup_pass,
            self._scheduler_config.maintenance_interval_seconds,
            job_id=_MAINTENANCE_JOB_IDS[0],
            resource_sensitive=True,
        )
        self._task_scheduler.add_job(
            self._memory_lifecycle_manager.run_monthly_review,
            self._scheduler_config.maintenance_interval_seconds,
            job_id=_MAINTENANCE_JOB_IDS[1],
            resource_sensitive=True,
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
            self._check_and_announce_priority_item,
            self._scheduler_config.poll_interval_seconds,
            job_id=_PRIORITY_ITEM_ANNOUNCEMENT_JOB_ID,
        )
        if self._wellness_tracker is not None:
            self._task_scheduler.add_job(
                self._maybe_enqueue_wellness_prompt,
                self._wellness_config.idle_check_interval_seconds,
                job_id=_WELLNESS_ENQUEUE_JOB_ID,
            )
        if self._pattern_recognizer is not None:
            self._task_scheduler.add_job(
                self._pattern_recognizer.run_detection_pass,
                self._learning_config.pattern_detection_interval_seconds,
                job_id=_PATTERN_DETECTION_JOB_ID,
                resource_sensitive=True,
            )
        if self._recommendation_engine is not None:
            self._task_scheduler.add_job(
                self._generate_and_enqueue_recommendations,
                self._learning_config.recommendation_generation_interval_seconds,
                job_id=_RECOMMENDATION_GENERATION_JOB_ID,
                resource_sensitive=True,
            )
        self._task_scheduler.add_job(
            self._run_runtime_housekeeping,
            self._runtime_config.housekeeping_interval_seconds,
            job_id=_RUNTIME_HOUSEKEEPING_JOB_ID,
        )
        # Sprint 6.21 — Privacy Verification. Zero-arg-callable via each
        # store's own configured-retention default, the identical shape
        # conversation_store_purge/action_audit_log_purge already
        # established above.
        if self._knowledge_graph_store is not None:
            self._task_scheduler.add_job(
                self._knowledge_graph_store.purge_older_than,
                self._scheduler_config.maintenance_interval_seconds,
                job_id=_KNOWLEDGE_GRAPH_PURGE_JOB_ID,
                resource_sensitive=True,
            )
        if self._usage_store is not None:
            self._task_scheduler.add_job(
                self._usage_store.purge_older_than,
                self._scheduler_config.maintenance_interval_seconds,
                job_id=_USAGE_STORE_PURGE_JOB_ID,
                resource_sensitive=True,
            )
        logger.info("Communication Pipeline wiring connected.")

    def stop(self) -> None:
        """Disconnect the callback chain and every TaskScheduler job
        registered in start(). Assumes task_scheduler is still running
        at this point — main.py's reverse-shutdown-order guarantee
        (task_scheduler registered/started before communication_pipeline
        means it stops AFTER communication_pipeline) keeps this true in
        real operation; see main.py's own docstring. The three Sprint
        5.24 job removals are unconditional (not re-guarded by the same
        None-checks start() used) — TaskScheduler.remove_job() is
        documented as a safe no-op for an unregistered job_id, so this is
        simpler than mirroring start()'s own guards for no behavioral
        difference."""
        self._task_scheduler.remove_job(_PRIORITY_ITEM_ANNOUNCEMENT_JOB_ID)
        self._task_scheduler.remove_job(_WELLNESS_ENQUEUE_JOB_ID)
        self._task_scheduler.remove_job(_PATTERN_DETECTION_JOB_ID)
        self._task_scheduler.remove_job(_RECOMMENDATION_GENERATION_JOB_ID)
        self._task_scheduler.remove_job(_RUNTIME_HOUSEKEEPING_JOB_ID)
        self._task_scheduler.remove_job(_KNOWLEDGE_GRAPH_PURGE_JOB_ID)
        self._task_scheduler.remove_job(_USAGE_STORE_PURGE_JOB_ID)
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
        immediately after (see this module's own docstring).

        Sprint 6.13: a real, pending Goal proposal (_pending_proposed_goal)
        is checked BEFORE the ordinary selected_engine dispatch below —
        an acceptance/rejection reply ("yes"/"no") is far too generic a
        phrase for decision/authority.py's own stateless keyword routing
        to ever reliably classify as PLANNING, so this class's own
        conversational state is what actually recognizes it, regardless
        of what the Decision Engine pipeline routed this turn to. Also
        tracks _last_session_id (every turn, unconditionally — needed by
        _check_and_announce_priority_item()'s own later ContextEngine.
        build() call) and _last_decision_trace (every turn EXCEPT an
        EXPLANATION one — see this class's own docstring for why).

        JARVIS Holographic HUD reskin, Phase 6: everything from Decision
        Engine pipeline through pacing now lives in _process_turn() below
        — extracted unchanged (same calls, same order, same exception
        boundaries) so ui/jarvis/command_bar.py's own submit_text() entry
        point can reuse the exact same turn-processing core without a
        live voice session, rather than duplicating it. This method's own
        outer try/except and the SPEAKING/speak_reply()/LISTENING tail
        stay here — a typed command's own equivalent tail is submit_text()'s
        own job, since it must not unconditionally speak (see that
        method's own docstring)."""
        self._last_session_id = session_id
        try:
            persona, paced_reply = self._process_turn(transcript, session_id)
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

    def _process_turn(self, transcript: str, session_id: str) -> tuple[Persona, str]:
        """The real turn-processing core shared by _handle_turn_complete()
        (a completed voice utterance) and submit_text() (a typed command,
        JARVIS Holographic HUD reskin, Phase 6) — Decision Engine pipeline
        -> persona selection -> reply composition -> persistence -> memory
        promotion/override -> pacing. Returns (persona, paced_reply);
        deliberately does NOT speak the reply — that's each caller's own
        decision (always, for a voice turn; only if a session happens to
        be active, for a typed one). Raises on an unexpected failure,
        exactly as this body always has — each caller supplies its own
        outer try/except with its own appropriate degradation, matching
        this class's now-longstanding "every stage fails safe internally;
        outer catches exist for whatever isn't already covered" discipline
        (see _handle_turn_complete()'s own docstring history above)."""
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

        context_analysis = decision_trace.context_analysis if decision_trace is not None else None

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
        selected_engine = decision_trace.selected_engine if decision_trace is not None else None
        emotional_state = self._emotional_state_manager.current_state()

        if selected_engine is not EngineSelection.EXPLANATION:
            self._last_decision_trace = decision_trace

        if (
            self._pending_proposed_goal is not None
            and decision_trace is not None
            and (_is_acceptance_phrase(transcript) or _is_rejection_phrase(transcript))
        ):
            reply = self._handle_planning_turn(decision_trace, session_id, persona.name)
        elif selected_engine is EngineSelection.DEVICE_CONTROL:
            reply = self._handle_device_control_turn(decision_trace, session_id, persona.name)
        elif selected_engine is EngineSelection.WORKFLOW:
            reply = self._handle_workflow_turn(decision_trace, session_id, persona.name)
        elif selected_engine is EngineSelection.SCHEDULER:
            reply = self._handle_scheduler_turn(decision_trace)
        elif selected_engine is EngineSelection.INTERNET_AGENT:
            reply = self._handle_internet_agent_turn(decision_trace)
        elif selected_engine is EngineSelection.WELLNESS:
            reply = self._handle_wellness_turn(decision_trace)
        elif selected_engine is EngineSelection.PLANNING:
            reply = self._handle_planning_turn(decision_trace, session_id, persona.name)
        elif selected_engine is EngineSelection.EXPLANATION:
            reply = self._handle_explanation_turn(decision_trace)
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

        # Sprint 6.18 (Stress & Recovery Testing) hardening: caught
        # locally, not left to a broader except, matching
        # self._conversation_store.record_turn()'s own established
        # "a best-effort side write must never break the user's
        # already-composed reply" degrade immediately above.
        # MemoryStore.store() deliberately raises MemoryStoreError
        # rather than swallowing it (memory/memory_store.py's own
        # docstring) so a caller with a real opinion can decide how
        # to degrade — unlike _accept_pending_goal()'s own
        # MemoryStoreError-shaped handling (where the write IS the
        # user's actual request, so an honest spoken failure is
        # correct), this memory promotion is invisible background
        # bookkeeping the user never asked for; found directly via
        # tests/system/test_level6_part_b_stress.py's own recovery
        # scenario (b), where a real, external SQLite lock on
        # promote_from_turn()'s own write was silently escalating
        # into ending the whole session and discarding an already-
        # composed reply that had nothing to do with memory storage.
        try:
            promoted_record_id = self._short_term_memory.promote_from_turn(turn)
        except MemoryStoreError:
            logger.exception("Failed to promote turn to short-term memory; continuing.")
            promoted_record_id = None
        if promoted_record_id is not None and self._confidence_scorer.detect_override_phrase(
            transcript
        ):
            self._memory_lifecycle_manager.apply_user_override(promoted_record_id)

        presentation_state = self._presentation_controller.last_state_for(persona.name)
        voice_warmth = presentation_state.voice_warmth if presentation_state is not None else 0.5
        paced_reply = self._voice_personality_modulator.shape_pacing(reply, voice_warmth)
        return persona, paced_reply

    def submit_text(self, transcript: str, session_id: str) -> str:
        """JARVIS Holographic HUD reskin, Phase 6 — the real, public entry
        point `ui/jarvis/command_bar.py`'s text input calls, reusing
        _process_turn() (the exact same Decision Engine pipeline/persona
        selection/reply composition/persistence/memory promotion
        _handle_turn_complete() itself uses for a spoken turn) rather than
        a second, competing conversational engine, per the brief's own
        explicit "Do not implement a second conversational engine" rule.

        Two deliberate differences from _handle_turn_complete(), both
        because a typed command has no live voice session backing it:
        - A failure degrades to an honest, returned error string rather
          than calling VoiceSessionManager.end_session() — there is no
          session for this call to have ended in the first place; this
          call itself might be running with no session active at all.
        - The reply is only spoken (speak_reply()) if a voice session
          genuinely IS active right now (e.g. the user typed while also
          mid-conversation) — never unconditionally, since
          VoiceSessionManager.speak_reply() raises SessionError without
          one (confirmed by this workstream's own research). The reply
          text itself is always returned regardless, for the command bar
          to display.

        Runs on whichever thread calls it — ui/jarvis/command_bar.py's own
        job is to call this from a worker thread, never the Qt main
        thread, matching this project's "never block the event loop on
        an LLM turn" discipline; this method itself has no thread
        affinity of its own to enforce that.
        """
        self._last_session_id = session_id
        try:
            persona, paced_reply = self._process_turn(transcript, session_id)
        except Exception:
            logger.exception("Unexpected failure while handling a typed command.")
            return "Sorry, something went wrong processing that."

        if self._session_manager.is_active():
            try:
                self._apply_turn_phase(RingState.SPEAKING)
                self._session_manager.speak_reply(
                    paced_reply,
                    persona.voice_id,
                    on_audio_ready=self._drive_lip_sync_if_avatar_mounted,
                )
                self._apply_turn_phase(RingState.LISTENING)
            except Exception:
                logger.exception(
                    "Failed to speak the reply to a typed command; the reply text is "
                    "still returned to the caller."
                )
        return paced_reply

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
            # Sprint 6.19 hardening (backlog item 39): bookkeeping reset
            # BEFORE apply_workspace_profile(), not after — a synchronous
            # raise from the renderer call is already caught one level up
            # by _run_presentation_pipeline()'s own caller (never aborts
            # the turn), but the old ordering left this reset unreached on
            # that path, so _pending_workspace_candidate/_workspace_
            # consecutive_match_count stayed stale (pointing at the
            # candidate that just failed) and _current_workspace_profile
            # never advanced to reflect the attempted switch — a future
            # turn's own `candidate == self._current_workspace_profile`
            # check above would then keep comparing against a profile this
            # class itself no longer believes is accurate.
            self._current_workspace_profile = candidate
            self._pending_workspace_candidate = None
            self._workspace_consecutive_match_count = 0
            self._jarvis_renderer.apply_workspace_profile(candidate)

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
        than the honest "couldn't find anything" this returns instead.

        Sprint 6.21 (Privacy Verification): checked first, before
        ResearchEngine.research() is ever reached — InternetConfig.enabled
        = False (a real, user-facing opt-out, closing backlog/
        technical_debt.md item 31's own long-open recommendation) means no
        outbound network call happens at all for this turn, not merely
        that the reply changes while a request still goes out."""
        if not self._internet_config.enabled:
            return "Internet research is currently turned off."
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

    def _handle_wellness_turn(self, trace: DecisionTrace) -> str:
        """Sprint 5.24. Answers a live wellness self-check turn — routed
        here by decision/authority.py's own keyword-gated WELLNESS branch
        — from real WellnessTracker/AnalyticsDashboardService state,
        never a fabricated number. trace itself is unused beyond its own
        signature (matching this sprint's own Expected Functions text
        exactly) — the reply is a live status report, not something
        derived from the trace's own routing decision.

        A real, disclosed narrowing: wellness_tracker.py is outside this
        sprint's own Files to Modify, and WellnessTracker exposes no
        public per-trigger elapsed-time accessor (only evaluate_
        triggers(), a currently-due-or-not check) — so this composes
        today's real total active time (AnalyticsDashboardService.
        daily_summary()) with whatever evaluate_triggers() itself already
        exposes publicly, rather than the richer "per-trigger elapsed
        time" the sprint file's own Expected Functions text describes.
        Degrades to an honest "I don't have enough information about
        today yet" when Level 5 Part B modules are unavailable (the
        null-fallback case) or when today's UsageStore has no data at
        all — never a fabricated number."""
        if self._wellness_tracker is None or self._dashboard_service is None:
            return "I don't have enough information about today yet."
        summary = self._dashboard_service.daily_summary(datetime.now(UTC).date())
        if summary.total_active_seconds <= 0:
            return "I don't have enough information about today yet."
        active_minutes = round(summary.total_active_seconds / 60)
        prompt = self._wellness_tracker.evaluate_triggers()
        status = (
            prompt.message if prompt is not None else "No wellness reminders are due right now."
        )
        return f"You've been active for about {active_minutes} minute(s) today. {status}"

    def _handle_planning_turn(
        self, trace: DecisionTrace, session_id: str, persona_name: str
    ) -> str:
        """Sprint 6.13. Three real sub-flows, distinguished by the
        transcript itself (decision/authority.py's own PLANNING routing
        only proves "this is planning-shaped," not which flavor — the
        same "routing is cheap, real resolution happens downstream" split
        _resolve_action_engine() already established):

        1. An acceptance/rejection reply to an already-pending proposal
           (_pending_proposed_goal is not None) — handled first,
           regardless of what decision/authority.py routed this turn to
           (see _handle_turn_complete()'s own docstring for why).
        2. An explicit "run my plan"/"resume my session" request.
        3. Anything else — treated as a fresh goal statement.

        Degrades to an honest "not currently available" whenever the
        Level 6 Part A bundle this specific sub-flow needs is absent —
        never a crash, matching Sprint 5.24's own identical Level 5 Part
        B graceful-degrade precedent."""
        transcript = trace.intent.raw_transcript

        if self._pending_proposed_goal is not None:
            if _is_acceptance_phrase(transcript):
                return self._accept_pending_goal()
            if _is_rejection_phrase(transcript):
                self._pending_proposed_goal = None
                return "Okay, I've discarded that plan."

        if _mentions_run_plan_keywords(transcript):
            return self._run_accepted_plan(session_id, persona_name, trace)
        if _mentions_resume_session_keywords(transcript):
            return self._resume_previous_session(session_id, persona_name, trace)
        return self._propose_new_goal(transcript)

    def _propose_new_goal(self, statement: str) -> str:
        """decompose_goal() never persists (planning/planning_engine.py's
        own "Plan Before Executing" boundary, Sprint 6.1) — this method
        only holds the proposal in memory until _accept_pending_goal()
        (a real Human-First gate, not a formality, per this sprint's own
        Objectives)."""
        if self._planning_engine is None:
            return "Planning isn't currently available."
        try:
            goal = self._planning_engine.decompose_goal(statement)
        except LlmError:
            logger.exception("PlanningEngine.decompose_goal() failed for %r.", statement)
            return "I'm sorry, I couldn't work out a plan for that right now."
        self._pending_proposed_goal = goal
        return _describe_proposed_goal(goal)

    def _accept_pending_goal(self) -> str:
        """The Human-First gate's own real effect: only an explicitly
        accepted Goal is ever persisted or becomes eligible to run — see
        _run_accepted_plan()'s own status check, the real enforcement
        point (TaskGraph.ready_tasks() itself does not distinguish
        PROPOSED from ACCEPTED, planning/task_graph.py's own
        _NON_TERMINAL_STATUSES).

        Sprint 6.14 hardening (scenario b): save_goal() is a write with
        no honest "empty" degrade the way a read has — a caller that
        silently swallowed a failed write here would go on to claim
        "I've saved your plan," a false success no less dishonest than a
        fabricated answer (the same reasoning memory/memory_store.py's
        own store() docstring already established for MemoryStoreError).
        Caught here, not inside TaskGraphStore itself, so the exact same
        honest reply already used for the store-absent case above covers
        the store-present-but-failing case too."""
        goal = self._pending_proposed_goal
        assert goal is not None  # only ever called from a not-None-guarded call site
        self._pending_proposed_goal = None
        if self._task_graph_store is None:
            return "I can't save that plan right now, but I'll remember it for this conversation."
        goal.status = PlanningStatus.ACCEPTED
        try:
            self._task_graph_store.save_goal(goal)
        except Exception:
            logger.exception("Failed to save an accepted plan %r.", goal.goal_id)
            return "I can't save that plan right now, but I'll remember it for this conversation."
        return f'Great — I\'ve saved your plan "{goal.statement}." Say "run my plan" when ready.'

    def _run_accepted_plan(
        self, session_id: str, persona_name: str, trace: DecisionTrace
    ) -> str:
        """Runs the most recently accepted Goal's own TaskGraph via
        TaskGraphWorkflowAdapter -> the existing, completely unmodified
        WorkflowExecutor — every step still goes through the same
        permission/confirmation/audit pipeline any other workflow does,
        never a privileged bypass (workflow/task_graph_adapter.py's own
        docstring).

        Sprint 6.14 hardening (scenario b's own adversarial-re-read
        finding): WorkflowStore.save() (item 27's own deliberately-
        unhardened write, since it had zero production callers until
        this sprint) now has a real one here — an uncaught failure would
        propagate to _handle_turn_complete()'s own outer catch and end
        the whole session, the identical coarse-degrade problem
        TaskGraphStore.save_goal() already had. Caught here rather than
        inside WorkflowStore itself, matching that same fix's own
        reasoning: a write has no honest "empty" degrade the way a read
        does."""
        if (
            self._task_graph_store is None
            or self._task_graph_workflow_adapter is None
            or self._workflow_store is None
        ):
            return "Running a plan isn't currently available."
        accepted_goals = self._task_graph_store.list_goals(status=PlanningStatus.ACCEPTED)
        if not accepted_goals:
            return "You don't have an accepted plan to run yet."
        goal = max(accepted_goals, key=lambda candidate: candidate.created_at)
        edges = self._task_graph_store.get_edges(goal.goal_id)
        task_graph = TaskGraph(goal, edges)
        if not task_graph.ready_tasks():
            return f'Your plan "{goal.statement}" has nothing left to run.'

        definition, originating_tasks = self._task_graph_workflow_adapter.build_workflow(
            task_graph, created_by=_PLANNING_REQUESTED_BY
        )
        try:
            self._workflow_store.save(definition)
        except Exception:
            logger.exception(
                "Failed to save workflow %r for an accepted plan.", definition.workflow_id
            )
            return "I couldn't set up your plan to run right now."
        context = ActionContext(
            requested_by=_PLANNING_REQUESTED_BY,
            persona_name=persona_name,
            session_id=session_id,
            decision_trace=trace,
        )
        run_result = self._workflow_executor.run(definition.workflow_id, context)
        self._finalize_workflow_run(run_result, task_graph, originating_tasks, goal)
        return _describe_workflow_result(run_result, goal.statement)

    def _resume_previous_session(
        self, session_id: str, persona_name: str, trace: DecisionTrace
    ) -> str:
        """A Knowledge-Graph-derived workflow (workflow/session_resumption.py)
        — no TaskGraph/Task involved, so _finalize_workflow_run() does not
        apply here (that method's own scope is explicitly TaskGraph-derived
        runs only, per this sprint's own Objectives).

        Sprint 6.14 hardening (scenario b's own adversarial-re-read
        finding): see _run_accepted_plan()'s own identical save()
        hardening docstring — the same real gap, the same fix."""
        if self._session_resumption is None or self._workflow_store is None:
            return "Resuming a session isn't currently available."
        definition = self._session_resumption.build_workflow(created_by=_PLANNING_REQUESTED_BY)
        if definition is None:
            return "I don't have a previous session to resume."
        try:
            self._workflow_store.save(definition)
        except Exception:
            logger.exception(
                "Failed to save workflow %r for a resumed session.", definition.workflow_id
            )
            return "I couldn't set up your session to resume right now."
        context = ActionContext(
            requested_by=_PLANNING_REQUESTED_BY,
            persona_name=persona_name,
            session_id=session_id,
            decision_trace=trace,
        )
        run_result = self._workflow_executor.run(definition.workflow_id, context)
        return _describe_workflow_result(run_result, definition.name)

    def _finalize_workflow_run(
        self,
        run_result: WorkflowRunResult,
        task_graph: TaskGraph,
        originating_tasks: list[Task],
        goal: Goal,
    ) -> None:
        """Wires a TaskGraph-derived WorkflowRunResult back onto the
        Task(s) that produced it (deferred by Sprint 6.9 to this sprint)
        and onward into SelfEvaluator.evaluate_workflow_run() (Sprint
        6.10). A skipped step (never dispatched at all — a prior step
        already aborted the run) leaves its own Task untouched, neither
        completed nor abandoned — it was never attempted, so it stays
        eligible for a future retry, rather than being marked as having
        failed. Every individual failure here is caught and logged, never
        allowed to turn a real, already-finished workflow run into a
        crashed turn — the run itself already happened; this is
        bookkeeping on top of it."""
        try:
            for step_result, task in zip(
                run_result.step_results, originating_tasks, strict=False
            ):
                if step_result.skipped:
                    continue
                if step_result.action_result.status is ActionStatus.SUCCEEDED:
                    task_graph.mark_completed(task.task_id)
                else:
                    task_graph.mark_failed(task.task_id)
            if self._task_graph_store is not None:
                self._task_graph_store.save_goal(goal)
        except Exception:
            logger.exception(
                "Failed to update the originating TaskGraph after a workflow run; "
                "the run itself already completed and is unaffected."
            )
        if self._self_evaluator is None:
            return
        try:
            self._self_evaluator.evaluate_workflow_run(run_result)
        except Exception:
            logger.exception(
                "SelfEvaluator.evaluate_workflow_run() failed; continuing without a "
                "recorded evaluation for this run."
            )

    def _handle_explanation_turn(self, trace: DecisionTrace) -> str:
        """Sprint 6.13. Resolves the subject of "why?" from the most
        recent NON-explanation turn's own DecisionTrace
        (lookup_last_decision_trace(), wired to ExplainabilityLayer via
        DecisionTraceLookupRelay in main.py) — a real, disclosed scope
        limit: this never resolves a specific Goal/Task/EvaluationRecord
        subject, only the prior turn's own routing decision, per this
        sprint's own Potential Risks ("resolving which prior subject the
        user means is Sprint 6.13's own... job" — done here at the
        single-most-recent-trace granularity, not a richer one).

        Sprint 6.14 hardening (scenario a): explain() falls through to
        ReasoningEngine.explain_why() (reasoning/explainability.py's own
        docstring) whenever _gather() finds nothing composable for the
        subject, and explain_why() raises LlmError by design (6.4) when
        Ollama is unreachable — a real gap this method left uncaught
        until now, unlike _propose_new_goal()'s already-correct identical
        shape. Left uncaught, this would fall through to
        _handle_turn_complete()'s own outer catch and end the whole
        session (SessionEndReason.ERROR) rather than just this one turn
        degrading — far coarser than intended."""
        if self._explainability_layer is None:
            return "I can't explain my reasoning right now."
        working_context = None
        if self._context_engine is not None:
            try:
                working_context = self._context_engine.build(
                    self._last_session_id, self._persona_manager.active_persona().name
                )
            except Exception:
                logger.exception(
                    "ContextEngine.build() failed for an explanation turn; continuing "
                    "without additional context."
                )
        request = ExplanationRequest(
            subject_id=_MOST_RECENT_TRACE_SUBJECT_ID, subject_kind="decision_trace"
        )
        try:
            explanation = self._explainability_layer.explain(request, working_context)
        except LlmError:
            logger.exception("ExplainabilityLayer.explain() failed for %r.", trace)
            return "I can't reach my reasoning model right now."
        return explanation.narrative

    def lookup_last_decision_trace(self, subject_id: str) -> DecisionTrace | None:
        """The real target DecisionTraceLookupRelay's own .target is
        pointed at (main.py, once this pipeline exists) — subject_id is
        accepted per ExplainabilityLayer's own Callable[[str], ...]
        contract but ignored, since this class tracks only the single
        most recent trace, never a keyed history (see
        _last_decision_trace's own docstring)."""
        return self._last_decision_trace

    def _check_and_announce_priority_item(self) -> None:
        """Sprint 4.18 (as _check_and_announce_due_reminder), renamed and
        widened Sprint 5.24 into a real, exhaustive three-source
        dispatcher, and Sprint 6.13 to a full five-source one — this
        project's first genuinely PROACTIVE (JARMINEI-initiated, not
        turn-triggered) behavior. TaskScheduler job body (registered in
        start(), on scheduler_config.poll_interval_seconds). See this
        module's own docstring for the full wiring diagram and
        Architecture Notes for the real concurrency discipline this
        method's own call ordering exists to satisfy.

        _maybe_enqueue_wellness_prompt() runs unconditionally, even while
        a live session is ACTIVE — Part 2's own "Queued" language applies
        equally to detection (a due wellness trigger should still be
        recorded) and to announcement (only the announcement itself waits
        for DORMANT below), the identical distinction the peek-before-pop
        discipline already draws for SCHEDULED_REMINDER.

        Part 2's own Priority Queue "Queued" language is explicit for
        every source: a due item found while a session is already ACTIVE
        is left untouched in the queue (peek_next(), not popped) rather
        than interrupting; the next poll checks again. self._priority_item_
        handlers is now exhaustive over every PriorityLevel this Sprint
        Book gives a real producer to (SCHEDULED_REMINDER, WELLNESS,
        GENERAL_SUGGESTION, IMPORTANT_ALERT — closing backlog/
        technical_debt.md item 17 in full), so an unrecognized one logs a
        warning and stays queued instead — structurally unreachable today,
        kept as a real, disclosed defensive floor.

        Sprint 6.13: consults AdaptivePrioritizer.next_item() (Sprint
        6.12) — which itself calls peek_next() internally — INSTEAD of
        peek_next() directly, when available, so this DORMANT-gated
        window is also where a soft item can be judged genuinely still
        "recently active enough" to defer a little longer even though
        the literal voice session already ended (see decision/
        adaptive_prioritizer.py's own docstring for why
        conversation_active_threshold_seconds is deliberately a much
        longer window than voice.session_timeout_seconds' own). Only a
        SURFACE_NOW decision proceeds to pop_next()/announce; DEFER_
        BRIEFLY/HOLD leave the item queued for the next natural poll,
        adding no new timer of its own. Falls back to the pre-6.12 direct
        peek_next() behavior whenever adaptive_prioritizer/context_engine
        is absent — the Level 6 Part A degrade-to-absent discipline
        applied at this exact integration boundary, per this sprint's own
        Expected Functions text."""
        self._maybe_enqueue_wellness_prompt()

        if self._quiet_mode_controller.current_mode() is not OperatingMode.DORMANT:
            return

        peeked = self._peek_next_priority_item()
        if peeked is None:
            return
        handler = self._priority_item_handlers.get(peeked.priority)
        if handler is None:
            logger.warning(
                "PriorityLevel %s has no real announcement handler yet; leaving it queued.",
                peeked.priority,
            )
            return
        item = self._priority_queue_manager.pop_next()
        handler(item)

    def _peek_next_priority_item(self) -> PriorityItem | None:
        """The pre-6.12 behavior (a plain peek_next()) whenever
        adaptive_prioritizer/context_engine is absent; otherwise defers
        to AdaptivePrioritizer.next_item()'s own situational judgment,
        returning the peeked item only on SURFACE_NOW. A
        ContextEngine.build() failure degrades to the plain peek_next()
        fallback too, rather than losing the queue's own next item for
        this whole tick."""
        if self._adaptive_prioritizer is None or self._context_engine is None:
            return self._priority_queue_manager.peek_next()
        try:
            working_context = self._context_engine.build(
                self._last_session_id, self._persona_manager.active_persona().name
            )
        except Exception:
            logger.exception(
                "ContextEngine.build() failed during priority-item arbitration; falling "
                "back to a plain peek_next()."
            )
            return self._priority_queue_manager.peek_next()
        result = self._adaptive_prioritizer.next_item(working_context)
        if result is None:
            return None
        item, decision = result
        if decision is not PrioritizationDecision.SURFACE_NOW:
            return None
        return item

    def _announce_scheduled_reminder(self, item: PriorityItem) -> None:
        """Sprint 4.18, extracted unchanged from the old
        _check_and_announce_due_reminder() as part of this sprint's own
        dispatch-table widening."""
        scheduled_item: ScheduledItem = item.payload
        persona = self._persona_manager.active_persona()
        self._quiet_mode_controller.activate(
            ActivationReason.SCHEDULED_ALERT,
            announce_first=(scheduled_item.title, persona.voice_id),
        )

    def _announce_wellness(self, item: PriorityItem) -> None:
        """Sprint 5.24. Part 2's own "Owned exclusively by Minie" language
        (stronger than anything said about reminders/suggestions) is why
        this is the one announcement source that force-switches persona:
        select(..., SwitchReason.WELLNESS) -> speak -> resume_previous(),
        the lighter select()/resume_previous() pair (unchanged since
        Sprint 2.11), never Sprint 5.10's full seven-phase
        TransitionEngine — a wellness announcement is a brief, single-
        utterance interruption, the same reasoning Sprint 4.18's own
        SCHEDULED_ALERT announcements never invoking TransitionEngine
        already established. select() failing here (unlikely given
        WELLNESS's own now-elevated priority rank — see personas/
        persona_manager.py's own module docstring for this sprint's
        disclosed reordering) degrades to announcing through whichever
        persona IS active rather than crashing this job; resume_previous()
        is only called when select() actually applied, so a refused
        switch never wrongly restores an unrelated older state.

        Sprint 5.25 hardening (scenario e): the force-switch/announce/
        resume sequence is now wrapped in a single try/except/finally —
        a real induced failure anywhere in that sequence (select() itself
        raising, or a later step raising after a switch already applied)
        is logged and absorbed rather than propagating, and the finally
        block guarantees resume_previous() still runs whenever switched
        is True, so PersonaManager can never be left stuck on Minie.
        When select() itself is what fails, switched stays False and
        resume_previous() is correctly never attempted. Mirrors
        presentation/lip_sync.py's own Sprint 5.11 "one mechanism, one
        try/finally, guaranteeing the cleanup call regardless of how the
        body failed" precedent."""
        prompt: WellnessPrompt = item.payload
        switched = False
        try:
            switched = self._persona_manager.select("minie", SwitchReason.WELLNESS)
            persona = self._persona_manager.active_persona()
            self._quiet_mode_controller.activate(
                ActivationReason.SCHEDULED_ALERT,
                announce_first=(prompt.message, persona.voice_id),
            )
        except Exception:
            logger.exception(
                "Wellness announcement failed; resuming previous persona if the "
                "switch was already applied, never leaving PersonaManager stuck."
            )
        finally:
            if switched:
                self._persona_manager.resume_previous()
        self._pending_wellness_trigger_types.discard(prompt.trigger_type)
        if self._wellness_escalation_manager is not None:
            self._wellness_escalation_manager.register_prompt_shown(prompt.trigger_type)

    def _announce_general_suggestion(self, item: PriorityItem) -> None:
        """Sprint 5.24. Announced through whichever persona is already
        active, unchanged — like SCHEDULED_REMINDER, and unlike WELLNESS,
        a suggestion never force-switches persona (Part 2 names no such
        requirement for it).

        Sprint 6.13 correction: a real, previously-latent bug, found by
        checking the actual code rather than trusting Sprint 6.8's own
        claim that "the existing dispatch table needs no change" —
        GENERAL_SUGGESTION now has TWO real producers with two DIFFERENT
        payload shapes (RecommendationEngine's own Recommendation.text;
        ProactiveAssistant's own three "softer trigger" ProactivePrompt.
        message, Sprint 6.8), and this method only ever read
        `.text` — an AttributeError against any ProactiveAssistant-sourced
        item the moment that producer went live, which it does for real
        for the first time in this sprint. Fixed via the shared
        _extract_announcement_text() helper below."""
        persona = self._persona_manager.active_persona()
        self._quiet_mode_controller.activate(
            ActivationReason.SCHEDULED_ALERT,
            announce_first=(_extract_announcement_text(item.payload), persona.voice_id),
        )

    def _announce_important_alert(self, item: PriorityItem) -> None:
        """Sprint 6.13 — IMPORTANT_ALERT's first real announcement
        handler, closing backlog/technical_debt.md item 17 in full (a
        real producer alone, since Sprint 6.8, was not the same as a
        real end-to-end announced path — this method is the missing
        other half). Announced through whichever persona is already
        active, unchanged — like SCHEDULED_REMINDER/GENERAL_SUGGESTION,
        and unlike WELLNESS, an alert never force-switches persona (Part
        2 names no such requirement for it, and ProactiveAssistant's own
        three IMPORTANT_ALERT triggers — UPCOMING_DEADLINE/BATTERY_
        CRITICAL/FORGOTTEN_REMINDER — are all informational in nature,
        not a companion-relationship moment the way a wellness check-in
        is)."""
        persona = self._persona_manager.active_persona()
        self._quiet_mode_controller.activate(
            ActivationReason.SCHEDULED_ALERT,
            announce_first=(_extract_announcement_text(item.payload), persona.voice_id),
        )

    def _maybe_enqueue_wellness_prompt(self) -> None:
        """Sprint 5.24 — the real WellnessTracker.evaluate_triggers() ->
        PriorityQueueManager.enqueue() step this module's own docstring
        names but wellness_tracker.py itself cannot own (it has no
        PriorityQueueManager dependency, and is outside this sprint's own
        Files to Modify) — a real, disclosed gap this class fills
        instead, the only place in the whole graph that legitimately can.

        Deduplicated per still-crossed trigger type via
        _pending_wellness_trigger_types (cleared once the prompt is
        actually announced, in _announce_wellness() above) —
        evaluate_triggers() is a pure read with no "already enqueued"
        memory of its own, so without this dedup the same still-crossed
        trigger would be re-enqueued as a fresh duplicate PriorityItem on
        every single poll until it's actually announced."""
        if self._wellness_tracker is None:
            return
        overrides = (
            self._adaptive_wellness_adjuster.compute_overrides()
            if self._adaptive_wellness_adjuster is not None
            else None
        )
        prompt = self._wellness_tracker.evaluate_triggers(interval_overrides=overrides)
        if prompt is None or prompt.trigger_type in self._pending_wellness_trigger_types:
            return
        self._pending_wellness_trigger_types.add(prompt.trigger_type)
        self._priority_queue_manager.enqueue(
            prompt, PriorityLevel.WELLNESS, source="wellness_tracker"
        )

    def _generate_and_enqueue_recommendations(self) -> None:
        """Sprint 5.24. RecommendationEngine.generate_recommendations() is
        deliberately stateless/idempotent (learning/recommendation.py's
        own docstring, which explicitly defers deduplication to "Sprint
        5.24's own live-caller concern") — deduplicated here per
        based_on_pattern_id (stable across calls, unlike each call's own
        fresh recommendation_id) via _enqueued_recommendation_pattern_ids."""
        if self._recommendation_engine is None:
            return
        for recommendation in self._recommendation_engine.generate_recommendations():
            if recommendation.based_on_pattern_id in self._enqueued_recommendation_pattern_ids:
                continue
            self._enqueued_recommendation_pattern_ids.add(recommendation.based_on_pattern_id)
            self._priority_queue_manager.enqueue(
                recommendation, PriorityLevel.GENERAL_SUGGESTION, source="recommendation_engine"
            )

    def _run_runtime_housekeeping(self) -> None:
        """Runtime Phase 9 (Runtime Refactor Sprint) — the one real
        periodic caller of RuntimeManager's own idle-timeout/resource-
        pressure eviction mechanism (core/runtime_manager.py's own
        sweep_idle_services()/evict_least_recently_used() docstrings).

        Idle-timeout sweep runs every tick, unconditionally — cheap (a
        handful of in-memory comparisons across today's 3 lazy=True
        services, no I/O of its own). Resource-pressure eviction only
        runs when ResourceMonitor.is_over_threshold() reports a real
        warning-level breach, and evicts exactly one service per tick
        (the least-recently-used) rather than every eligible service at
        once — the same gradual, re-checked-every-tick approach as
        letting the sweep run again next tick if pressure is still high,
        rather than risking evicting several services on a single
        transient spike."""
        evicted_idle = self._runtime_manager.sweep_idle_services()
        if evicted_idle:
            logger.info("Runtime housekeeping: idle-timeout evicted %s.", evicted_idle)
        snapshot = self._resource_monitor.sample()
        if self._resource_monitor.is_over_threshold(snapshot):
            evicted_pressure = self._runtime_manager.evict_least_recently_used(1)
            if evicted_pressure:
                logger.warning(
                    "Runtime housekeeping: resource-pressure evicted %s.", evicted_pressure
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
