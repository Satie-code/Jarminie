"""Unit tests for wellness.wellness_model."""

from datetime import UTC, datetime

from wellness.wellness_model import WellnessPrompt, WellnessTriggerType


def test_wellness_trigger_type_has_five_named_categories():
    assert {t.value for t in WellnessTriggerType} == {
        "break",
        "hydration",
        "eye_protection",
        "late_night",
        "overwork",
    }


def test_wellness_prompt_escalation_level_defaults_to_one():
    prompt = WellnessPrompt(
        trigger_type=WellnessTriggerType.BREAK,
        message="Take a break.",
        triggered_at=datetime.now(UTC),
    )

    assert prompt.escalation_level == 1


def test_wellness_prompt_generates_a_prompt_id_when_not_supplied():
    prompt = WellnessPrompt(
        trigger_type=WellnessTriggerType.HYDRATION,
        message="Drink some water.",
        triggered_at=datetime.now(UTC),
    )

    assert prompt.prompt_id


def test_wellness_prompt_ids_are_unique_across_constructions():
    now = datetime.now(UTC)
    first = WellnessPrompt(trigger_type=WellnessTriggerType.BREAK, message="m", triggered_at=now)
    second = WellnessPrompt(trigger_type=WellnessTriggerType.BREAK, message="m", triggered_at=now)

    assert first.prompt_id != second.prompt_id
