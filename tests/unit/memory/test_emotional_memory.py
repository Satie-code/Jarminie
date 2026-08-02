"""Unit tests for memory.emotional_memory.

Real SqliteClient (temp file) + real ChromaMemoryClient (temp directory)
for record_significant_moment()/recall_recent_moments() — mirrors
test_memory_store.py's/test_event_memory.py's own "real save, real
reload" precedent, since this module's whole point is real persistence.
_score_significance() itself is tested as a pure function separately,
no store needed.
"""

from datetime import UTC, datetime

import pytest

from config.schema import DatabaseConfig, MemoryConfig
from database.sqlite_client import SqliteClient
from emotion.state_manager import EmotionalState
from memory.chroma_client import ChromaMemoryClient
from memory.emotional_memory import EmotionalMemory, _score_significance
from memory.memory_store import MemoryStore
from memory.models import MemoryType


@pytest.fixture
def database_config(tmp_path):
    return DatabaseConfig(
        sqlite_path=str(tmp_path / "memory.db"), chroma_path=str(tmp_path / "chroma")
    )


@pytest.fixture
def memory_config():
    return MemoryConfig(chroma_collection_prefix="test_emotional_memory")


@pytest.fixture
def store(database_config, memory_config):
    sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)
    store = MemoryStore(sqlite_client, chroma_client)
    store.start()
    yield store
    store.stop()


@pytest.fixture
def emotional_memory(store, memory_config):
    return EmotionalMemory(store, memory_config)


def _neutral_state() -> EmotionalState:
    return EmotionalState()


def _displaced_state(**overrides) -> EmotionalState:
    defaults = dict(mood=0.0, stress=50.0, comfort=50.0)
    defaults.update(overrides)
    return EmotionalState(**defaults)


class TestScoreSignificance:
    def test_neutral_state_scores_zero(self) -> None:
        assert _score_significance(_neutral_state()) == 0.0

    def test_extreme_stress_scores_near_one(self) -> None:
        state = _displaced_state(stress=100.0)
        assert _score_significance(state) == pytest.approx(1.0)

    def test_extreme_positive_mood_scores_near_one(self) -> None:
        state = _displaced_state(mood=100.0)
        assert _score_significance(state) == pytest.approx(1.0)

    def test_extreme_negative_mood_scores_near_one(self) -> None:
        state = _displaced_state(mood=-100.0)
        assert _score_significance(state) == pytest.approx(1.0)

    def test_extreme_low_comfort_scores_near_one(self) -> None:
        state = _displaced_state(comfort=0.0)
        assert _score_significance(state) == pytest.approx(1.0)

    def test_multiple_displaced_dimensions_uses_the_maximum(self) -> None:
        # stress displaced by 0.4 of its half-range, mood by 0.9 of its own.
        state = _displaced_state(stress=70.0, mood=90.0)
        assert _score_significance(state) == pytest.approx(0.9)

    def test_result_always_within_bounds(self) -> None:
        state = _displaced_state(stress=100.0, mood=100.0, comfort=0.0)
        score = _score_significance(state)
        assert 0.0 <= score <= 1.0


class TestRecordSignificantMoment:
    def test_persists_a_real_record_with_computed_significance(
        self, emotional_memory: EmotionalMemory, store: MemoryStore
    ) -> None:
        state = _displaced_state(stress=100.0)
        record_id = emotional_memory.record_significant_moment(
            content="a genuinely stressful deadline",
            memory_type=MemoryType.SHARED,
            category="project",
            state=state,
        )

        fetched = store.get_by_id(record_id)
        assert fetched is not None
        assert fetched.content == "a genuinely stressful deadline"
        assert fetched.emotional_significance == pytest.approx(1.0)

    def test_occurred_at_is_honored(
        self, emotional_memory: EmotionalMemory, store: MemoryStore
    ) -> None:
        occurred = datetime(2026, 6, 1, tzinfo=UTC)
        record_id = emotional_memory.record_significant_moment(
            content="a milestone-adjacent moment",
            memory_type=MemoryType.MINIE,
            category="wellness",
            state=_neutral_state(),
            occurred_at=occurred,
        )
        fetched = store.get_by_id(record_id)
        assert fetched.occurred_at == occurred

    @pytest.mark.parametrize("memory_type", [MemoryType.EVENT, MemoryType.SHORT_TERM])
    def test_rejects_event_and_short_term_memory_types(
        self, emotional_memory: EmotionalMemory, memory_type: MemoryType
    ) -> None:
        with pytest.raises(ValueError, match="EVENT/SHORT_TERM"):
            emotional_memory.record_significant_moment(
                content="should not be allowed",
                memory_type=memory_type,
                category="x",
                state=_neutral_state(),
            )

    @pytest.mark.parametrize(
        "memory_type", [MemoryType.SHARED, MemoryType.JARVIS, MemoryType.MINIE]
    )
    def test_accepts_every_allowed_memory_type(
        self, emotional_memory: EmotionalMemory, memory_type: MemoryType
    ) -> None:
        record_id = emotional_memory.record_significant_moment(
            content="fine", memory_type=memory_type, category="x", state=_neutral_state()
        )
        assert record_id


class TestRecallRecentMoments:
    def test_filters_below_threshold(
        self, emotional_memory: EmotionalMemory, memory_config: MemoryConfig
    ) -> None:
        emotional_memory.record_significant_moment(
            content="barely notable",
            memory_type=MemoryType.SHARED,
            category="x",
            state=_displaced_state(stress=55.0),  # well below the 0.6 default threshold
        )
        results = emotional_memory.recall_recent_moments(MemoryType.SHARED)
        assert results == []

    def test_surfaces_records_at_or_above_threshold(
        self, emotional_memory: EmotionalMemory
    ) -> None:
        emotional_memory.record_significant_moment(
            content="a real stress spike",
            memory_type=MemoryType.SHARED,
            category="x",
            state=_displaced_state(stress=95.0),
        )
        results = emotional_memory.recall_recent_moments(MemoryType.SHARED)
        assert len(results) == 1
        assert results[0].content == "a real stress spike"

    def test_orders_most_significant_first(self, emotional_memory: EmotionalMemory) -> None:
        emotional_memory.record_significant_moment(
            content="moderately significant",
            memory_type=MemoryType.SHARED,
            category="x",
            state=_displaced_state(stress=80.0),
        )
        emotional_memory.record_significant_moment(
            content="highly significant",
            memory_type=MemoryType.SHARED,
            category="x",
            state=_displaced_state(stress=100.0),
        )
        results = emotional_memory.recall_recent_moments(MemoryType.SHARED)
        assert [record.content for record in results] == [
            "highly significant",
            "moderately significant",
        ]

    def test_respects_limit(self, emotional_memory: EmotionalMemory) -> None:
        for i in range(3):
            emotional_memory.record_significant_moment(
                content=f"significant moment {i}",
                memory_type=MemoryType.SHARED,
                category="x",
                state=_displaced_state(stress=90.0),
            )
        results = emotional_memory.recall_recent_moments(MemoryType.SHARED, limit=2)
        assert len(results) == 2

    def test_scoped_to_requested_memory_type_only(
        self, emotional_memory: EmotionalMemory
    ) -> None:
        emotional_memory.record_significant_moment(
            content="a jarvis-scoped moment",
            memory_type=MemoryType.JARVIS,
            category="x",
            state=_displaced_state(stress=95.0),
        )
        results = emotional_memory.recall_recent_moments(MemoryType.MINIE)
        assert results == []

    def test_empty_store_returns_empty_list(self, emotional_memory: EmotionalMemory) -> None:
        assert emotional_memory.recall_recent_moments(MemoryType.SHARED) == []
