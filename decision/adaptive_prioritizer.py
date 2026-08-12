"""Adaptive Prioritization — the dynamic, situational arbitration layer
above Sprint 3.10's fixed `PriorityLevel` ordering, deciding not just
"what rank is this" but "should this actually interrupt what's happening
right now." See docs/sprint_book/sprint_6/sprint_6_12.md.

Extends `decision/` (not a new top-level package) — the direct sibling
of `decision/decision_engine_v2.py` (Sprint 6.5) within the same
package.

**`AdaptivePrioritizer` judges, it never dequeues or dispatches.**
`next_item()` calls `PriorityQueueManager.peek_next()` (existing,
non-consuming) and returns a decision only — it never calls `pop_next()`
itself and never speaks. `PriorityQueueManager`'s own fixed
`PriorityLevel` ordering is never overridden or re-sorted; this class
sits in front of it, answering a narrower question that queue was never
designed to answer. The actual "pop and announce" stays exactly where it
already lives (`voice/pipeline.py`'s `_check_and_announce_priority_item()`,
wired at Sprint 6.13) — this mirrors `DecisionEngineV2`'s own identical
"rank/judge, never dispatch" boundary (Sprint 6.5) exactly.

**`PriorityLevel.CRITICAL_EMERGENCY` always resolves `SURFACE_NOW`,
unconditionally, checked first and never reachable by any other branch
below.** This is hard-coded, not config-driven or situationally
overridable by any signal this module introduces — a deliberate,
load-bearing safety property; Level 6's own principles would be violated
by any construction that let a "the user seems busy" heuristic delay a
genuine emergency.

**A real, disclosed interpretive resolution of this sprint file's own
internally inconsistent text.** Its Expected Functions prose names two
different thresholds for "always surfaces regardless of context" in two
adjacent sentences: the active-conversation branch says "SURFACE_NOW for
IMPORTANT_ALERT" (implying only IMPORTANT_ALERT-and-above always
surfaces during a conversation), while the no-conversation branch says
"SURFACE_NOW for anything at SCHEDULED_REMINDER or above" (a lower,
more inclusive threshold). Resolved toward the single, internally
consistent threshold — SCHEDULED_REMINDER-and-above always resolves
SURFACE_NOW regardless of conversation state — both because a scheduled
reminder is, by its own real-world nature, time-critical enough to
still warrant interrupting a conversation (unlike WELLNESS/
GENERAL_SUGGESTION's genuinely softer content), and because a single
uniform threshold is a more defensible design than two different ones
for functionally the same question. Only `WELLNESS`/`GENERAL_SUGGESTION`
can ever resolve `DEFER_BRIEFLY` or `HOLD`.

**Two real, necessary constructor/config additions beyond this sprint
file's own literal text, both disclosed the same way `TaskGraph`'s own
`planning_config` addition (Sprint 6.2) and `ExplainabilityLayer`'s own
`reasoning_config` addition (Sprint 6.11) already were**:

1. This sprint file's own literal Expected Classes constructor —
   `(priority_queue_manager, decision_engine_v2, decision_engine_config)`
   — has no way to actually produce "decision_engine_v2's own confidence
   signal (via a ReasoningEngine-backed estimate on the item's own
   description)": `DecisionEngineV2`'s real, current public API
   (`rank_actions()`/`requires_confirmation()`/`suggest_alternatives()`)
   only ever accepts an `ActionRequest`, and a queued `PriorityItem`'s own
   payload (an `Intent`, a `ResourceAlert`, a `ProactivePrompt`, a
   `Recommendation`...) is never one — nothing in this sprint's own Files
   to Modify authorizes widening `decision_engine_v2.py` to expose a raw
   confidence-over-text method. Resolved by accepting `decision_engine_v2`
   exactly as the literal signature requires (genuinely unused by
   `next_item()` — the fifth instance of this Book's own "accepted but
   not yet consumed" pattern: Sprint 6.5's `authority_evaluator`, Sprint
   6.8's `decision_engine_v2`/`pattern_recognizer`, Sprint 6.10's
   `evaluation_timeout_seconds`, Sprint 6.11's `ranked_action` resolution
   gap) and adding a fourth, disclosed parameter, `reasoning_engine:
   ReasoningEngine`, used directly for the one real confidence check this
   sprint's own low-confidence `HOLD` branch needs.
2. `DecisionEngineConfig` gains two further fields beyond this sprint
   file's own named `active_conversation_defer_seconds`/
   `low_battery_boost_threshold_percent`: `conversation_active_threshold_
   seconds` (nothing in `ConversationContext` (Sprint 2.8) itself marks a
   session "still active" — only `last_activity_at`, requiring a real
   threshold this sprint's own text never assigns a config field to) and
   `low_confidence_hold_threshold` (the numeric cutoff behind "confidence
   ... is low," likewise never assigned one). See config/schema.py's own
   `DecisionEngineConfig` docstring for the full reasoning.

**`active_conversation_defer_seconds` is genuinely consumed by
`next_item()` itself, not merely accepted-but-unused**, via a small,
disclosed quality improvement beyond this sprint file's own literal
minimum: `PrioritizationDecision.DEFER_BRIEFLY`'s own docstring says
"wait up to `active_conversation_defer_seconds`, then re-check" — this
sprint's own Integration Considerations text says the *caller* (Sprint
6.13's poll loop) is what re-checks, adding no new timer here — but
`PriorityItem.enqueued_at` (Sprint 3.10) already exists, so `next_item()`
mechanically compares it against `active_conversation_defer_seconds` on
every call: a soft item that has been sitting deferred longer than that
window resolves `SURFACE_NOW` even if the conversation is technically
still active, rather than deferring it forever across repeated polls.
This changes no Acceptance Criteria (each is tested "all else equal"
against a freshly-enqueued item, safely inside the defer window) — a
disclosed exceed-scope-on-quality addition, not a silently-unused field.

**A related, disclosed design decision on the low-battery boost**: every
real, current power-relevant producer in this codebase
(`device_control/resource_gate.py`'s battery `ResourceAlert`,
`proactive/proactive_assistant.py`'s `BATTERY_CRITICAL` `ProactivePrompt`)
already enqueues at `IMPORTANT_ALERT`, a level that already always
resolves `SURFACE_NOW` regardless of conversation state per the rule
above — meaning the boost is a structural no-op against every payload
this codebase can produce today. The boost check is nonetheless applied
unconditionally, before the priority-level checks, so the mechanism
itself is real and independently verified (via a constructed test case
at a lower priority) rather than a phantom rule that never actually
fires against any input this codebase can construct.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from core.logging_setup import get_logger
from core.resource_monitor import ResourceAlert
from decision.llm_client import LlmError
from decision.priority_queue import PriorityLevel
from proactive.proactive_model import ProactivePrompt, ProactiveTriggerType

if TYPE_CHECKING:
    from config.schema import DecisionEngineConfig
    from context.context_model import WorkingContext
    from decision.decision_engine_v2 import DecisionEngineV2
    from decision.priority_queue import PriorityItem, PriorityQueueManager
    from reasoning.reasoning_engine import ReasoningEngine

logger = get_logger(__name__)

_ALWAYS_SURFACE_LEVELS = frozenset(
    {PriorityLevel.IMPORTANT_ALERT, PriorityLevel.SCHEDULED_REMINDER}
)
"""CRITICAL_EMERGENCY is handled separately, first, unconditionally —
never included here. See this module's own docstring for why
SCHEDULED_REMINDER is included alongside IMPORTANT_ALERT."""


class PrioritizationDecision(Enum):
    """SURFACE_NOW: announce/interrupt immediately. DEFER_BRIEFLY: wait
    up to active_conversation_defer_seconds, then next_item() itself
    reconsiders. HOLD: leave queued, no explicit re-check scheduled by
    this module — the caller's own next natural poll (wired at 6.13)
    reconsiders it."""

    SURFACE_NOW = "surface_now"
    DEFER_BRIEFLY = "defer_briefly"
    HOLD = "hold"


class AdaptivePrioritizer:
    """Constructor DI: (priority_queue_manager, decision_engine_v2,
    decision_engine_config, reasoning_engine) — see this module's own
    docstring for why the fourth parameter is a necessary, disclosed
    addition and decision_engine_v2 is accepted but genuinely unused.
    Not a ManagedModule — a pure decision layer over already-lifecycle-
    managed collaborators, matching DecisionEngineV2's own identical
    shape."""

    def __init__(
        self,
        priority_queue_manager: PriorityQueueManager,
        decision_engine_v2: DecisionEngineV2,
        decision_engine_config: DecisionEngineConfig,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        self._priority_queue_manager = priority_queue_manager
        self._decision_engine_v2 = decision_engine_v2
        self._config = decision_engine_config
        self._reasoning_engine = reasoning_engine

    def next_item(
        self, working_context: WorkingContext
    ) -> tuple[PriorityItem, PrioritizationDecision] | None:
        """None if the queue is empty. Never pops, never speaks — see
        this module's own docstring."""
        item = self._priority_queue_manager.peek_next()
        if item is None:
            return None

        if item.priority is PriorityLevel.CRITICAL_EMERGENCY:
            return item, PrioritizationDecision.SURFACE_NOW

        if self._is_power_relevant(item) and self._is_battery_low(working_context):
            return item, PrioritizationDecision.SURFACE_NOW

        if item.priority in _ALWAYS_SURFACE_LEVELS:
            return item, PrioritizationDecision.SURFACE_NOW

        # item.priority is WELLNESS or GENERAL_SUGGESTION from here on.
        if self._is_conversation_active(working_context) and not self._has_exceeded_defer_window(
            item
        ):
            return item, PrioritizationDecision.DEFER_BRIEFLY

        if item.priority is PriorityLevel.GENERAL_SUGGESTION and self._is_low_confidence(
            item, working_context
        ):
            return item, PrioritizationDecision.HOLD

        return item, PrioritizationDecision.SURFACE_NOW

    def _is_conversation_active(self, working_context: WorkingContext) -> bool:
        """Isolated for direct testing per this sprint's own explicit
        Testing Checklist item. working_context.conversation is None
        whenever ContextEngine had no ContextManager or it failed
        (context/context_engine.py) — never itself "active." When
        present, "active" means last_activity_at is more recent than
        conversation_active_threshold_seconds — see this module's own
        docstring for why that is its own dedicated field, not a reuse
        of voice.session_timeout_seconds.

        Sprint 6.13 integration correction, found by a real, reproduced
        hang, not assumed: ConversationContext.last_activity_at defaults
        to "now" for a session with zero recorded turns
        (voice/context_manager.py's own ContextManager.current_context()
        docstring) — so a session_id that has genuinely never had a real
        turn (CommunicationPipeline._check_and_announce_priority_item()'s
        own proactive-tick call site, which has no live session of its
        own at all) would otherwise always read as "just active," an
        honest but wrong signal that permanently starved every soft
        announcement via DEFER_BRIEFLY. recent_turns non-empty is now a
        real prerequisite for "active" — a genuinely empty conversation
        history is never evidence of current engagement, regardless of
        what its own timestamp default says."""
        if working_context.conversation is None:
            return False
        if not working_context.conversation.recent_turns:
            return False
        elapsed = (
            datetime.now(UTC) - working_context.conversation.last_activity_at
        ).total_seconds()
        return elapsed < self._config.conversation_active_threshold_seconds

    def _has_exceeded_defer_window(self, item: PriorityItem) -> bool:
        waited_seconds = (datetime.now(UTC) - item.enqueued_at).total_seconds()
        return waited_seconds >= self._config.active_conversation_defer_seconds

    def _is_power_relevant(self, item: PriorityItem) -> bool:
        """True only for a payload this codebase's own real producers
        can construct that genuinely concerns battery/power: a battery
        ResourceAlert (device_control/resource_gate.py) or a
        BATTERY_CRITICAL ProactivePrompt (proactive/proactive_assistant.py,
        Sprint 6.8). Every other payload — including a non-battery
        ResourceAlert (cpu/ram/disk) — is not power-relevant."""
        payload = item.payload
        if isinstance(payload, ResourceAlert):
            return payload.resource == "battery"
        if isinstance(payload, ProactivePrompt):
            return payload.trigger_type is ProactiveTriggerType.BATTERY_CRITICAL
        return False

    def _is_battery_low(self, working_context: WorkingContext) -> bool:
        if working_context.resource_status is None:
            return False
        battery_percent = working_context.resource_status.battery_percent
        if battery_percent is None:
            return False
        return battery_percent < self._config.low_battery_boost_threshold_percent

    def _is_low_confidence(self, item: PriorityItem, working_context: WorkingContext) -> bool:
        """On LlmError, degrades to False (treated as adequate
        confidence) rather than HOLD — a transient LLM failure must
        never silently swallow a real, if minor, suggestion, compounding
        this module's own already-disclosed "HOLD has no maximum wait"
        risk."""
        description = _describe_payload(item)
        try:
            trace = self._reasoning_engine.estimate_confidence(description, working_context)
        except LlmError:
            logger.warning(
                "AdaptivePrioritizer: estimate_confidence() raised LlmError for a %s item; "
                "defaulting to adequate confidence rather than holding it indefinitely.",
                item.source,
            )
            return False
        return trace.confidence < self._config.low_confidence_hold_threshold


def _describe_payload(item: PriorityItem) -> str:
    """A plain description of item.payload (typed object — an Intent, a
    ResourceAlert, a ProactivePrompt, a Recommendation...) for
    ReasoningEngine.estimate_confidence() to reason about. Reads
    whichever of a small set of conventional text-bearing attribute
    names the payload actually has (ProactivePrompt.message,
    Recommendation.text) — never fabricated — falling back to a generic,
    honest mechanical description built from the item's own real
    source/priority when neither exists."""
    for attribute_name in ("message", "text"):
        value = getattr(item.payload, attribute_name, None)
        if isinstance(value, str) and value:
            return value
    return f"a {item.source} item of priority {item.priority.value}"
