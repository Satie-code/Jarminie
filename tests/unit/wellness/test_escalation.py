"""Unit tests for wellness.escalation."""

from config.schema import WellnessConfig
from wellness.escalation import WellnessEscalationManager
from wellness.wellness_model import WellnessTriggerType


def _manager(**overrides) -> WellnessEscalationManager:
    return WellnessEscalationManager(WellnessConfig(**overrides))


# --- level progression and cap ------------------------------------------------------------


def test_a_trigger_never_touched_starts_at_level_one_not_hard_limited():
    manager = _manager()

    assert manager.current_level(WellnessTriggerType.BREAK) == 1
    assert manager.is_hard_limited(WellnessTriggerType.BREAK) is False


def test_register_postponed_escalates_level_one_to_two_to_three_capped():
    manager = _manager(max_postponements_before_hard_limit=10)

    manager.register_postponed(WellnessTriggerType.BREAK)
    assert manager.current_level(WellnessTriggerType.BREAK) == 2

    manager.register_postponed(WellnessTriggerType.BREAK)
    assert manager.current_level(WellnessTriggerType.BREAK) == 3

    manager.register_postponed(WellnessTriggerType.BREAK)
    assert manager.current_level(WellnessTriggerType.BREAK) == 3


# --- hard-limit boundary -------------------------------------------------------------------


def test_hard_limit_engages_exactly_on_the_third_postponement():
    manager = _manager(max_postponements_before_hard_limit=3)

    manager.register_postponed(WellnessTriggerType.HYDRATION)
    assert manager.is_hard_limited(WellnessTriggerType.HYDRATION) is False

    manager.register_postponed(WellnessTriggerType.HYDRATION)
    assert manager.is_hard_limited(WellnessTriggerType.HYDRATION) is False

    manager.register_postponed(WellnessTriggerType.HYDRATION)
    assert manager.is_hard_limited(WellnessTriggerType.HYDRATION) is True

    manager.register_postponed(WellnessTriggerType.HYDRATION)
    assert manager.is_hard_limited(WellnessTriggerType.HYDRATION) is True
    assert manager.current_level(WellnessTriggerType.HYDRATION) == 3


def test_hard_limit_is_per_trigger_not_global():
    manager = _manager(max_postponements_before_hard_limit=1)

    manager.register_postponed(WellnessTriggerType.BREAK)

    assert manager.is_hard_limited(WellnessTriggerType.BREAK) is True
    assert manager.is_hard_limited(WellnessTriggerType.HYDRATION) is False


# --- reset_all() vs. reset(trigger_type) scoping -------------------------------------------


def test_reset_all_clears_every_trigger():
    manager = _manager(max_postponements_before_hard_limit=1)
    manager.register_postponed(WellnessTriggerType.BREAK)
    manager.register_postponed(WellnessTriggerType.HYDRATION)

    manager.reset_all()

    for trigger_type in WellnessTriggerType:
        assert manager.current_level(trigger_type) == 1
        assert manager.is_hard_limited(trigger_type) is False


def test_reset_clears_only_the_named_trigger():
    manager = _manager(max_postponements_before_hard_limit=1)
    manager.register_postponed(WellnessTriggerType.BREAK)
    manager.register_postponed(WellnessTriggerType.HYDRATION)

    manager.reset(WellnessTriggerType.BREAK)

    assert manager.current_level(WellnessTriggerType.BREAK) == 1
    assert manager.is_hard_limited(WellnessTriggerType.BREAK) is False
    assert manager.is_hard_limited(WellnessTriggerType.HYDRATION) is True


# --- message_for(): mapped vs. fallback template --------------------------------------------


def test_message_for_resolves_the_configured_template_at_the_current_level():
    manager = _manager(
        max_postponements_before_hard_limit=10,
        escalation_message_templates={"break": ["gentle", "stronger", "strong"]},
    )

    assert manager.message_for(WellnessTriggerType.BREAK) == "gentle"
    manager.register_postponed(WellnessTriggerType.BREAK)
    assert manager.message_for(WellnessTriggerType.BREAK) == "stronger"
    manager.register_postponed(WellnessTriggerType.BREAK)
    assert manager.message_for(WellnessTriggerType.BREAK) == "strong"


def test_message_for_falls_back_to_the_generic_template_for_an_unmapped_trigger():
    manager = _manager(escalation_message_templates={})

    message = manager.message_for(WellnessTriggerType.OVERWORK)

    assert message
    assert isinstance(message, str)


def test_message_for_generic_fallback_also_escalates_by_level():
    manager = _manager(
        max_postponements_before_hard_limit=10, escalation_message_templates={}
    )

    level_one_message = manager.message_for(WellnessTriggerType.LATE_NIGHT)
    manager.register_postponed(WellnessTriggerType.LATE_NIGHT)
    level_two_message = manager.message_for(WellnessTriggerType.LATE_NIGHT)

    assert level_one_message != level_two_message


# --- register_prompt_shown() never itself escalates or resets ------------------------------


def test_register_prompt_shown_does_not_change_level_or_hard_limit_state():
    manager = _manager(max_postponements_before_hard_limit=1)

    manager.register_prompt_shown(WellnessTriggerType.BREAK)

    assert manager.current_level(WellnessTriggerType.BREAK) == 1
    assert manager.is_hard_limited(WellnessTriggerType.BREAK) is False


def test_register_prompt_shown_after_postponement_does_not_further_escalate():
    manager = _manager(max_postponements_before_hard_limit=10)
    manager.register_postponed(WellnessTriggerType.BREAK)

    manager.register_prompt_shown(WellnessTriggerType.BREAK)
    manager.register_prompt_shown(WellnessTriggerType.BREAK)

    assert manager.current_level(WellnessTriggerType.BREAK) == 2
