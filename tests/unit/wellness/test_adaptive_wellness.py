"""Unit tests for wellness.adaptive_wellness.

AdaptiveWellnessAdjuster is exercised against a duck-typed fake
PatternStore (only list_by_type() is needed, matching the real class's
own contract) — PatternStore's own persistence/upsert logic is already
covered by tests/unit/learning/test_pattern_store.py (Sprint 5.21).
"""

from datetime import UTC, datetime

import pytest

from config.schema import WellnessConfig
from learning.pattern_model import LearnedPattern, PatternType
from wellness.adaptive_wellness import AdaptiveWellnessAdjuster
from wellness.wellness_model import WellnessTriggerType

_NOW = datetime(2026, 8, 4, 15, 0, tzinfo=UTC)


class _FakePatternStore:
    def __init__(self, patterns: list[LearnedPattern]) -> None:
        self._patterns = patterns
        self.list_by_type_calls: list[PatternType] = []

    def list_by_type(self, pattern_type: PatternType) -> list[LearnedPattern]:
        self.list_by_type_calls.append(pattern_type)
        return [p for p in self._patterns if p.pattern_type is pattern_type]


def _work_habit(subject: str = "coding", confidence: float = 0.8) -> LearnedPattern:
    return LearnedPattern(
        pattern_type=PatternType.WORK_HABIT,
        description=f"Regularly active in the '{subject}' category",
        subject=subject,
        confidence=confidence,
        evidence_count=5,
        first_observed_at=_NOW,
        last_updated_at=_NOW,
    )


def _adjuster(patterns=None, **config_overrides):
    store = _FakePatternStore(patterns or [])
    config = WellnessConfig(**config_overrides)
    return AdaptiveWellnessAdjuster(store, config), store


# --- compute_overrides(): no-evidence default ------------------------------------------------


def test_compute_overrides_with_no_patterns_is_inert_for_every_trigger():
    adjuster, _ = _adjuster()

    overrides = adjuster.compute_overrides()

    assert overrides == dict.fromkeys(WellnessTriggerType, 1.0)


def test_compute_overrides_reads_both_pattern_types():
    adjuster, store = _adjuster()

    adjuster.compute_overrides()

    assert PatternType.WORK_HABIT in store.list_by_type_calls
    assert PatternType.PREFERRED_TIME in store.list_by_type_calls


# --- compute_overrides(): high-confidence widening + clamping --------------------------------


def test_compute_overrides_widens_break_and_eye_protection_from_a_work_habit_pattern():
    adjuster, _ = _adjuster(
        patterns=[_work_habit(confidence=0.8)],
        adaptive_min_multiplier=0.75,
        adaptive_max_multiplier=1.5,
    )

    overrides = adjuster.compute_overrides()

    expected = 1.0 + 0.8 * (1.5 - 1.0)
    assert overrides[WellnessTriggerType.BREAK] == pytest.approx(expected)
    assert overrides[WellnessTriggerType.EYE_PROTECTION] == pytest.approx(expected)


def test_compute_overrides_uses_the_strongest_work_habit_pattern():
    adjuster, _ = _adjuster(
        patterns=[_work_habit("coding", confidence=0.4), _work_habit("writing", confidence=0.9)],
        adaptive_min_multiplier=0.75,
        adaptive_max_multiplier=1.5,
    )

    overrides = adjuster.compute_overrides()

    expected = 1.0 + 0.9 * (1.5 - 1.0)
    assert overrides[WellnessTriggerType.BREAK] == pytest.approx(expected)


def test_compute_overrides_clamps_at_the_configured_max():
    adjuster, _ = _adjuster(
        patterns=[_work_habit(confidence=1.0)],
        adaptive_min_multiplier=0.75,
        adaptive_max_multiplier=1.2,
    )

    overrides = adjuster.compute_overrides()

    assert overrides[WellnessTriggerType.BREAK] == 1.2


def test_compute_overrides_clamps_at_the_configured_min():
    adjuster, _ = _adjuster(
        patterns=[_work_habit(confidence=0.5)],
        adaptive_min_multiplier=2.0,
        adaptive_max_multiplier=3.0,
    )

    overrides = adjuster.compute_overrides()

    assert overrides[WellnessTriggerType.BREAK] == 2.0


# --- LATE_NIGHT/OVERWORK/HYDRATION exclusion --------------------------------------------------


def test_compute_overrides_never_widens_late_night_or_overwork():
    adjuster, _ = _adjuster(patterns=[_work_habit(confidence=1.0)])

    overrides = adjuster.compute_overrides()

    assert overrides[WellnessTriggerType.LATE_NIGHT] == 1.0
    assert overrides[WellnessTriggerType.OVERWORK] == 1.0


def test_compute_overrides_does_not_widen_hydration_this_sprint():
    adjuster, _ = _adjuster(patterns=[_work_habit(confidence=1.0)])

    overrides = adjuster.compute_overrides()

    assert overrides[WellnessTriggerType.HYDRATION] == 1.0


# --- explain() -------------------------------------------------------------------------------


def test_explain_with_no_evidence_returns_the_honest_default_sentence():
    adjuster, _ = _adjuster()

    assert adjuster.explain(WellnessTriggerType.BREAK) == (
        "No pattern evidence yet — using the default interval."
    )


def test_explain_with_evidence_names_the_real_pattern_and_percent():
    adjuster, _ = _adjuster(
        patterns=[_work_habit("coding", confidence=0.8)],
        adaptive_min_multiplier=0.75,
        adaptive_max_multiplier=1.5,
    )

    explanation = adjuster.explain(WellnessTriggerType.BREAK)

    assert "coding" in explanation
    assert "%" in explanation


def test_explain_for_a_never_adaptive_trigger_always_returns_the_default_sentence():
    adjuster, _ = _adjuster(patterns=[_work_habit(confidence=1.0)])

    assert adjuster.explain(WellnessTriggerType.LATE_NIGHT) == (
        "No pattern evidence yet — using the default interval."
    )
    assert adjuster.explain(WellnessTriggerType.OVERWORK) == (
        "No pattern evidence yet — using the default interval."
    )
    assert adjuster.explain(WellnessTriggerType.HYDRATION) == (
        "No pattern evidence yet — using the default interval."
    )
