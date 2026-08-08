"""Unit tests for learning.recommendation.

RecommendationEngine is exercised against a duck-typed fake PatternStore
(only list_all() is needed, matching the real class's own contract) —
PatternStore's own persistence logic is already covered by
tests/unit/learning/test_pattern_store.py (Sprint 5.21).
"""

import ast
import os
from datetime import UTC, datetime

from config.schema import LearningConfig
from learning.pattern_model import LearnedPattern, PatternType
from learning.recommendation import Recommendation, RecommendationEngine

_NOW = datetime(2026, 8, 4, 15, 0, tzinfo=UTC)


class _FakePatternStore:
    def __init__(self, patterns: list[LearnedPattern]) -> None:
        self._patterns = patterns

    def list_all(self) -> list[LearnedPattern]:
        return list(self._patterns)


def _pattern(pattern_type: PatternType, subject: str, confidence: float = 0.8) -> LearnedPattern:
    return LearnedPattern(
        pattern_type=pattern_type,
        description="d",
        subject=subject,
        confidence=confidence,
        evidence_count=5,
        first_observed_at=_NOW,
        last_updated_at=_NOW,
    )


def _engine(patterns, **config_overrides):
    store = _FakePatternStore(patterns)
    config = LearningConfig(**config_overrides)
    return RecommendationEngine(store, config)


# --- per-PatternType template formatting -----------------------------------------------------


def test_generate_recommendations_formats_frequent_application():
    engine = _engine([_pattern(PatternType.FREQUENT_APPLICATION, "code.exe")])

    recommendations = engine.generate_recommendations()

    assert len(recommendations) == 1
    assert "code.exe" in recommendations[0].text


def test_generate_recommendations_formats_preferred_time():
    engine = _engine([_pattern(PatternType.PREFERRED_TIME, "14-16")])

    recommendations = engine.generate_recommendations()

    assert len(recommendations) == 1
    assert "14-16" in recommendations[0].text


def test_generate_recommendations_formats_work_habit():
    engine = _engine([_pattern(PatternType.WORK_HABIT, "coding")])

    recommendations = engine.generate_recommendations()

    assert len(recommendations) == 1
    assert "coding" in recommendations[0].text


def test_generate_recommendations_formats_conversation_style():
    engine = _engine([_pattern(PatternType.CONVERSATION_STYLE, "jarvis")])

    recommendations = engine.generate_recommendations()

    assert len(recommendations) == 1
    assert "jarvis" in recommendations[0].text


def test_generate_recommendations_formats_preferred_workflow():
    engine = _engine([_pattern(PatternType.PREFERRED_WORKFLOW, "wf-1")])

    recommendations = engine.generate_recommendations()

    assert len(recommendations) == 1
    assert "wf-1" in recommendations[0].text


def test_generate_recommendations_formats_preferred_tool():
    engine = _engine([_pattern(PatternType.PREFERRED_TOOL, "code.exe")])

    recommendations = engine.generate_recommendations()

    assert len(recommendations) == 1
    assert "code.exe" in recommendations[0].text


def test_generate_recommendations_formats_daily_routine():
    engine = _engine([_pattern(PatternType.DAILY_ROUTINE, "09-11")])

    recommendations = engine.generate_recommendations()

    assert len(recommendations) == 1
    assert "09-11" in recommendations[0].text


def test_generate_recommendations_formats_study_schedule():
    engine = _engine([_pattern(PatternType.STUDY_SCHEDULE, "20-22")])

    recommendations = engine.generate_recommendations()

    assert len(recommendations) == 1
    assert "20-22" in recommendations[0].text


def test_generate_recommendations_sets_based_on_pattern_id():
    pattern = _pattern(PatternType.FREQUENT_APPLICATION, "code.exe")
    engine = _engine([pattern])

    recommendation = engine.generate_recommendations()[0]

    assert recommendation.based_on_pattern_id == pattern.pattern_id


# --- untemplated pattern type produces no recommendation --------------------------------------


def test_generate_recommendations_produces_nothing_for_an_untemplated_pattern_type():
    engine = _engine(
        [_pattern(PatternType.FREQUENT_APPLICATION, "code.exe")],
        recommendation_templates={},
    )

    assert engine.generate_recommendations() == []


def test_generate_recommendations_skips_only_the_untemplated_pattern():
    engine = _engine(
        [
            _pattern(PatternType.FREQUENT_APPLICATION, "code.exe"),
            _pattern(PatternType.WORK_HABIT, "coding"),
        ],
        recommendation_templates={
            "frequent_application": "Uses {subject} a lot.",
        },
    )

    recommendations = engine.generate_recommendations()

    assert len(recommendations) == 1
    assert "code.exe" in recommendations[0].text


# --- idempotency -------------------------------------------------------------------------------


def test_generate_recommendations_is_idempotent_against_unchanged_data():
    engine = _engine(
        [
            _pattern(PatternType.FREQUENT_APPLICATION, "code.exe"),
            _pattern(PatternType.WORK_HABIT, "coding"),
        ]
    )

    first = engine.generate_recommendations()
    second = engine.generate_recommendations()

    first_shape = sorted((r.text, r.based_on_pattern_id) for r in first)
    second_shape = sorted((r.text, r.based_on_pattern_id) for r in second)
    assert first_shape == second_shape


def test_generate_recommendations_with_no_patterns_returns_an_empty_list():
    engine = _engine([])

    assert engine.generate_recommendations() == []


# --- dataclass shape -----------------------------------------------------------------------


def test_recommendation_generates_a_recommendation_id_when_not_supplied():
    recommendation = Recommendation(text="t", based_on_pattern_id="p", generated_at=_NOW)

    assert recommendation.recommendation_id


# --- static: no LLM-facing import anywhere in learning/recommendation.py ----------------------


def test_recommendation_module_imports_no_llm_facing_module():
    """AST-based, not a substring scan — mirrors tests/unit/wellness/
    test_wellness_tracker.py's own import-boundary check precedent.
    Confirms no LanguageModelClient/decision.llm_client import anywhere in
    learning/recommendation.py, the mechanical half of this sprint's own
    "templated, never LLM-generated" Acceptance Criterion."""
    module_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "learning", "recommendation.py"
    )
    with open(module_path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=module_path)

    top_level_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            top_level_imports.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.append(node.module.split(".")[0])

    assert "decision" not in top_level_imports
