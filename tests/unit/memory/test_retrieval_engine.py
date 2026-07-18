"""Unit tests for memory.retrieval_engine.

Uses local fake doubles for PersonaScopedMemory/EventMemory/
ShortTermMemory (which would otherwise require real SQLite/Chroma I/O),
but a REAL ConfidenceScorer — it's a pure, cheap, side-effect-free
function of a MemoryRecord + MemoryConfig, matching the precedent
test_lifecycle_manager.py (Sprint 3.6) already established of using a
real ConfidenceScorer wherever a fake isn't actually needed.
"""

import pytest

from config.errors import ConfigError
from config.schema import AppConfig, MemoryConfig
from memory.confidence_scorer import ConfidenceScorer
from memory.models import MemoryRecord, MemoryType
from memory.retrieval_engine import MemoryRetrievalEngine


class FakePersonaScopedMemory:
    def __init__(self, results: list[tuple[MemoryRecord, float]] | None = None) -> None:
        self._results = results or []
        self.calls: list[tuple[str, str]] = []

    def recall_for_persona_scored(self, persona_name, query_text, n_results=5):
        self.calls.append((persona_name, query_text))
        return self._results


class FakeEventMemory:
    def __init__(self, results: list[tuple[MemoryRecord, float]] | None = None) -> None:
        self._results = results or []
        self.calls: list[str] = []

    def search_milestones_scored(self, query_text, n_results=5):
        self.calls.append(query_text)
        return self._results


class FakeShortTermMemory:
    def __init__(self, records: list[MemoryRecord] | None = None) -> None:
        self._records = records or []
        self.calls: list[str] = []

    def active_context_memories(self, session_id):
        self.calls.append(session_id)
        return self._records


def make_record(content: str = "some content", confidence_score: float = 50.0) -> MemoryRecord:
    return MemoryRecord(
        memory_type=MemoryType.SHARED, content=content, confidence_score=confidence_score
    )


@pytest.fixture
def memory_config() -> MemoryConfig:
    return MemoryConfig()


@pytest.fixture
def confidence_scorer(memory_config) -> ConfidenceScorer:
    return ConfidenceScorer(memory_config)


def make_engine(
    memory_config,
    confidence_scorer,
    persona_results=None,
    event_results=None,
    short_term_records=None,
):
    return MemoryRetrievalEngine(
        persona_scoped_memory=FakePersonaScopedMemory(persona_results),
        event_memory=FakeEventMemory(event_results),
        short_term_memory=FakeShortTermMemory(short_term_records),
        confidence_scorer=confidence_scorer,
        memory_config=memory_config,
    )


# --- Delegation / cross-persona leak ----------------------------------------


def test_retrieve_passes_persona_name_and_query_through_unchanged(memory_config, confidence_scorer):
    persona_memory = FakePersonaScopedMemory([])
    engine = MemoryRetrievalEngine(
        persona_scoped_memory=persona_memory,
        event_memory=FakeEventMemory([]),
        short_term_memory=FakeShortTermMemory([]),
        confidence_scorer=confidence_scorer,
        memory_config=memory_config,
    )

    engine.retrieve("what's my favorite hobby", "jarvis", "session-1")

    assert persona_memory.calls == [("jarvis", "what's my favorite hobby")]


def test_retrieve_never_adds_results_beyond_what_persona_scoped_memory_returns(
    memory_config, confidence_scorer
):
    """MemoryRetrievalEngine must fully trust PersonaScopedMemory's own
    read-scoping guarantee (Sprint 3.2) rather than re-querying or
    supplementing it — this composition layer introduces no way for a
    cross-persona record to appear that recall_for_persona_scored()
    itself didn't return."""
    only_allowed = make_record("the one allowed record")
    engine = make_engine(
        memory_config, confidence_scorer, persona_results=[(only_allowed, 0.2)]
    )

    results = engine.retrieve("query", "jarvis", "session-1")

    assert [r.record.content for r in results] == ["the one allowed record"]


# --- Weight-blend ranking ----------------------------------------------------


def test_combined_rank_score_blend_flips_with_different_weights(confidence_scorer):
    """Proves combined_rank_score is a genuine blend, not one field
    renamed: a high-confidence/lower-similarity record outranks a
    low-confidence/higher-similarity one under one weight pair, and the
    ranking flips under a different weight pair."""
    high_confidence_low_similarity = make_record("A", confidence_score=95.0)
    low_confidence_high_similarity = make_record("B", confidence_score=10.0)
    persona_results = [
        (high_confidence_low_similarity, 3.0),  # distance 3.0 -> similarity 0.25
        (low_confidence_high_similarity, 0.05),  # distance 0.05 -> similarity ~0.952
    ]

    confidence_heavy_config = MemoryConfig(
        retrieval_similarity_weight=0.1, retrieval_confidence_weight=0.9
    )
    engine_confidence_heavy = make_engine(
        confidence_heavy_config, confidence_scorer, persona_results=persona_results
    )
    results_confidence_heavy = engine_confidence_heavy.retrieve("q", "jarvis", "s1")
    assert results_confidence_heavy[0].record.content == "A"

    similarity_heavy_config = MemoryConfig(
        retrieval_similarity_weight=0.9, retrieval_confidence_weight=0.1
    )
    engine_similarity_heavy = make_engine(
        similarity_heavy_config, confidence_scorer, persona_results=persona_results
    )
    results_similarity_heavy = engine_similarity_heavy.retrieve("q", "jarvis", "s1")
    assert results_similarity_heavy[0].record.content == "B"


# --- retrieval_reason content -------------------------------------------------


@pytest.mark.parametrize(
    ("confidence_score", "expected_band_label"),
    [
        (10.0, "Temporary"),
        (40.0, "Short-term"),
        (60.0, "Monthly-review"),
        (80.0, "Long-term"),
        (95.0, "Permanent"),
    ],
)
def test_retrieval_reason_contains_similarity_and_band_confidence(
    memory_config, confidence_scorer, confidence_score, expected_band_label
):
    record = make_record("some content", confidence_score=confidence_score)
    engine = make_engine(memory_config, confidence_scorer, persona_results=[(record, 0.0)])

    results = engine.retrieve("query", "jarvis", "session-1")

    reason = results[0].retrieval_reason
    assert reason
    assert "100% similar" in reason
    assert expected_band_label in reason
    assert f"{confidence_score:.0f}/100" in reason


# --- max_results truncation ---------------------------------------------------


def test_retrieve_truncates_to_configured_max_results(memory_config, confidence_scorer):
    persona_results = [(make_record(f"record {i}"), 0.1 * i) for i in range(10)]
    memory_config.max_retrieval_results = 3
    engine = make_engine(memory_config, confidence_scorer, persona_results=persona_results)

    results = engine.retrieve("query", "jarvis", "session-1")

    assert len(results) == 3


def test_retrieve_max_results_argument_overrides_config_default(memory_config, confidence_scorer):
    persona_results = [(make_record(f"record {i}"), 0.1 * i) for i in range(10)]
    engine = make_engine(memory_config, confidence_scorer, persona_results=persona_results)

    results = engine.retrieve("query", "jarvis", "session-1", max_results=2)

    assert len(results) == 2


# --- empty / irrelevant query --------------------------------------------------


def test_retrieve_returns_empty_list_for_empty_query_without_querying_anything(
    memory_config, confidence_scorer
):
    persona_memory = FakePersonaScopedMemory([(make_record(), 0.1)])
    event_memory = FakeEventMemory([(make_record(), 0.1)])
    short_term_memory = FakeShortTermMemory([make_record()])
    engine = MemoryRetrievalEngine(
        persona_scoped_memory=persona_memory,
        event_memory=event_memory,
        short_term_memory=short_term_memory,
        confidence_scorer=confidence_scorer,
        memory_config=memory_config,
    )

    results = engine.retrieve("", "jarvis", "session-1")

    assert results == []
    assert persona_memory.calls == []
    assert event_memory.calls == []
    assert short_term_memory.calls == []


def test_retrieve_returns_empty_list_for_whitespace_only_query(memory_config, confidence_scorer):
    engine = make_engine(memory_config, confidence_scorer)

    assert engine.retrieve("   ", "jarvis", "session-1") == []


def test_event_memory_result_below_similarity_threshold_is_excluded(
    memory_config, confidence_scorer
):
    """An unrelated query still gets nearest-neighbor results back from a
    semantic search (Chroma always returns its nearest matches, however
    poor) — this proves MemoryRetrievalEngine filters those out rather
    than trusting them as relevant just because they were returned."""
    unrelated_milestone = make_record("finished my computer science degree")
    engine = make_engine(
        memory_config, confidence_scorer, event_results=[(unrelated_milestone, 5.0)]
    )

    results = engine.retrieve("what's the weather like", "jarvis", "session-1")

    assert results == []


def test_event_memory_result_above_similarity_threshold_is_included(
    memory_config, confidence_scorer
):
    relevant_milestone = make_record("finished my computer science degree")
    engine = make_engine(
        memory_config, confidence_scorer, event_results=[(relevant_milestone, 0.1)]
    )

    results = engine.retrieve("tell me about my degree", "jarvis", "session-1")

    assert len(results) == 1
    assert results[0].record.content == "finished my computer science degree"


def test_short_term_memory_with_no_keyword_overlap_is_excluded(memory_config, confidence_scorer):
    unrelated_context = make_record("we talked about the weather earlier")
    engine = make_engine(
        memory_config, confidence_scorer, short_term_records=[unrelated_context]
    )

    results = engine.retrieve("what's my favorite programming language", "jarvis", "session-1")

    assert results == []


def test_short_term_memory_with_keyword_overlap_is_included(memory_config, confidence_scorer):
    relevant_context = make_record("the user mentioned their favorite programming language")
    engine = make_engine(
        memory_config, confidence_scorer, short_term_records=[relevant_context]
    )

    results = engine.retrieve("what's my favorite programming language", "jarvis", "session-1")

    assert len(results) == 1
    assert results[0].record.content == "the user mentioned their favorite programming language"


def test_short_term_memory_queried_by_session_id(memory_config, confidence_scorer):
    short_term_memory = FakeShortTermMemory([])
    engine = MemoryRetrievalEngine(
        persona_scoped_memory=FakePersonaScopedMemory([]),
        event_memory=FakeEventMemory([]),
        short_term_memory=short_term_memory,
        confidence_scorer=confidence_scorer,
        memory_config=memory_config,
    )

    engine.retrieve("query", "jarvis", "session-42")

    assert short_term_memory.calls == ["session-42"]


# --- MemoryConfig validation --------------------------------------------------


def test_default_retrieval_weights_sum_to_one():
    AppConfig().validate()  # must not raise


def test_retrieval_weights_not_summing_to_one_raises():
    config = AppConfig(memory=MemoryConfig(retrieval_similarity_weight=0.5))
    with pytest.raises(ConfigError, match="retrieval.*sum to 1.0"):
        config.validate()


def test_negative_retrieval_weight_raises():
    config = AppConfig(
        memory=MemoryConfig(retrieval_similarity_weight=-0.1, retrieval_confidence_weight=1.1)
    )
    with pytest.raises(ConfigError, match="retrieval_similarity_weight"):
        config.validate()


def test_non_positive_max_retrieval_results_raises():
    config = AppConfig(memory=MemoryConfig(max_retrieval_results=0))
    with pytest.raises(ConfigError, match="max_retrieval_results"):
        config.validate()
