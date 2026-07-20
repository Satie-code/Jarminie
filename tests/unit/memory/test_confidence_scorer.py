"""Unit tests for memory.confidence_scorer.

No MemoryStore/database/Chroma fixture needed anywhere in this file —
ConfidenceScorer is a pure function of a MemoryRecord's fields plus
MemoryConfig, per this sprint's own Architecture Notes.
"""

from datetime import UTC, datetime, timedelta

import pytest

from config.errors import ConfigError
from config.schema import AppConfig, MemoryConfig
from memory.confidence_scorer import ConfidenceBand, ConfidenceScorer
from memory.models import MemoryRecord, MemoryType


@pytest.fixture
def memory_config():
    return MemoryConfig()


@pytest.fixture
def scorer(memory_config):
    return ConfidenceScorer(memory_config)


def make_record(**overrides):
    defaults = dict(
        memory_type=MemoryType.SHARED,
        content="some memory",
        category=None,
        access_count=0,
        last_accessed_at=datetime.now(UTC),
        user_override=False,
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)


# --- Frequency factor -------------------------------------------------


def test_higher_access_count_produces_higher_score(scorer):
    low = make_record(access_count=0)
    high = make_record(access_count=50)

    assert scorer.score(high) > scorer.score(low)


def test_frequency_factor_has_diminishing_returns(scorer):
    score_0 = scorer.score(make_record(access_count=0))
    score_1 = scorer.score(make_record(access_count=1))
    score_10 = scorer.score(make_record(access_count=10))
    score_100 = scorer.score(make_record(access_count=100))

    # each doubling-ish step adds progressively less
    assert (score_1 - score_0) > (score_10 - score_1) / 9
    assert (score_100 - score_10) < (score_10 - score_1)


# --- Recency factor -----------------------------------------------------


def test_more_recent_last_accessed_at_produces_higher_score(scorer):
    recent = make_record(last_accessed_at=datetime.now(UTC))
    stale = make_record(last_accessed_at=datetime.now(UTC) - timedelta(days=60))

    assert scorer.score(recent) > scorer.score(stale)


def test_recency_factor_at_half_life_is_half(memory_config):
    memory_config.recency_half_life_days = 14.0
    scorer = ConfidenceScorer(memory_config)
    fresh = make_record(last_accessed_at=datetime.now(UTC))
    at_half_life = make_record(last_accessed_at=datetime.now(UTC) - timedelta(days=14))

    fresh_score = scorer.score(fresh)
    half_life_score = scorer.score(at_half_life)

    # recency contributes recency_weight (0.25) * 100 = 25 points at full
    # strength; at exactly one half-life it should contribute ~half that,
    # so the two scores should differ by roughly 12.5 (holding frequency/
    # category/emotional constant since both records are otherwise equal)
    assert abs((fresh_score - half_life_score) - 12.5) < 0.5


# --- Category factor ------------------------------------------------------


def test_known_category_uses_configured_importance(memory_config):
    memory_config.category_importance = {"project": 1.0}
    memory_config.category_default_weight = 0.0
    scorer = ConfidenceScorer(memory_config)
    project_record = make_record(category="project")
    unknown_record = make_record(category="something_else")

    assert scorer.score(project_record) > scorer.score(unknown_record)


def test_unknown_category_falls_back_to_default_weight(memory_config):
    memory_config.category_importance = {"project": 0.9}
    memory_config.category_default_weight = 0.5
    scorer = ConfidenceScorer(memory_config)

    record = make_record(category="not_in_the_table")

    # category factor should be exactly category_default_weight (0.5),
    # contributing category_weight * 0.5 * 100 to the total
    expected_category_contribution = memory_config.category_weight * 0.5 * 100
    frequency_contribution = 0.0  # access_count=0 -> frequency_factor=0
    recency_contribution = memory_config.recency_weight * 1.0 * 100  # just accessed
    emotional_contribution = memory_config.emotional_weight * 0.5 * 100
    expected = (
        frequency_contribution
        + recency_contribution
        + expected_category_contribution
        + emotional_contribution
    )
    assert scorer.score(record) == pytest.approx(expected, abs=0.01)


def test_none_category_falls_back_to_default_weight(memory_config):
    scorer = ConfidenceScorer(memory_config)
    with_category = make_record(category=None)

    # must not raise and must use category_default_weight
    scorer.score(with_category)


# --- Sprint 3.13 hardening (scenario c): edge cases --------------------------


def test_zero_elapsed_time_since_last_accessed_does_not_raise(scorer):
    """last_accessed_at == now (effectively created_at == last_accessed_at
    for a freshly-created record) must not divide by zero in the recency
    decay curve — elapsed_days == 0 should just mean "no decay yet"
    (recency_factor == 1.0), not an error."""
    now = datetime.now(UTC)
    record = make_record(created_at=now, last_accessed_at=now, access_count=0)

    score = scorer.score(record)

    assert score == score  # not NaN
    assert 0.0 <= score <= 100.0


def test_access_count_zero_produces_a_valid_low_frequency_term(scorer):
    """A freshly-created, never-yet-read record (access_count=0) must
    score without error, with frequency_factor == 0/(0+1) == 0 — the
    lowest possible frequency contribution, not a crash."""
    record = make_record(access_count=0)

    score = scorer.score(record)

    assert score == score  # not NaN
    assert 0.0 <= score <= 100.0


# recency_half_life_days appears only in score()'s denominator — the real
# zero-division risk this scenario guards against lives at the config
# layer, already covered by test_non_positive_recency_half_life_raises()
# further below, not by a MemoryRecord's own fields.


# --- User override short-circuit -----------------------------------------


def test_user_override_always_scores_100_regardless_of_other_fields(scorer):
    record = make_record(
        access_count=0,
        last_accessed_at=datetime.now(UTC) - timedelta(days=365),
        category=None,
        user_override=True,
    )

    assert scorer.score(record) == 100.0


def test_apply_user_override_sets_score_and_flag(scorer):
    record = make_record(access_count=0, user_override=False)

    overridden = scorer.apply_user_override(record)

    assert overridden.confidence_score == 100.0
    assert overridden.user_override is True


def test_apply_user_override_does_not_mutate_input(scorer):
    record = make_record(user_override=False)

    scorer.apply_user_override(record)

    assert record.user_override is False
    assert record.confidence_score == 0.0


# --- Override phrase detection ---------------------------------------------


@pytest.mark.parametrize(
    "transcript",
    ["remember this", "REMEMBER THIS", "please remember this forever",
     "never forget this", "this is important"],
)
def test_detect_override_phrase_matches_configured_phrases(scorer, transcript):
    assert scorer.detect_override_phrase(transcript) is True


def test_detect_override_phrase_no_match_on_unrelated_text(scorer):
    assert scorer.detect_override_phrase("what's the weather like today") is False


# --- Band boundaries ------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected_band",
    [
        (0, ConfidenceBand.TEMPORARY),
        (29, ConfidenceBand.TEMPORARY),
        (30, ConfidenceBand.SHORT_TERM),
        (49, ConfidenceBand.SHORT_TERM),
        (50, ConfidenceBand.MONTHLY_REVIEW),
        (69, ConfidenceBand.MONTHLY_REVIEW),
        (70, ConfidenceBand.LONG_TERM),
        (89, ConfidenceBand.LONG_TERM),
        (90, ConfidenceBand.PERMANENT),
        (100, ConfidenceBand.PERMANENT),
    ],
)
def test_band_boundaries(scorer, score, expected_band):
    assert scorer.band(score) == expected_band


# --- Score clamping / un-overridden ceiling --------------------------------


def test_score_never_exceeds_80_without_override_at_default_weights(memory_config):
    """importance_weight has no term in the formula (see this module's
    docstring) — with the default weights, the maximum achievable
    un-overridden score is (frequency + recency + category + emotional)
    weights * 100 = 80."""
    memory_config.category_importance = {"best": 1.0}
    scorer = ConfidenceScorer(memory_config)
    maximally_favorable = make_record(
        access_count=10_000, last_accessed_at=datetime.now(UTC), category="best"
    )

    assert scorer.score(maximally_favorable) <= 80.0 + 1e-6


# --- Config validation ------------------------------------------------------


def test_default_memory_config_weights_sum_to_one():
    AppConfig().validate()  # must not raise


def test_weights_not_summing_to_one_raises():
    config = AppConfig(memory=MemoryConfig(frequency_weight=0.5))
    with pytest.raises(ConfigError, match="sum to 1.0"):
        config.validate()


def test_negative_weight_raises():
    config = AppConfig(memory=MemoryConfig(frequency_weight=-0.1, recency_weight=0.35))
    with pytest.raises(ConfigError, match="frequency_weight"):
        config.validate()


def test_non_positive_recency_half_life_raises():
    config = AppConfig(memory=MemoryConfig(recency_half_life_days=0))
    with pytest.raises(ConfigError, match="recency_half_life_days"):
        config.validate()


def test_category_default_weight_out_of_range_raises():
    config = AppConfig(memory=MemoryConfig(category_default_weight=1.5))
    with pytest.raises(ConfigError, match="category_default_weight"):
        config.validate()


def test_category_importance_value_out_of_range_raises():
    config = AppConfig(memory=MemoryConfig(category_importance={"project": 1.5}))
    with pytest.raises(ConfigError, match="category_importance"):
        config.validate()


def test_empty_override_trigger_phrases_raises():
    config = AppConfig(memory=MemoryConfig(override_trigger_phrases=[]))
    with pytest.raises(ConfigError, match="override_trigger_phrases"):
        config.validate()
