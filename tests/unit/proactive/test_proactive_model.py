"""Unit tests for proactive.proactive_model."""

from datetime import UTC, datetime

from decision.priority_queue import PriorityLevel
from proactive.proactive_model import ProactivePrompt, ProactiveTriggerType

_NOW = datetime(2026, 8, 9, 13, 0, 0, tzinfo=UTC)


def test_proactive_prompt_defaults_subject_entity_id_to_none():
    prompt = ProactivePrompt(
        trigger_type=ProactiveTriggerType.BATTERY_CRITICAL,
        message="Battery is low.",
        priority=PriorityLevel.IMPORTANT_ALERT,
        evaluated_at=_NOW,
    )

    assert prompt.subject_entity_id is None


def test_proactive_prompt_can_carry_a_subject_entity_id():
    prompt = ProactivePrompt(
        trigger_type=ProactiveTriggerType.PROJECT_INACTIVITY,
        message="Project has gone quiet.",
        priority=PriorityLevel.GENERAL_SUGGESTION,
        evaluated_at=_NOW,
        subject_entity_id="e1",
    )

    assert prompt.subject_entity_id == "e1"


def test_proactive_trigger_type_has_exactly_the_six_expected_members():
    assert {member.value for member in ProactiveTriggerType} == {
        "upcoming_deadline",
        "forgotten_reminder",
        "battery_critical",
        "long_session",
        "missed_meal",
        "project_inactivity",
    }
