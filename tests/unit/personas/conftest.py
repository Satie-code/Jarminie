"""Shared test fixtures for personas/ unit tests.

Plain helper functions can't be imported across files here (tests/ has no
__init__.py, by convention since Sprint 1.1), so shared helpers are
exposed as fixtures instead, same pattern as tests/unit/voice/conftest.py.
"""

from datetime import UTC, datetime

import pytest

from decision.authority import AuthorityLevel, DecisionTrace, EngineSelection
from decision.context_analyzer import ContextAnalysis, SentimentHint
from decision.models import Intent, IntentCategory
from decision.priority_queue import PriorityLevel
from voice.context_manager import ConversationContext


@pytest.fixture
def conversation_context_factory():
    """Factory fixture: build a ConversationContext with sensible
    defaults, overridable per test via keyword arguments. Reused by
    Sprint 2.10 (Minie Persona) and 2.11 (Persona Switching)'s tests."""

    def _make(**overrides):
        now = datetime.now(UTC)
        defaults = dict(
            session_id="session-1",
            active_persona_name="jarvis",
            recent_turns=[],
            session_started_at=now,
            last_activity_at=now,
        )
        defaults.update(overrides)
        return ConversationContext(**defaults)

    return _make


@pytest.fixture
def context_analysis_factory():
    """Factory fixture: build a ContextAnalysis with neutral defaults,
    overridable per test — Sprint 3.12 addition, reused by
    decision_trace_factory below and by test_persona_manager.py's
    select_from_context() tests."""

    def _make(**overrides):
        defaults = dict(
            primary_topic="",
            mentioned_entities=[],
            references_past_memory=False,
            suggested_persona=None,
            sentiment_hint=SentimentHint.NEUTRAL,
            analyzed_at=datetime.now(UTC),
        )
        defaults.update(overrides)
        return ContextAnalysis(**defaults)

    return _make


@pytest.fixture
def decision_trace_factory(context_analysis_factory):
    """Factory fixture: build a DecisionTrace with sensible defaults
    (INFORM authority, CONVERSATIONAL_RESPONSE engine, no retrieved
    memories), overridable per test — Sprint 3.12 addition, reused by
    JarvisPersona/MiniePersona/PersonaManager's compose_reply()-adjacent
    tests."""

    def _make(**overrides):
        defaults = dict(
            intent=Intent(
                category=IntentCategory.INFORMATIONAL,
                confidence=0.9,
                raw_transcript="x",
                detected_at=datetime.now(UTC),
            ),
            context_analysis=context_analysis_factory(),
            retrieved_memories=[],
            priority_level=PriorityLevel.GENERAL_SUGGESTION,
            authority_level=AuthorityLevel.INFORM,
            selected_engine=EngineSelection.CONVERSATIONAL_RESPONSE,
            reasoning_text="test reasoning",
            decided_at=datetime.now(UTC),
        )
        defaults.update(overrides)
        return DecisionTrace(**defaults)

    return _make
