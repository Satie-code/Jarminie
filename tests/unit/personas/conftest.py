"""Shared test fixtures for personas/ unit tests.

Plain helper functions can't be imported across files here (tests/ has no
__init__.py, by convention since Sprint 1.1), so shared helpers are
exposed as fixtures instead, same pattern as tests/unit/voice/conftest.py.
"""

from datetime import UTC, datetime

import pytest

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
