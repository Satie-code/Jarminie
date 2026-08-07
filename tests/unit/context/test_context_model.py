"""Unit tests for context.context_model."""

import dataclasses
from datetime import UTC, datetime

import pytest

from context.context_model import WorkingContext


def test_working_context_defaults_known_projects_to_empty_list():
    ctx = WorkingContext(
        built_at=datetime.now(UTC),
        conversation=None,
        recent_memories=[],
        recent_applications=[],
        upcoming_scheduled_items=[],
        resource_status=None,
    )

    assert ctx.known_projects == []


def test_working_context_is_frozen():
    ctx = WorkingContext(
        built_at=datetime.now(UTC),
        conversation=None,
        recent_memories=[],
        recent_applications=[],
        upcoming_scheduled_items=[],
        resource_status=None,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.recent_memories = ["mutated"]
