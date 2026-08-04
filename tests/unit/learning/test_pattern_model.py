"""Unit tests for learning.pattern_model."""

from datetime import UTC, datetime

from learning.pattern_model import LearnedPattern, PatternType


def test_pattern_type_has_four_named_categories():
    assert {t.value for t in PatternType} == {
        "preferred_time",
        "frequent_application",
        "work_habit",
        "conversation_style",
    }


def test_learned_pattern_generates_a_pattern_id_when_not_supplied():
    now = datetime.now(UTC)
    pattern = LearnedPattern(
        pattern_type=PatternType.FREQUENT_APPLICATION,
        description="Frequently uses code.exe",
        subject="code.exe",
        confidence=0.8,
        evidence_count=5,
        first_observed_at=now,
        last_updated_at=now,
    )

    assert pattern.pattern_id


def test_learned_pattern_ids_are_unique_across_constructions():
    now = datetime.now(UTC)
    kwargs = dict(
        pattern_type=PatternType.FREQUENT_APPLICATION,
        description="d",
        subject="s",
        confidence=0.5,
        evidence_count=1,
        first_observed_at=now,
        last_updated_at=now,
    )

    first = LearnedPattern(**kwargs)
    second = LearnedPattern(**kwargs)

    assert first.pattern_id != second.pattern_id
