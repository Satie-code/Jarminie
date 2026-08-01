"""Unit tests for decision.authority."""

import itertools
import logging
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from decision.authority import AuthorityEvaluator, AuthorityLevel, EngineSelection
from decision.context_analyzer import ContextAnalysis, SentimentHint
from decision.models import Intent, IntentCategory
from decision.priority_queue import PriorityLevel
from memory.models import MemoryRecord, MemoryType
from memory.retrieval_engine import RetrievedMemory


def make_intent(
    category: IntentCategory = IntentCategory.INFORMATIONAL, raw_transcript: str = "x"
) -> Intent:
    return Intent(
        category=category,
        confidence=0.9,
        raw_transcript=raw_transcript,
        detected_at=datetime.now(UTC),
    )


def make_context_analysis(
    primary_topic: str = "", mentioned_entities: list[str] | None = None
) -> ContextAnalysis:
    return ContextAnalysis(
        primary_topic=primary_topic,
        mentioned_entities=mentioned_entities if mentioned_entities is not None else [],
        references_past_memory=False,
        suggested_persona=None,
        sentiment_hint=SentimentHint.NEUTRAL,
        analyzed_at=datetime.now(UTC),
    )


def make_retrieved_memory(
    reason: str = "50% similar - Long-term confidence (70/100)",
) -> RetrievedMemory:
    record = MemoryRecord(memory_type=MemoryType.SHARED, content="some content")
    return RetrievedMemory(
        record=record,
        similarity_score=0.5,
        confidence_score=70.0,
        combined_rank_score=0.6,
        retrieval_reason=reason,
    )


@pytest.fixture
def evaluator() -> AuthorityEvaluator:
    return AuthorityEvaluator()


# --- Whitelist gate (EMERGENCY_ASSIST) ----------------------------------------


@pytest.mark.parametrize(
    ("priority_level", "category"),
    list(itertools.product(PriorityLevel, IntentCategory)),
)
def test_empty_whitelist_makes_emergency_assist_unreachable(evaluator, priority_level, category):
    """Exhaustive over every PriorityLevel x IntentCategory combination —
    no input at all can produce EMERGENCY_ASSIST while the whitelist is
    empty (the default at Level 3)."""
    trace = evaluator.evaluate(make_intent(category), make_context_analysis(), [], priority_level)

    assert trace.authority_level is not AuthorityLevel.EMERGENCY_ASSIST


def test_non_empty_whitelist_with_matching_procedure_allows_emergency_assist():
    """Proves the gate isn't hardcoded shut — only correctly empty by
    default. The whitelist is checked against a normalized
    ContextAnalysis.primary_topic (this sprint's own implementation-time
    decision, documented in decision/authority.py's module docstring)."""
    evaluator = AuthorityEvaluator(approved_emergency_procedures=frozenset({"kitchen fire"}))
    intent = make_intent(IntentCategory.EMERGENCY)
    context = make_context_analysis(primary_topic="Kitchen Fire")

    trace = evaluator.evaluate(intent, context, [], PriorityLevel.CRITICAL_EMERGENCY)

    assert trace.authority_level is AuthorityLevel.EMERGENCY_ASSIST


def test_non_empty_whitelist_without_matching_procedure_still_recommends():
    evaluator = AuthorityEvaluator(approved_emergency_procedures=frozenset({"kitchen fire"}))
    intent = make_intent(IntentCategory.EMERGENCY)
    context = make_context_analysis(primary_topic="carbon monoxide leak")

    trace = evaluator.evaluate(intent, context, [], PriorityLevel.CRITICAL_EMERGENCY)

    assert trace.authority_level is AuthorityLevel.RECOMMEND


# --- Authority level (non-emergency paths) ------------------------------------


def test_action_request_is_recommend(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.ACTION_REQUEST),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.authority_level is AuthorityLevel.RECOMMEND


@pytest.mark.parametrize(
    "category",
    [
        IntentCategory.INFORMATIONAL,
        IntentCategory.MEMORY_RECALL,
        IntentCategory.EMOTIONAL_SUPPORT,
        IntentCategory.CASUAL_CONVERSATION,
        IntentCategory.UNKNOWN,
    ],
)
def test_other_categories_are_inform(evaluator, category):
    trace = evaluator.evaluate(
        make_intent(category), make_context_analysis(), [], PriorityLevel.GENERAL_SUGGESTION
    )
    assert trace.authority_level is AuthorityLevel.INFORM


# --- Engine selection degrade --------------------------------------------------


def test_selected_engine_is_always_conversational_or_inform_only(evaluator):
    """True given make_context_analysis()'s default empty
    mentioned_entities — an ACTION_REQUEST with a real, named target now
    genuinely selects DEVICE_CONTROL/WORKFLOW instead (Sprint 4.11), see
    the dedicated tests below; this test only covers the "no resolvable
    target" case, across every category."""
    for category in IntentCategory:
        trace = evaluator.evaluate(
            make_intent(category), make_context_analysis(), [], PriorityLevel.GENERAL_SUGGESTION
        )
        assert trace.selected_engine in (
            EngineSelection.CONVERSATIONAL_RESPONSE,
            EngineSelection.INFORM_ONLY,
        )


def test_action_request_never_actually_selects_device_control(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.ACTION_REQUEST),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.CONVERSATIONAL_RESPONSE
    assert "Device Control" in trace.reasoning_text


def test_emotional_support_never_actually_selects_wellness(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.EMOTIONAL_SUPPORT),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.CONVERSATIONAL_RESPONSE
    assert "Wellness Engine" in trace.reasoning_text


def test_informational_intent_selects_inform_only(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.INFORMATIONAL),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.INFORM_ONLY


# --- Sprint 4.11: real DEVICE_CONTROL/WORKFLOW routing -------------------------


def test_action_request_with_a_named_entity_selects_device_control(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.ACTION_REQUEST, raw_transcript="open notepad"),
        make_context_analysis(mentioned_entities=["notepad"]),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.DEVICE_CONTROL
    assert "device control" in trace.reasoning_text.lower()


def test_action_request_with_workflow_keyword_selects_workflow(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.ACTION_REQUEST, raw_transcript="run my morning routine"),
        make_context_analysis(mentioned_entities=["morning routine"]),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.WORKFLOW
    assert "workflow" in trace.reasoning_text.lower()


def test_action_request_with_entity_and_explicit_workflow_word_selects_workflow(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.ACTION_REQUEST, raw_transcript="run the backup workflow"),
        make_context_analysis(mentioned_entities=["backup"]),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.WORKFLOW


def test_action_request_with_no_entities_still_falls_back_conversationally(evaluator):
    """No concrete target (empty mentioned_entities) must never guess —
    same fallback as before this sprint, just with updated wording since
    Device Control is now real rather than merely inferred-future."""
    trace = evaluator.evaluate(
        make_intent(IntentCategory.ACTION_REQUEST, raw_transcript="do the thing"),
        make_context_analysis(mentioned_entities=[]),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.CONVERSATIONAL_RESPONSE
    assert "couldn't identify a specific target" in trace.reasoning_text


# --- Sprint 4.18: real SCHEDULER/INTERNET_AGENT routing ------------------------


def test_action_request_with_reminder_keyword_and_resolvable_time_selects_scheduler(evaluator):
    trace = evaluator.evaluate(
        make_intent(
            IntentCategory.ACTION_REQUEST, raw_transcript="remind me to call mom in 20 minutes"
        ),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.SCHEDULER
    assert "scheduler" in trace.reasoning_text.lower()


def test_action_request_with_reminder_keyword_in_hours_selects_scheduler(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.ACTION_REQUEST, raw_transcript="set a reminder in 2 hours"),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.SCHEDULER


def test_action_request_with_reminder_keyword_but_no_resolvable_time_falls_back(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.ACTION_REQUEST, raw_transcript="remind me to call mom tomorrow"),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.CONVERSATIONAL_RESPONSE
    assert "couldn't identify a specific time" in trace.reasoning_text


def test_action_request_with_resolvable_time_but_no_reminder_keyword_does_not_select_scheduler(
    evaluator,
):
    """A bare relative-time phrase with no scheduler keyword must not
    accidentally route to SCHEDULER — both conditions are required."""
    trace = evaluator.evaluate(
        make_intent(IntentCategory.ACTION_REQUEST, raw_transcript="open notepad in 5 minutes"),
        make_context_analysis(mentioned_entities=["notepad"]),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.DEVICE_CONTROL


def test_informational_intent_wanting_current_information_selects_internet_agent(evaluator):
    trace = evaluator.evaluate(
        make_intent(
            IntentCategory.INFORMATIONAL, raw_transcript="search for the latest Python release"
        ),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.INTERNET_AGENT
    assert "internet agent" in trace.reasoning_text.lower()


@pytest.mark.parametrize(
    "transcript",
    [
        "what's the latest news on AI",
        "look up the current weather",
        "what's happening in the world today",
    ],
)
def test_informational_intent_current_information_keyword_variants(evaluator, transcript):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.INFORMATIONAL, raw_transcript=transcript),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.INTERNET_AGENT


def test_informational_intent_without_current_information_keyword_stays_inform_only(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.INFORMATIONAL, raw_transcript="what is the capital of France"),
        make_context_analysis(),
        [],
        PriorityLevel.GENERAL_SUGGESTION,
    )
    assert trace.selected_engine is EngineSelection.INFORM_ONLY


# --- reasoning_text -------------------------------------------------------------


@pytest.mark.parametrize(
    ("category", "priority_level"),
    [
        (IntentCategory.INFORMATIONAL, PriorityLevel.GENERAL_SUGGESTION),
        (IntentCategory.ACTION_REQUEST, PriorityLevel.GENERAL_SUGGESTION),
        (IntentCategory.EMERGENCY, PriorityLevel.CRITICAL_EMERGENCY),
        (IntentCategory.CASUAL_CONVERSATION, PriorityLevel.IMPORTANT_ALERT),
    ],
)
def test_reasoning_text_references_intent_category_and_priority_level(
    evaluator, category, priority_level
):
    trace = evaluator.evaluate(make_intent(category), make_context_analysis(), [], priority_level)

    assert trace.reasoning_text
    assert category.name in trace.reasoning_text
    assert priority_level.name in trace.reasoning_text


def test_reasoning_text_mentions_retrieved_memory_count(evaluator):
    memories = [make_retrieved_memory(), make_retrieved_memory()]
    trace = evaluator.evaluate(
        make_intent(), make_context_analysis(), memories, PriorityLevel.GENERAL_SUGGESTION
    )

    assert "2 retrieved memories" in trace.reasoning_text


def test_unapproved_emergency_reasoning_states_the_limitation_honestly(evaluator):
    trace = evaluator.evaluate(
        make_intent(IntentCategory.EMERGENCY),
        make_context_analysis(),
        [],
        PriorityLevel.CRITICAL_EMERGENCY,
    )

    assert "no pre-approved emergency procedures" in trace.reasoning_text


# --- explain() -------------------------------------------------------------------


def test_explain_includes_every_retrieval_reason(evaluator):
    memories = [make_retrieved_memory("reason one"), make_retrieved_memory("reason two")]
    trace = evaluator.evaluate(
        make_intent(), make_context_analysis(), memories, PriorityLevel.GENERAL_SUGGESTION
    )

    explanation = evaluator.explain(trace)

    assert "reason one" in explanation
    assert "reason two" in explanation
    assert trace.reasoning_text in explanation


def test_explain_with_no_memories_states_so(evaluator):
    trace = evaluator.evaluate(
        make_intent(), make_context_analysis(), [], PriorityLevel.GENERAL_SUGGESTION
    )

    explanation = evaluator.explain(trace)

    assert "No memories were retrieved" in explanation


# --- health_check() ---------------------------------------------------------------


def test_health_check_true_with_empty_whitelist(evaluator):
    assert evaluator.health_check() is True


def test_health_check_warns_but_still_true_with_non_empty_whitelist(caplog):
    evaluator = AuthorityEvaluator(approved_emergency_procedures=frozenset({"some procedure"}))

    with caplog.at_level(logging.WARNING):
        result = evaluator.health_check()

    assert result is True
    assert any("non-empty" in record.message for record in caplog.records)


def test_start_and_stop_do_not_raise(evaluator):
    evaluator.start()
    evaluator.stop()


# --- Sprint 3.13 hardening (scenario e): fail safe-down, never safe-up -------------


def test_internal_exception_degrades_to_safe_default_inform(evaluator, caplog):
    """An unexpected internal failure (simulated here via a raising
    _determine_engine(), the same "patch one internal method to raise"
    technique already established for AuthorityEvaluator's own
    collaborators elsewhere in this project) must resolve to the lowest,
    safest AuthorityLevel/EngineSelection pair — never propagate, and
    never default to anything more permissive."""
    with patch.object(
        AuthorityEvaluator, "_determine_engine", side_effect=RuntimeError("boom")
    ), caplog.at_level(logging.ERROR):
        trace = evaluator.evaluate(
            make_intent(IntentCategory.EMERGENCY),
            make_context_analysis(),
            [],
            PriorityLevel.CRITICAL_EMERGENCY,
        )

    assert trace.authority_level is AuthorityLevel.INFORM
    assert trace.selected_engine is EngineSelection.INFORM_ONLY
    assert "internal error" in trace.reasoning_text
    assert any("failed internally" in record.message for record in caplog.records)


def test_internal_exception_still_returns_every_other_trace_field(evaluator):
    """The safe-default path must not silently drop the rest of the
    DecisionTrace's contract — callers downstream (CommunicationPipeline,
    Persona.compose_reply()) still need intent/context_analysis/
    retrieved_memories/priority_level/decided_at populated."""
    intent = make_intent(IntentCategory.MEMORY_RECALL)
    context = make_context_analysis(primary_topic="a topic")
    memories = [make_retrieved_memory()]

    with patch.object(AuthorityEvaluator, "_determine_authority", side_effect=RuntimeError("x")):
        trace = evaluator.evaluate(intent, context, memories, PriorityLevel.WELLNESS)

    assert trace.intent is intent
    assert trace.context_analysis is context
    assert trace.retrieved_memories is memories
    assert trace.priority_level is PriorityLevel.WELLNESS
    assert trace.decided_at is not None


def test_internal_exception_in_reasoning_builder_also_degrades_safely(evaluator):
    """A failure in the reasoning-text builder (called last, after
    authority/engine are already determined) must still discard whatever
    authority_level/selected_engine were computed and fall back to the
    safe default — a partial success must not leak a more permissive
    level than the safe default allows."""
    with patch("decision.authority._build_reasoning", side_effect=RuntimeError("boom")):
        trace = evaluator.evaluate(
            make_intent(IntentCategory.ACTION_REQUEST),
            make_context_analysis(),
            [],
            PriorityLevel.GENERAL_SUGGESTION,
        )

    assert trace.authority_level is AuthorityLevel.INFORM
    assert trace.selected_engine is EngineSelection.INFORM_ONLY


# --- DecisionTrace shape -----------------------------------------------------------


def test_decision_trace_carries_every_input(evaluator):
    intent = make_intent(IntentCategory.MEMORY_RECALL)
    context = make_context_analysis(primary_topic="a topic")
    memories = [make_retrieved_memory()]

    trace = evaluator.evaluate(intent, context, memories, PriorityLevel.WELLNESS)

    assert trace.intent is intent
    assert trace.context_analysis is context
    assert trace.retrieved_memories is memories
    assert trace.priority_level is PriorityLevel.WELLNESS
    assert trace.decided_at is not None
