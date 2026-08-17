"""Unit tests for memory.lifecycle_manager.

Uses a real MemoryStore (real temp-file SqliteClient + real temp-dir
ChromaMemoryClient) and a real ConfidenceScorer, matching the "real save,
real reload" convention established since Sprint 2.7 — this module's
whole point is real lifecycle behavior driven by real scoring. A small
local double covers the one failure-injection scenario (a scoring
exception) a real scorer can't easily simulate.
"""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from config.schema import DatabaseConfig, MemoryConfig
from database.sqlite_client import SqliteClient
from memory.chroma_client import ChromaMemoryClient
from memory.confidence_scorer import ConfidenceScorer
from memory.lifecycle_manager import MemoryLifecycleManager
from memory.memory_store import MemoryStore
from memory.models import MemoryRecord, MemoryType
from scheduler.task_scheduler import TaskScheduler

_WAIT_TIMEOUT = 2.0


def _wait_until(predicate, timeout: float = _WAIT_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _ScoreRaisingConfidenceScorer(ConfidenceScorer):
    """A real ConfidenceScorer whose score() always fails for one
    specific record id — everything else (band, override handling)
    behaves normally."""

    def __init__(self, memory_config: MemoryConfig, failing_record_id: str) -> None:
        super().__init__(memory_config)
        self._failing_record_id = failing_record_id

    def score(self, record: MemoryRecord) -> float:
        if record.id == self._failing_record_id:
            raise RuntimeError("scoring exploded")
        return super().score(record)


@pytest.fixture
def database_config(tmp_path):
    return DatabaseConfig(
        sqlite_path=str(tmp_path / "memory.db"), chroma_path=str(tmp_path / "chroma")
    )


@pytest.fixture
def memory_config():
    return MemoryConfig(chroma_collection_prefix="test_memory")


@pytest.fixture
def store(database_config, memory_config):
    sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)
    memory_store = MemoryStore(sqlite_client, chroma_client)
    memory_store.start()
    yield memory_store
    memory_store.stop()


@pytest.fixture
def scorer(memory_config):
    return ConfidenceScorer(memory_config)


@pytest.fixture
def lifecycle_manager(store, scorer, memory_config):
    return MemoryLifecycleManager(store, scorer, memory_config)


def make_temporary_scoring_record(**overrides):
    """A record whose real ConfidenceScorer.score() lands in the
    Temporary band (0-29) with default weights: zero access_count, very
    stale last_accessed_at, and an unrecognized category (falls back to
    category_default_weight=0.5) — no frequency/recency contribution,
    only category (0.15*0.5*100=7.5). emotional_significance defaults to
    0.0 (Sprint 5.3 — a real, disclosed change from the old 0.5 neutral
    placeholder this docstring originally assumed), contributing nothing,
    so the real total is 7.5, not the originally-claimed 15 — still
    comfortably within the Temporary band either way, which is all this
    helper's own callers actually assert."""
    defaults = dict(
        memory_type=MemoryType.SHARED,
        content="a temporary memory",
        category="not_in_the_importance_table",
        access_count=0,
        last_accessed_at=datetime.now(UTC) - timedelta(days=365),
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)


# --- Structural exclusion (defensive) --------------------------------------


def test_run_cleanup_pass_never_touches_is_permanent_records(lifecycle_manager, store):
    record_id = store.store(
        make_temporary_scoring_record(is_permanent=True, confidence_score=5.0)
    )

    report = lifecycle_manager.run_cleanup_pass()

    assert store.get_by_id(record_id) is not None
    assert store.get_by_id(record_id).confidence_score == 5.0
    assert record_id not in report.deleted_record_ids


def test_run_cleanup_pass_never_touches_user_override_records(lifecycle_manager, store):
    record_id = store.store(
        make_temporary_scoring_record(user_override=True, confidence_score=5.0)
    )

    report = lifecycle_manager.run_cleanup_pass()

    assert store.get_by_id(record_id) is not None
    assert store.get_by_id(record_id).confidence_score == 5.0
    assert record_id not in report.deleted_record_ids


def test_run_monthly_review_never_includes_is_permanent_or_override_records(
    lifecycle_manager, store
):
    old_band_entered_at = datetime(2020, 1, 1, tzinfo=UTC)
    store.store(
        make_temporary_scoring_record(
            is_permanent=True, confidence_score=60.0, band_entered_at=old_band_entered_at
        )
    )
    store.store(
        make_temporary_scoring_record(
            user_override=True, confidence_score=60.0, band_entered_at=old_band_entered_at
        )
    )

    report = lifecycle_manager.run_monthly_review()

    assert report.records == []


# --- Cleanup pass: rescoring and grace period -------------------------------


def test_run_cleanup_pass_rescores_and_reports_count(lifecycle_manager, store):
    store.store(make_temporary_scoring_record())
    store.store(make_temporary_scoring_record())

    report = lifecycle_manager.run_cleanup_pass()

    assert report.records_rescored == 2


def test_temporary_record_younger_than_grace_period_survives(memory_config, store, scorer):
    memory_config.cleanup_grace_period_days = 7
    lifecycle_manager = MemoryLifecycleManager(store, scorer, memory_config)
    record_id = store.store(
        make_temporary_scoring_record(created_at=datetime.now(UTC) - timedelta(days=1))
    )

    report = lifecycle_manager.run_cleanup_pass()

    assert record_id not in report.deleted_record_ids
    assert store.get_by_id(record_id) is not None


def test_temporary_record_older_than_grace_period_is_deleted(memory_config, store, scorer):
    memory_config.cleanup_grace_period_days = 7
    lifecycle_manager = MemoryLifecycleManager(store, scorer, memory_config)
    record_id = store.store(
        make_temporary_scoring_record(created_at=datetime.now(UTC) - timedelta(days=8))
    )

    report = lifecycle_manager.run_cleanup_pass()

    assert record_id in report.deleted_record_ids
    assert report.records_deleted == 1
    assert store.get_by_id(record_id) is None


def test_band_entered_at_advances_only_on_a_real_band_change(memory_config, store, scorer):
    lifecycle_manager = MemoryLifecycleManager(store, scorer, memory_config)
    old_band_entered_at = datetime.now(UTC) - timedelta(days=100)
    # already scores Temporary before the pass (confidence_score=15 was
    # never persisted as scored, but band_entered_at should stay put
    # since old_band == new_band == TEMPORARY)
    record_id = store.store(
        make_temporary_scoring_record(
            confidence_score=15.0,
            band_entered_at=old_band_entered_at,
            created_at=datetime.now(UTC),
        )
    )

    lifecycle_manager.run_cleanup_pass()

    assert store.get_by_id(record_id).band_entered_at == old_band_entered_at


def test_band_entered_at_updates_when_band_actually_changes(memory_config, store, scorer):
    lifecycle_manager = MemoryLifecycleManager(store, scorer, memory_config)
    old_band_entered_at = datetime.now(UTC) - timedelta(days=100)
    # confidence_score=95 (Permanent) persisted, but the real formula will
    # rescore it down to Temporary (~15) — a genuine band change
    record_id = store.store(
        make_temporary_scoring_record(confidence_score=95.0, band_entered_at=old_band_entered_at)
    )

    lifecycle_manager.run_cleanup_pass()

    assert store.get_by_id(record_id).band_entered_at > old_band_entered_at


# --- Per-record error isolation --------------------------------------------


def test_one_record_scoring_failure_does_not_abort_the_rest_of_the_pass(store, memory_config):
    good_id = store.store(make_temporary_scoring_record())
    bad_id = store.store(make_temporary_scoring_record())
    failing_scorer = _ScoreRaisingConfidenceScorer(memory_config, failing_record_id=bad_id)
    lifecycle_manager = MemoryLifecycleManager(store, failing_scorer, memory_config)

    report = lifecycle_manager.run_cleanup_pass()

    assert report.records_rescored == 1
    assert len(report.errors) == 1
    assert bad_id in report.errors[0]
    # the good record was still processed despite the bad one failing
    assert store.get_by_id(good_id).confidence_score != 0.0


# --- Monthly review ---------------------------------------------------------


def test_run_monthly_review_performs_no_writes(lifecycle_manager, store):
    record_id = store.store(
        make_temporary_scoring_record(
            confidence_score=60.0,
            band_entered_at=datetime.now(UTC) - timedelta(days=60),
        )
    )
    before = store.get_by_id(record_id)

    lifecycle_manager.run_monthly_review()

    after = store.get_by_id(record_id)
    # only get_by_id()'s own access_count bump should differ; confidence
    # and band_entered_at must be untouched by run_monthly_review() itself
    assert after.confidence_score == before.confidence_score
    assert after.band_entered_at == before.band_entered_at


def test_run_monthly_review_includes_record_old_enough_in_band(memory_config, store, scorer):
    memory_config.monthly_review_min_band_days = 30
    lifecycle_manager = MemoryLifecycleManager(store, scorer, memory_config)
    record_id = store.store(
        make_temporary_scoring_record(
            confidence_score=60.0,
            band_entered_at=datetime.now(UTC) - timedelta(days=31),
        )
    )

    report = lifecycle_manager.run_monthly_review()

    assert record_id in [record.id for record in report.records]


def test_run_monthly_review_excludes_record_too_new_in_band(memory_config, store, scorer):
    memory_config.monthly_review_min_band_days = 30
    lifecycle_manager = MemoryLifecycleManager(store, scorer, memory_config)
    record_id = store.store(
        make_temporary_scoring_record(
            confidence_score=60.0,
            band_entered_at=datetime.now(UTC) - timedelta(days=5),
        )
    )

    report = lifecycle_manager.run_monthly_review()

    assert record_id not in [record.id for record in report.records]


def test_run_monthly_review_excludes_records_outside_the_band(lifecycle_manager, store):
    store.store(
        make_temporary_scoring_record(
            confidence_score=95.0,  # Permanent, not Monthly-review
            band_entered_at=datetime.now(UTC) - timedelta(days=60),
        )
    )

    report = lifecycle_manager.run_monthly_review()

    assert report.records == []


# --- apply_user_override ----------------------------------------------------


def test_apply_user_override_persists_score_and_flag(lifecycle_manager, store):
    record_id = store.store(make_temporary_scoring_record())

    result = lifecycle_manager.apply_user_override(record_id)

    assert result is True
    fetched = store.get_by_id(record_id)
    assert fetched.confidence_score == 100.0
    assert fetched.user_override is True


def test_apply_user_override_returns_false_for_unknown_id(lifecycle_manager):
    assert lifecycle_manager.apply_user_override("no-such-record") is False


# --- ManagedModule lifecycle -------------------------------------------------


def test_health_check_delegates_to_memory_store(lifecycle_manager, store):
    assert lifecycle_manager.health_check() == store.health_check()


def test_start_runs_both_lifecycle_passes_once(lifecycle_manager, store, caplog):
    """Sprint 3.12: start() is the one hook guaranteed to run exactly
    once at real main.py startup (CoreManager.startup() calls every
    registered module's start() once, in registration order) — see this
    module's own docstring for why start() itself, not some other file,
    is where this sprint wires the one-time invocation."""
    temporary_record = make_temporary_scoring_record()
    store.store(temporary_record)

    with caplog.at_level("INFO"):
        lifecycle_manager.start()

    assert any("Startup cleanup pass" in record.message for record in caplog.records)
    assert any("Startup monthly review" in record.message for record in caplog.records)
    # The record was rescored (a real, observable side effect) confirming
    # run_cleanup_pass() genuinely ran, not just logged a claim it did.
    rescored = store.get_by_id(temporary_record.id)
    assert rescored.confidence_score != 0.0


# --- Sprint 6.17 (Async Background Task Audit): TaskScheduler job isolation -------------


def test_a_raising_run_cleanup_pass_does_not_stop_future_recurrence(
    lifecycle_manager, store, monkeypatch
):
    """One of the 12 jobs not yet individually verified against
    TaskScheduler's own explicit max_instances=1, mirroring Sprint
    6.14's own established shape (proactive/test_proactive_assistant.py's
    test_a_raising_tick_does_not_stop_future_recurrence). Unlike the
    per-record failures run_cleanup_pass() already catches internally
    (this file's own test_one_record_scoring_failure_does_not_abort_the_
    rest_of_the_pass), the outer store.recent() call it iterates over has
    no such guard — a real, genuinely propagating exception, the shape
    this sprint's own job-isolation objective actually cares about."""
    task_scheduler = TaskScheduler()
    task_scheduler.start()
    tick_count = 0

    def _raising_recent(memory_type, limit):
        nonlocal tick_count
        tick_count += 1
        raise RuntimeError("MemoryStore.recent() exploded")

    monkeypatch.setattr(store, "recent", _raising_recent)
    task_scheduler.add_job(
        lifecycle_manager.run_cleanup_pass, interval_seconds=0.05, job_id="cleanup-pass-isolation"
    )
    try:
        assert _wait_until(lambda: tick_count >= 3)
        assert task_scheduler.health_check() is True
    finally:
        task_scheduler.stop()


def test_a_raising_run_monthly_review_does_not_stop_future_recurrence(
    lifecycle_manager, store, monkeypatch
):
    """The second of MemoryLifecycleManager's two independently
    registered TaskScheduler jobs — see the sibling run_cleanup_pass
    test immediately above for the full rationale; run_monthly_review()
    has no try/except of its own at all (a pure read query, per its own
    docstring), so store.recent() raising propagates identically."""
    task_scheduler = TaskScheduler()
    task_scheduler.start()
    tick_count = 0

    def _raising_recent(memory_type, limit):
        nonlocal tick_count
        tick_count += 1
        raise RuntimeError("MemoryStore.recent() exploded")

    monkeypatch.setattr(store, "recent", _raising_recent)
    task_scheduler.add_job(
        lifecycle_manager.run_monthly_review,
        interval_seconds=0.05,
        job_id="monthly-review-isolation",
    )
    try:
        assert _wait_until(lambda: tick_count >= 3)
        assert task_scheduler.health_check() is True
    finally:
        task_scheduler.stop()


# --- Sprint 6.19 (Resource Protection & Fail-Gracefully Verification):
# runtime_manager.ensure_started() before touching memory_store (backlog item 53) -------


@pytest.fixture
def runtime_manager():
    return MagicMock()


@pytest.fixture
def lifecycle_manager_with_runtime_manager(store, scorer, memory_config, runtime_manager):
    return MemoryLifecycleManager(store, scorer, memory_config, runtime_manager=runtime_manager)


def test_run_cleanup_pass_ensures_memory_store_started_first(
    lifecycle_manager_with_runtime_manager, runtime_manager
):
    lifecycle_manager_with_runtime_manager.run_cleanup_pass()

    runtime_manager.ensure_started.assert_called_once_with("memory_store")


def test_run_monthly_review_ensures_memory_store_started_first(
    lifecycle_manager_with_runtime_manager, runtime_manager
):
    lifecycle_manager_with_runtime_manager.run_monthly_review()

    runtime_manager.ensure_started.assert_called_once_with("memory_store")


def test_apply_user_override_ensures_memory_store_started_first(
    lifecycle_manager_with_runtime_manager, runtime_manager, store
):
    record_id = store.store(make_temporary_scoring_record())

    lifecycle_manager_with_runtime_manager.apply_user_override(record_id)

    runtime_manager.ensure_started.assert_called_once_with("memory_store")


def test_no_runtime_manager_supplied_behaves_exactly_as_before(lifecycle_manager, store):
    """The default (runtime_manager=None, every existing construction
    site/test in this file) must keep working completely unchanged —
    ensure_started() is purely additive and opt-in via this one
    constructor parameter, matching every other optional cross-cutting
    collaborator in this codebase (e.g. scheduler/task_scheduler.py's
    own resource_monitor, Sprint 6.19's own identical pattern)."""
    record_id = store.store(make_temporary_scoring_record())

    report = lifecycle_manager.run_cleanup_pass()
    review = lifecycle_manager.run_monthly_review()
    override_result = lifecycle_manager.apply_user_override(record_id)

    assert isinstance(report.records_rescored, int)
    assert isinstance(review.records, list)
    assert override_result is True
