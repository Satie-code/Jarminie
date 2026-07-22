"""Authority Evaluation & Engine Selection — the Decision Engine
pipeline's final two stages, per 02_System_Architecture.md: "... ->
Priority Evaluation -> **Authority Evaluation -> Engine Selection** ->
Execution -> Response Generation." Closes Phase 3.3 (Decision Engine).

Authority levels (Part 2's three-level Authority System):

    1  INFORM             - wired: plain informational answers
    2  RECOMMEND          - wired: suggest/recommend, never auto-act
    3  EMERGENCY_ASSIST    - structurally unreachable at Level 3 (see below)

Engine selections (the first four have a real handler as of Sprint 4.11;
every other value exists so a future Level only needs to add a handler,
never modify this enum):

    CONVERSATIONAL_RESPONSE  - wired: Persona.compose_reply() (2.9/2.10)
    INFORM_ONLY              - wired: plain factual answer, no persona flavor
    DEVICE_CONTROL           - wired: CommunicationPipeline._handle_device_control_turn() (4.11)
    WORKFLOW                 - wired: CommunicationPipeline._handle_workflow_turn() (4.11)
    SCHEDULER                - reserved: Level 4 (Scheduler)
    INTERNET_AGENT           - reserved: Level 4 (Internet Agent)
    WELLNESS                 - reserved: Level 5 (Wellness Engine)
    EMOTION_SUPPORT          - reserved: Level 5 (Emotion Engine)

DEVICE_CONTROL/WORKFLOW routing (Sprint 4.11, _determine_engine()):
an ACTION_REQUEST intent routes to one of them only when
ContextAnalysis.mentioned_entities names a concrete, nameable target —
no entity means no route, falling back to CONVERSATIONAL_RESPONSE
(the same honest "I can't tell what to act on" capability gap the old
reserved-engine wording used to describe, now narrower since the
capability itself is real). Whether the named target is a stored
workflow rather than a plain application/file target is decided by a
small, literal keyword check against the raw transcript ("workflow",
"routine", "automation", "sequence") — deliberately not a live
existence check against WorkflowStore/an installed-application list:
this method's only job is ROUTING, not authorization. Real existence
and permission enforcement happen downstream, exactly where they
already lived before this sprint — CommunicationPipeline resolves the
named target for real (WorkflowStore lookup by name; ActionRegistry.
dispatch()'s existing PermissionGate/ActionResourceGate stack) and
degrades to an honest spoken "couldn't find/run that" if the routing
guess doesn't pan out, never a crash. See this module's own
_resolve_action_engine()'s docstring, and sprint_4_11.md's Architecture
Notes for the full reasoning behind this routing/enforcement split.

EMERGENCY_ASSIST is structurally unreachable at Level 3 by design, not
an oversight: Part 2 requires emergency actions to be limited to
"previously approved emergency procedures." AuthorityEvaluator enforces
this as a default-deny whitelist (approved_emergency_procedures, empty
by default) rather than a default-allow path guarded by exceptions —
every EMERGENCY_ASSIST-eligible request degrades to RECOMMEND until the
whitelist is populated with real, reviewed procedure ids.

**Still deliberately empty as of Sprint 4.7 (Permission & Confirmation
System), reviewed and explicitly deferred, not an oversight.** Device
Control (Level 4, Sprints 4.1-4.6) now exists, but nothing in the
codebase wires EMERGENCY_ASSIST authority to any real automated action
yet: _determine_engine() below always returns CONVERSATIONAL_RESPONSE/
INFORM_ONLY regardless of authority_level, and no ActionType exists for
anything resembling a real emergency-response procedure (e.g. a safe
shutdown). Approving a procedure id today would be symbolic only, with
no real capability behind it — a false sense of readiness, not a real
safety improvement. Revisit once real Device-Control-to-Authority
wiring exists (Sprint 4.11 or later) and a concrete emergency-response
ActionType is actually built to back a real procedure id. See
sprint_4_7.md's own Sprint Completion Report for the full reasoning.

The whitelist is checked against a normalized form of
ContextAnalysis.primary_topic as the "procedure id" — evaluate()'s own
signature has no separate procedure-id parameter, and primary_topic is
the only available description of what the request is actually about.
This is a genuine implementation-time decision (not spelled out by this
sprint's own spec), harmless at Level 3 since the whitelist is always
empty regardless of what string is checked against it.

selected_engine is CONVERSATIONAL_RESPONSE, INFORM_ONLY, DEVICE_CONTROL,
or WORKFLOW in the real returned DecisionTrace as of Sprint 4.11 — never
one of the four still-reserved values above, even when a reserved
engine would ideally be the destination (e.g. an EMOTIONAL_SUPPORT
intent "really" belongs to Wellness) — that inference is recorded only
in reasoning_text, worded as an honest capability gap ("this looks like
X, which doesn't exist yet"), never as if the request were actually
routed there.

Sprint 3.13 hardening (scenario e): evaluate()'s own body is wrapped in
a try/except — any internal exception (a malformed input, a bug in
_determine_authority()/_determine_engine()/_build_reasoning()) resolves
to AuthorityLevel.INFORM/EngineSelection.INFORM_ONLY, never anything
more permissive than clean inputs would have produced. Fail
safe-DOWN, never safe-up.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from core.logging_setup import get_logger
from decision.context_analyzer import ContextAnalysis
from decision.models import Intent, IntentCategory
from decision.priority_queue import PriorityLevel
from memory.retrieval_engine import RetrievedMemory

logger = get_logger(__name__)


class AuthorityLevel(Enum):
    """Part 2's three authority levels, exact numbering."""

    INFORM = 1
    RECOMMEND = 2
    EMERGENCY_ASSIST = 3


class EngineSelection(Enum):
    """Every engine Part 2's full architecture names. Only the first two
    are wired at Level 3 — see this module's own docstring."""

    CONVERSATIONAL_RESPONSE = "conversational_response"
    INFORM_ONLY = "inform_only"
    DEVICE_CONTROL = "device_control"
    WORKFLOW = "workflow"
    SCHEDULER = "scheduler"
    INTERNET_AGENT = "internet_agent"
    WELLNESS = "wellness"
    EMOTION_SUPPORT = "emotion_support"


@dataclass
class DecisionTrace:
    """Every input that fed one decision, plus a human-readable
    justification — the Explainability Rule's own deliverable, built as
    a first-class part of this sprint rather than reconstructed later
    from raw scores."""

    intent: Intent
    context_analysis: ContextAnalysis
    retrieved_memories: list[RetrievedMemory]
    priority_level: PriorityLevel
    authority_level: AuthorityLevel
    selected_engine: EngineSelection
    reasoning_text: str
    decided_at: datetime


# intent.category -> the engine that would ideally handle this request,
# once it exists. Only categories with a genuine future-capability gap
# appear here — categories already well-served by CONVERSATIONAL_
# RESPONSE/INFORM_ONLY (MEMORY_RECALL, CASUAL_CONVERSATION, UNKNOWN,
# INFORMATIONAL, EMERGENCY) are deliberately absent. ACTION_REQUEST is
# no longer here as of Sprint 4.11 — Device Control is a real,
# resolvable engine now (see _resolve_action_engine()), not merely an
# inferred future one; an unresolvable ACTION_REQUEST (no concrete
# target) gets its own honest wording directly in _build_reasoning()
# instead of this generic "doesn't exist yet" table.
_INFERRED_FUTURE_ENGINE: dict[IntentCategory, EngineSelection] = {
    IntentCategory.EMOTIONAL_SUPPORT: EngineSelection.WELLNESS,
}

_WORKFLOW_KEYWORDS: tuple[str, ...] = ("workflow", "routine", "automation", "sequence")
"""Substrings in the raw transcript that indicate an ACTION_REQUEST names
a stored *workflow* rather than a single device-control target (an
application, a file/folder) — checked only after mentioned_entities
already proves a concrete target exists at all. A small, literal
keyword set, not NLU — matching this project's consistent plain-match
discipline for this exact class of routing decision (e.g.
PersonaManager's trigger phrases, ConfidenceScorer's override phrases)."""

_ENGINE_DISPLAY_NAMES: dict[EngineSelection, str] = {
    EngineSelection.DEVICE_CONTROL: "Device Control",
    EngineSelection.WORKFLOW: "the Workflow Engine",
    EngineSelection.SCHEDULER: "the Scheduler",
    EngineSelection.INTERNET_AGENT: "the Internet Agent",
    EngineSelection.WELLNESS: "the Wellness Engine",
    EngineSelection.EMOTION_SUPPORT: "the Emotion Engine",
}

_RECOMMEND_INTENT_CATEGORIES = frozenset({IntentCategory.ACTION_REQUEST, IntentCategory.EMERGENCY})


class AuthorityEvaluator:
    """Constructor DI: receives the pre-approved emergency procedure
    whitelist (empty by default at Level 3). The parameter exists now so
    Level 4 (Device Control) can inject real procedure ids without
    changing this class's signature — see this module's own docstring."""

    def __init__(self, approved_emergency_procedures: frozenset[str] = frozenset()) -> None:
        self._approved_emergency_procedures = approved_emergency_procedures

    def start(self) -> None:
        logger.info("Authority Evaluator started.")

    def stop(self) -> None:
        logger.info("Authority Evaluator stopped.")

    def health_check(self) -> bool:
        """Always reports healthy (True) — a non-empty whitelist at
        Level 3 is unusual (nothing yet is meant to populate it) but not
        itself a failure, since Level 4+ genuinely will populate this;
        logged as a warning purely for visibility."""
        if self._approved_emergency_procedures:
            logger.warning(
                "AuthorityEvaluator has a non-empty approved_emergency_procedures "
                "whitelist — expected only from Level 4 (Device Control) onward."
            )
        return True

    def evaluate(
        self,
        intent: Intent,
        context_analysis: ContextAnalysis,
        retrieved_memories: list[RetrievedMemory],
        priority_level: PriorityLevel,
    ) -> DecisionTrace:
        """Sprint 3.13 hardening (scenario e): must fail safe-down, never
        safe-up — any exception raised anywhere in this method's own body
        (a malformed input, a bug in a helper) resolves to the lowest,
        safest AuthorityLevel/EngineSelection pair (INFORM/INFORM_ONLY)
        rather than propagating or defaulting to anything more
        permissive. This is Human First + Reliability over Intelligence
        applied mechanically: a broken decision engine must become more
        cautious, not less."""
        try:
            authority_level, emergency_approved = self._determine_authority(
                intent, context_analysis, priority_level
            )
            selected_engine = self._determine_engine(intent, context_analysis)
            reasoning_text = _build_reasoning(
                intent,
                priority_level,
                authority_level,
                emergency_approved,
                selected_engine,
                retrieved_memories,
            )
        except Exception:
            logger.exception(
                "AuthorityEvaluator.evaluate() failed internally; defaulting to the "
                "safest response."
            )
            authority_level = AuthorityLevel.INFORM
            selected_engine = EngineSelection.INFORM_ONLY
            reasoning_text = (
                "Decision Engine encountered an internal error; defaulting to the "
                "safest response."
            )
        return DecisionTrace(
            intent=intent,
            context_analysis=context_analysis,
            retrieved_memories=retrieved_memories,
            priority_level=priority_level,
            authority_level=authority_level,
            selected_engine=selected_engine,
            reasoning_text=reasoning_text,
            decided_at=datetime.now(UTC),
        )

    def explain(self, trace: DecisionTrace) -> str:
        """Renders reasoning_text plus a structured summary of every
        retrieved memory's own retrieval_reason (Sprint 3.9) — the
        literal function a future "why?" query would call (not wired to
        a live trigger in this sprint)."""
        lines = [trace.reasoning_text]
        if trace.retrieved_memories:
            lines.append("Memories considered:")
            lines.extend(f"- {memory.retrieval_reason}" for memory in trace.retrieved_memories)
        else:
            lines.append("No memories were retrieved for this decision.")
        return "\n".join(lines)

    def _determine_authority(
        self, intent: Intent, context_analysis: ContextAnalysis, priority_level: PriorityLevel
    ) -> tuple[AuthorityLevel, bool]:
        if priority_level == PriorityLevel.CRITICAL_EMERGENCY:
            procedure_id = context_analysis.primary_topic.strip().lower()
            if procedure_id and procedure_id in self._approved_emergency_procedures:
                return AuthorityLevel.EMERGENCY_ASSIST, True
            return AuthorityLevel.RECOMMEND, False
        if intent.category in _RECOMMEND_INTENT_CATEGORIES:
            return AuthorityLevel.RECOMMEND, False
        return AuthorityLevel.INFORM, False

    def _determine_engine(
        self, intent: Intent, context_analysis: ContextAnalysis
    ) -> EngineSelection:
        if intent.category == IntentCategory.INFORMATIONAL:
            return EngineSelection.INFORM_ONLY
        if intent.category == IntentCategory.ACTION_REQUEST:
            resolved = self._resolve_action_engine(intent, context_analysis)
            if resolved is not None:
                return resolved
        return EngineSelection.CONVERSATIONAL_RESPONSE

    def _resolve_action_engine(
        self, intent: Intent, context_analysis: ContextAnalysis
    ) -> EngineSelection | None:
        """Deliberately narrow, per sprint_4_11.md's own Architecture
        Notes: a concrete, nameable target (context_analysis.
        mentioned_entities non-empty) is required before routing to
        DEVICE_CONTROL/WORKFLOW at all — no target means None (the
        caller falls back to CONVERSATIONAL_RESPONSE), never a guess.
        This is a routing decision only — real existence (is this
        actually a stored, enabled workflow? an installed application?)
        is deliberately NOT checked here, since this class has no live
        dependency on WorkflowStore or any Device Control module by
        design (keeping the Decision Engine's own dependency-light
        precedent intact). CommunicationPipeline resolves the named
        target for real and degrades gracefully (an honest "couldn't
        find/run that" spoken reply) if this routing guess doesn't pan
        out — the same "routing is cheap, real enforcement happens
        downstream" split PermissionGate already established for
        authorization vs. ActionRegistry.dispatch()."""
        if not context_analysis.mentioned_entities:
            return None
        lowered_transcript = intent.raw_transcript.lower()
        if any(keyword in lowered_transcript for keyword in _WORKFLOW_KEYWORDS):
            return EngineSelection.WORKFLOW
        return EngineSelection.DEVICE_CONTROL


def _build_reasoning(
    intent: Intent,
    priority_level: PriorityLevel,
    authority_level: AuthorityLevel,
    emergency_approved: bool,
    selected_engine: EngineSelection,
    retrieved_memories: list[RetrievedMemory],
) -> str:
    parts = [f"Classified as {intent.category.name} with {priority_level.name} priority."]

    if priority_level == PriorityLevel.CRITICAL_EMERGENCY and not emergency_approved:
        parts.append(
            "This looks like an emergency, but no pre-approved emergency procedures "
            "exist yet at this level of the system, so I can only recommend rather "
            "than act automatically."
        )
    elif authority_level is AuthorityLevel.EMERGENCY_ASSIST:
        parts.append(
            "This matches a pre-approved emergency procedure, so I'm authorized to assist directly."
        )
    elif authority_level is AuthorityLevel.RECOMMEND:
        parts.append("This looks like something to recommend or suggest, not just inform about.")
    else:
        parts.append("This is best handled as a plain informational response.")

    if selected_engine is EngineSelection.DEVICE_CONTROL:
        parts.append(
            "This names a concrete target, so I'll carry it out directly via "
            f"{_ENGINE_DISPLAY_NAMES[EngineSelection.DEVICE_CONTROL]}."
        )
    elif selected_engine is EngineSelection.WORKFLOW:
        parts.append(
            "This names a stored workflow, so I'll run it directly via "
            f"{_ENGINE_DISPLAY_NAMES[EngineSelection.WORKFLOW]}."
        )
    elif intent.category is IntentCategory.ACTION_REQUEST:
        device_control_name = _ENGINE_DISPLAY_NAMES[EngineSelection.DEVICE_CONTROL]
        parts.append(
            f"This looks like a request for {device_control_name}, but I couldn't "
            "identify a specific target (an application, file, or workflow name) to "
            "act on, so I'll respond conversationally instead."
        )
    else:
        future_engine = _INFERRED_FUTURE_ENGINE.get(intent.category)
        if future_engine is not None:
            display_name = _ENGINE_DISPLAY_NAMES[future_engine]
            parts.append(
                f"This looks like a task for {display_name}, which doesn't exist yet at "
                "this level of the system - answering conversationally instead."
            )

    if retrieved_memories:
        count = len(retrieved_memories)
        noun = "memory" if count == 1 else "memories"
        parts.append(f"Drew on {count} retrieved {noun} to inform this response.")

    return " ".join(parts)
