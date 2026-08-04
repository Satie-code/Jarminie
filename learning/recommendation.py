"""Recommendations — the Learning Engine's own "may recommend
improvements" half. See docs/sprint_book/sprint_5/sprint_5_23.md.

**Recommendations are templated, never LLM-generated, and never auto-
executed** — the literal implementation of Part 2's own "may recommend...
never makes major autonomous decisions" and Phase 5.4's "No unpredictable
behavior" Acceptance Criterion. RecommendationEngine composes
LearnedPatterns (Sprint 5.21/5.23) into a small, fixed set of pre-written
templates (config/schema.py's LearningConfig.recommendation_templates) —
no LanguageModelClient call, and no import of decision/llm_client.py or
any other LLM-facing module, anywhere in this file (verified mechanically
by tests/unit/learning/test_recommendation.py's own AST-based check).
A recommendation whose exact wording could vary run-to-run for the same
underlying pattern would itself be a form of the unpredictable behavior
Phase 5.4 rules out — even though a real LanguageModelClient is already
available elsewhere in this codebase (decision/llm_client.py), it is
deliberately not used here.

RecommendationEngine never reaches back into MemoryStore/UsageStore
itself — it only ever reads PatternStore, keeping the Learning Engine's
own two halves (detecting patterns; recommending from them) as cleanly
separated as Sprint 5.18/5.19's Wellness trigger/escalation split and
Sprint 5.17/5.20's Analytics tracker/dashboard split.

generate_recommendations() is deliberately stateless and idempotent —
calling it twice against unchanged PatternStore data produces the same
recommendations again (same text, same based_on_pattern_id; a fresh
recommendation_id/generated_at each call, the same "re-evaluated fresh
every call, no caching" precedent AnalyticsDashboardService (Sprint 5.20)
already established). Deduplication against what has already been
shown/acted on is Sprint 5.24's own live-caller concern, not this
sprint's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from config.schema import LearningConfig
from learning.pattern_store import PatternStore


@dataclass
class Recommendation:
    text: str
    based_on_pattern_id: str
    generated_at: datetime
    recommendation_id: str = field(default_factory=lambda: str(uuid4()))


class RecommendationEngine:
    """Constructor DI: (pattern_store, learning_config)."""

    def __init__(self, pattern_store: PatternStore, learning_config: LearningConfig) -> None:
        self._pattern_store = pattern_store
        self._config = learning_config

    def generate_recommendations(self) -> list[Recommendation]:
        """Reads pattern_store.list_all(); for every LearnedPattern whose
        pattern_type has a configured template in recommendation_templates,
        formats one Recommendation. A pattern type with no configured
        template produces no recommendation — never a raw/untemplated
        fallback string."""
        now = datetime.now(UTC)
        recommendations: list[Recommendation] = []
        for pattern in self._pattern_store.list_all():
            template = self._config.recommendation_templates.get(pattern.pattern_type.value)
            if template is None:
                continue
            recommendations.append(
                Recommendation(
                    text=template.format(subject=pattern.subject),
                    based_on_pattern_id=pattern.pattern_id,
                    generated_at=now,
                )
            )
        return recommendations
