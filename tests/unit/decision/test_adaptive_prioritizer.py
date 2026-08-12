"""Unit tests for decision.adaptive_prioritizer.

Uses a small, local, duck-typed FakePriorityQueueManager (implementing
only peek_next(), the sole method AdaptivePrioritizer ever calls on it —
the same "fake only what the test needs to control" discipline
test_decision_engine_v2.py's own fakes already establish) and a real
ReasoningEngine wired to a local FakeLanguageModelClient for the
low-confidence HOLD path. decision_engine_v2 is passed as None
throughout — AdaptivePrioritizer accepts it per this sprint's own
literal constructor signature but never calls it (see
decision/adaptive_prioritizer.py's own docstring).
"""

from datetime import UTC, datetime, timedelta

import pytest

from config.schema import DecisionEngineConfig, ModelConfig, ReasoningConfig
from context.context_model import WorkingContext
from core.resource_monitor import ResourceAlert, ResourceSnapshot
from decision.adaptive_prioritizer import AdaptivePrioritizer, PrioritizationDecision
from decision.llm_client import LlmError
from decision.priority_queue import PriorityItem, PriorityLevel
from proactive.proactive_model import ProactivePrompt, ProactiveTriggerType
from reasoning.reasoning_engine import ReasoningEngine
from voice.context_manager import ConversationContext
from voice.conversation_store import ConversationTurn


class FakePriorityQueueManager:
    def __init__(self, item: PriorityItem | None) -> None:
        self._item = item

    def peek_next(self) -> PriorityItem | None:
        return self._item


class FakeLanguageModelClient:
    """Implements ONLY the LanguageModelClient Protocol (no is_reachable)
    — matches test_reasoning_engine.py's own established fake."""

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[str] = []

    def generate(
        self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
    ) -> str:
        self.calls.append(prompt)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def make_item(
    priority: PriorityLevel,
    payload: object = "a generic queued item",
    source: str = "test",
    enqueued_at: datetime | None = None,
) -> PriorityItem:
    return PriorityItem(
        payload=payload,
        priority=priority,
        enqueued_at=enqueued_at or datetime.now(UTC),
        source=source,
    )


def make_working_context(
    conversation_active: bool | None = None,
    battery_percent: float | None = None,
) -> WorkingContext:
    conversation = None
    if conversation_active is not None:
        now = datetime.now(UTC)
        last_activity_at = now if conversation_active else (now - timedelta(hours=1))
        # A real, non-empty recent_turns entry is required for "active"
        # to mean anything (Sprint 6.13's own integration correction —
        # an empty conversation history is never active regardless of
        # its own last_activity_at timestamp, see
        # decision/adaptive_prioritizer.py's own docstring).
        recent_turns = [
            ConversationTurn(
                session_id="s1",
                persona_name="jarvis",
                timestamp=last_activity_at,
                user_text="hello",
                response_text="hi",
            )
        ]
        conversation = ConversationContext(
            session_id="s1",
            active_persona_name="jarvis",
            recent_turns=recent_turns,
            session_started_at=last_activity_at,
            last_activity_at=last_activity_at,
        )
    resource_status = None
    if battery_percent is not None:
        resource_status = ResourceSnapshot(
            cpu_percent=10.0,
            ram_percent=10.0,
            disk_percent=10.0,
            battery_percent=battery_percent,
            timestamp=datetime.now(UTC),
        )
    return WorkingContext(
        built_at=datetime.now(UTC),
        conversation=conversation,
        recent_memories=[],
        recent_applications=[],
        upcoming_scheduled_items=[],
        resource_status=resource_status,
    )


def make_prioritizer(
    item: PriorityItem | None,
    decision_engine_config: DecisionEngineConfig | None = None,
    response: str = "CONCLUSION: fine\nCONFIDENCE: 0.9",
    error: Exception | None = None,
) -> tuple[AdaptivePrioritizer, FakeLanguageModelClient]:
    fake_client = FakeLanguageModelClient(response=response, error=error)
    reasoning_engine = ReasoningEngine(
        fake_client, ModelConfig(ollama_timeout_seconds=5.0), ReasoningConfig()
    )
    prioritizer = AdaptivePrioritizer(
        FakePriorityQueueManager(item),
        None,
        decision_engine_config or DecisionEngineConfig(),
        reasoning_engine,
    )
    return prioritizer, fake_client


# --- empty queue -----------------------------------------------------------------------------


def test_empty_queue_returns_none():
    prioritizer, _ = make_prioritizer(None)

    assert prioritizer.next_item(make_working_context()) is None


# --- CRITICAL_EMERGENCY always wins -----------------------------------------------------------


@pytest.mark.parametrize("conversation_active", [True, False, None])
@pytest.mark.parametrize("battery_percent", [3.0, 80.0, None])
def test_critical_emergency_always_surfaces_now(conversation_active, battery_percent):
    item = make_item(PriorityLevel.CRITICAL_EMERGENCY)
    prioritizer, fake_client = make_prioritizer(item)
    working_context = make_working_context(conversation_active, battery_percent)

    result = prioritizer.next_item(working_context)

    assert result == (item, PrioritizationDecision.SURFACE_NOW)
    assert fake_client.calls == []


# --- IMPORTANT_ALERT/SCHEDULED_REMINDER never defer --------------------------------------------


@pytest.mark.parametrize(
    "priority", [PriorityLevel.IMPORTANT_ALERT, PriorityLevel.SCHEDULED_REMINDER]
)
def test_important_alert_and_scheduled_reminder_never_defer_during_active_conversation(priority):
    item = make_item(priority)
    prioritizer, _ = make_prioritizer(item)
    working_context = make_working_context(conversation_active=True)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.SURFACE_NOW


# --- GENERAL_SUGGESTION/WELLNESS defer during an active conversation --------------------------


@pytest.mark.parametrize("priority", [PriorityLevel.WELLNESS, PriorityLevel.GENERAL_SUGGESTION])
def test_soft_items_defer_during_active_conversation(priority):
    item = make_item(priority)
    prioritizer, fake_client = make_prioritizer(item)
    working_context = make_working_context(conversation_active=True)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.DEFER_BRIEFLY
    assert fake_client.calls == []


@pytest.mark.parametrize("priority", [PriorityLevel.WELLNESS, PriorityLevel.GENERAL_SUGGESTION])
def test_soft_items_do_not_defer_when_conversation_is_not_active(priority):
    item = make_item(priority)
    prioritizer, _ = make_prioritizer(
        item, response="CONCLUSION: fine\nCONFIDENCE: 0.9"
    )
    working_context = make_working_context(conversation_active=False)

    _, decision = prioritizer.next_item(working_context)

    assert decision != PrioritizationDecision.DEFER_BRIEFLY


def test_wellness_item_surfaces_now_with_no_active_conversation():
    item = make_item(PriorityLevel.WELLNESS)
    prioritizer, fake_client = make_prioritizer(item)
    working_context = make_working_context(conversation_active=False)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.SURFACE_NOW
    assert fake_client.calls == []


def test_soft_item_surfaces_now_once_the_defer_window_has_been_exceeded():
    config = DecisionEngineConfig(active_conversation_defer_seconds=60.0)
    stale_enqueued_at = datetime.now(UTC) - timedelta(seconds=120.0)
    item = make_item(PriorityLevel.WELLNESS, enqueued_at=stale_enqueued_at)
    prioritizer, _ = make_prioritizer(item, decision_engine_config=config)
    working_context = make_working_context(conversation_active=True)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.SURFACE_NOW


# --- low-battery boost -------------------------------------------------------------------------


def test_battery_resource_alert_boosts_to_surface_now_when_battery_is_low():
    alert = ResourceAlert(
        resource="battery", value=5.0, threshold=10.0, timestamp=datetime.now(UTC)
    )
    item = make_item(PriorityLevel.GENERAL_SUGGESTION, payload=alert)
    prioritizer, fake_client = make_prioritizer(item)
    working_context = make_working_context(conversation_active=True, battery_percent=5.0)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.SURFACE_NOW
    assert fake_client.calls == []


def test_battery_critical_proactive_prompt_boosts_to_surface_now_when_battery_is_low():
    prompt = ProactivePrompt(
        trigger_type=ProactiveTriggerType.BATTERY_CRITICAL,
        message="Battery is critically low.",
        priority=PriorityLevel.GENERAL_SUGGESTION,
        evaluated_at=datetime.now(UTC),
    )
    item = make_item(PriorityLevel.GENERAL_SUGGESTION, payload=prompt)
    prioritizer, _ = make_prioritizer(item)
    working_context = make_working_context(conversation_active=True, battery_percent=2.0)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.SURFACE_NOW


def test_power_relevant_item_not_boosted_when_battery_is_normal():
    alert = ResourceAlert(
        resource="battery", value=50.0, threshold=10.0, timestamp=datetime.now(UTC)
    )
    item = make_item(PriorityLevel.WELLNESS, payload=alert)
    prioritizer, _ = make_prioritizer(item)
    working_context = make_working_context(conversation_active=True, battery_percent=80.0)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.DEFER_BRIEFLY


def test_non_battery_resource_alert_is_not_power_relevant():
    alert = ResourceAlert(resource="cpu", value=95.0, threshold=90.0, timestamp=datetime.now(UTC))
    item = make_item(PriorityLevel.WELLNESS, payload=alert)
    prioritizer, _ = make_prioritizer(item)
    working_context = make_working_context(conversation_active=True, battery_percent=2.0)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.DEFER_BRIEFLY


def test_no_resource_status_never_boosts():
    alert = ResourceAlert(
        resource="battery", value=5.0, threshold=10.0, timestamp=datetime.now(UTC)
    )
    item = make_item(PriorityLevel.WELLNESS, payload=alert)
    prioritizer, _ = make_prioritizer(item)
    working_context = make_working_context(conversation_active=True, battery_percent=None)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.DEFER_BRIEFLY


# --- low-confidence HOLD ------------------------------------------------------------------------


def test_general_suggestion_holds_on_low_confidence_with_no_active_conversation():
    item = make_item(PriorityLevel.GENERAL_SUGGESTION, payload="a vague suggestion")
    prioritizer, fake_client = make_prioritizer(
        item, response="CONCLUSION: unsure\nCONFIDENCE: 0.1"
    )
    working_context = make_working_context(conversation_active=False)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.HOLD
    assert len(fake_client.calls) == 1


def test_general_suggestion_surfaces_now_on_high_confidence_with_no_active_conversation():
    item = make_item(PriorityLevel.GENERAL_SUGGESTION, payload="a solid suggestion")
    prioritizer, _ = make_prioritizer(item, response="CONCLUSION: sure\nCONFIDENCE: 0.9")
    working_context = make_working_context(conversation_active=False)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.SURFACE_NOW


def test_wellness_item_never_hits_the_confidence_check():
    item = make_item(PriorityLevel.WELLNESS, payload="a wellness nudge")
    prioritizer, fake_client = make_prioritizer(
        item, response="CONCLUSION: unsure\nCONFIDENCE: 0.0"
    )
    working_context = make_working_context(conversation_active=False)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.SURFACE_NOW
    assert fake_client.calls == []


def test_low_confidence_check_degrades_to_surface_now_on_llm_error():
    item = make_item(PriorityLevel.GENERAL_SUGGESTION)
    prioritizer, _ = make_prioritizer(item, error=LlmError("model unreachable"))
    working_context = make_working_context(conversation_active=False)

    _, decision = prioritizer.next_item(working_context)

    assert decision == PrioritizationDecision.SURFACE_NOW


def test_describes_payload_using_message_attribute_when_present():
    prompt = ProactivePrompt(
        trigger_type=ProactiveTriggerType.LONG_SESSION,
        message="You've been at this a while.",
        priority=PriorityLevel.GENERAL_SUGGESTION,
        evaluated_at=datetime.now(UTC),
    )
    item = make_item(PriorityLevel.GENERAL_SUGGESTION, payload=prompt)
    prioritizer, fake_client = make_prioritizer(
        item, response="CONCLUSION: fine\nCONFIDENCE: 0.9"
    )
    working_context = make_working_context(conversation_active=False)

    prioritizer.next_item(working_context)

    assert "You've been at this a while." in fake_client.calls[0]


# --- _is_conversation_active() in isolation -----------------------------------------------------


def test_is_conversation_active_false_when_no_conversation():
    prioritizer, _ = make_prioritizer(None)

    assert prioritizer._is_conversation_active(make_working_context()) is False


def test_is_conversation_active_false_for_an_empty_conversation():
    """Sprint 6.13 integration correction: ConversationContext.
    last_activity_at defaults to "now" for a session with zero recorded
    turns (voice/context_manager.py's own ContextManager.current_context()
    docstring) — a real, reproduced bug this test guards against
    regressing, found via a genuine integration-test hang where a
    never-used session_id always read as "just active," permanently
    deferring every soft announcement."""
    prioritizer, _ = make_prioritizer(None)
    empty_conversation = ConversationContext(
        session_id="s1",
        active_persona_name="jarvis",
        recent_turns=[],
        session_started_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
    )
    working_context = WorkingContext(
        built_at=datetime.now(UTC),
        conversation=empty_conversation,
        recent_memories=[],
        recent_applications=[],
        upcoming_scheduled_items=[],
        resource_status=None,
    )

    assert prioritizer._is_conversation_active(working_context) is False


def test_is_conversation_active_true_for_recent_activity():
    prioritizer, _ = make_prioritizer(None)

    working_context = make_working_context(conversation_active=True)
    assert prioritizer._is_conversation_active(working_context) is True


def test_is_conversation_active_false_once_past_the_threshold():
    """A real, non-empty recent_turns is used here specifically so this
    test still exercises the time-threshold logic itself, not the
    separate empty-recent_turns guard (see that guard's own dedicated
    test, test_is_conversation_active_false_for_an_empty_conversation)."""
    config = DecisionEngineConfig(conversation_active_threshold_seconds=30.0)
    prioritizer, _ = make_prioritizer(None, decision_engine_config=config)
    stale_timestamp = datetime.now(UTC) - timedelta(seconds=60.0)
    stale_conversation = ConversationContext(
        session_id="s1",
        active_persona_name="jarvis",
        recent_turns=[
            ConversationTurn(
                session_id="s1",
                persona_name="jarvis",
                timestamp=stale_timestamp,
                user_text="hello",
                response_text="hi",
            )
        ],
        session_started_at=stale_timestamp,
        last_activity_at=stale_timestamp,
    )
    working_context = WorkingContext(
        built_at=datetime.now(UTC),
        conversation=stale_conversation,
        recent_memories=[],
        recent_applications=[],
        upcoming_scheduled_items=[],
        resource_status=None,
    )

    assert prioritizer._is_conversation_active(working_context) is False
