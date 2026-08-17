"""Unit tests for analytics.usage_store."""

from datetime import UTC, datetime, timedelta

import pytest

from analytics.usage_model import AppFocusSample
from analytics.usage_store import UsageStore
from config.schema import AnalyticsConfig
from database.sqlite_client import SqliteClient

_NOW = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)


def make_sample(
    sample_id: str = "sample-1",
    process_name: str = "devenv.exe",
    window_title: str = "JARMINEI - Visual Studio",
    sampled_at: datetime = _NOW,
) -> AppFocusSample:
    return AppFocusSample(
        sample_id=sample_id,
        process_name=process_name,
        window_title=window_title,
        sampled_at=sampled_at,
    )


@pytest.fixture
def store(tmp_path) -> UsageStore:
    client = SqliteClient(str(tmp_path / "usage.db"))
    usage_store = UsageStore(client, AnalyticsConfig())
    usage_store.start()
    yield usage_store
    usage_store.stop()


# --- record_sample()/list_samples_since() round trip -------------------------------


def test_record_sample_round_trip_preserves_every_field(store):
    sample = make_sample()

    store.record_sample(sample)
    fetched = store.list_samples_since(_NOW - timedelta(minutes=1))

    assert len(fetched) == 1
    assert fetched[0].sample_id == sample.sample_id
    assert fetched[0].process_name == sample.process_name
    assert fetched[0].window_title == sample.window_title
    assert fetched[0].sampled_at == sample.sampled_at


def test_list_samples_since_excludes_samples_before_the_window(store):
    store.record_sample(make_sample("old", sampled_at=_NOW - timedelta(hours=1)))
    store.record_sample(make_sample("new", sampled_at=_NOW))

    fetched = store.list_samples_since(_NOW)

    assert [s.sample_id for s in fetched] == ["new"]


def test_list_samples_since_returns_oldest_first(store):
    store.record_sample(make_sample("second", sampled_at=_NOW + timedelta(minutes=2)))
    store.record_sample(make_sample("first", sampled_at=_NOW))
    store.record_sample(make_sample("third", sampled_at=_NOW + timedelta(minutes=5)))

    fetched = store.list_samples_since(_NOW)

    assert [s.sample_id for s in fetched] == ["first", "second", "third"]


def test_list_samples_since_empty_store_returns_empty_list(store):
    assert store.list_samples_since(_NOW) == []


# --- list_sessions_since() grouping -------------------------------------------------


def test_contiguous_same_process_samples_merge_into_one_session(tmp_path):
    config = AnalyticsConfig(session_gap_seconds=180.0)
    merged_store = UsageStore(SqliteClient(str(tmp_path / "merge.db")), config)
    merged_store.start()
    for offset in (0, 60, 120):
        merged_store.record_sample(
            make_sample(f"s{offset}", sampled_at=_NOW + timedelta(seconds=offset))
        )

    sessions = merged_store.list_sessions_since(_NOW)
    merged_store.stop()

    assert len(sessions) == 1
    assert sessions[0].process_name == "devenv.exe"
    assert sessions[0].sample_count == 3
    assert sessions[0].started_at == _NOW
    assert sessions[0].ended_at == _NOW + timedelta(seconds=120)


def test_a_gap_wider_than_session_gap_seconds_splits_into_two_sessions(tmp_path):
    config = AnalyticsConfig(session_gap_seconds=60.0)
    gapped_store = UsageStore(SqliteClient(str(tmp_path / "gap.db")), config)
    gapped_store.start()
    gapped_store.record_sample(make_sample("first", sampled_at=_NOW))
    gapped_store.record_sample(
        make_sample("second", sampled_at=_NOW + timedelta(seconds=61))
    )

    sessions = gapped_store.list_sessions_since(_NOW)
    gapped_store.stop()

    assert len(sessions) == 2
    assert sessions[0].sample_count == 1
    assert sessions[1].sample_count == 1


def test_a_different_process_starts_a_new_session_even_with_no_gap(store):
    store.record_sample(make_sample("a", process_name="devenv.exe", sampled_at=_NOW))
    store.record_sample(
        make_sample("b", process_name="chrome.exe", sampled_at=_NOW + timedelta(seconds=1))
    )

    sessions = store.list_sessions_since(_NOW)

    assert [s.process_name for s in sessions] == ["devenv.exe", "chrome.exe"]
    assert all(s.sample_count == 1 for s in sessions)


def test_a_lone_sample_becomes_its_own_one_sample_session(store):
    store.record_sample(make_sample())

    sessions = store.list_sessions_since(_NOW - timedelta(minutes=1))

    assert len(sessions) == 1
    assert sessions[0].sample_count == 1
    assert sessions[0].started_at == sessions[0].ended_at == _NOW


def test_list_sessions_since_resolves_category_from_config_map(tmp_path):
    config = AnalyticsConfig(category_map={"devenv.exe": "coding"})
    mapped_store = UsageStore(SqliteClient(str(tmp_path / "mapped.db")), config)
    mapped_store.start()
    mapped_store.record_sample(make_sample(process_name="devenv.exe"))
    mapped_store.record_sample(make_sample("unmapped", process_name="unknown.exe"))

    sessions = {s.process_name: s.category for s in mapped_store.list_sessions_since(_NOW)}
    mapped_store.stop()

    assert sessions["devenv.exe"] == "coding"
    assert sessions["unknown.exe"] is None


def test_list_sessions_since_empty_store_returns_empty_list(store):
    assert store.list_sessions_since(_NOW) == []


# --- real persistence across close()/reopen -----------------------------------------


def test_persistence_survives_close_and_reopen(tmp_path):
    db_path = str(tmp_path / "persist.db")
    sample = make_sample()

    client1 = SqliteClient(db_path)
    store1 = UsageStore(client1, AnalyticsConfig())
    store1.start()
    store1.record_sample(sample)
    store1.stop()

    client2 = SqliteClient(db_path)
    store2 = UsageStore(client2, AnalyticsConfig())
    store2.start()
    fetched = store2.list_samples_since(_NOW - timedelta(minutes=1))
    store2.stop()

    assert len(fetched) == 1
    assert fetched[0].sample_id == sample.sample_id


# --- health_check() -------------------------------------------------------------------


def test_health_check_false_before_start(tmp_path):
    client = SqliteClient(str(tmp_path / "hc.db"))
    store = UsageStore(client, AnalyticsConfig())
    assert store.health_check() is False


def test_health_check_true_after_start(store):
    assert store.health_check() is True


# --- purge_older_than() (Sprint 6.21 — Privacy Verification) ----------------------------------


def test_purge_older_than_removes_old_samples_and_keeps_recent_ones(store):
    now = datetime.now(UTC)
    store.record_sample(make_sample("old", sampled_at=now - timedelta(days=10)))
    store.record_sample(make_sample("new", sampled_at=now - timedelta(hours=1)))

    removed = store.purge_older_than(days=5)

    assert removed == 1
    remaining = store.list_samples_since(now - timedelta(days=365))
    assert [s.sample_id for s in remaining] == ["new"]


def test_purge_older_than_defaults_to_the_configured_retention_days(tmp_path):
    config = AnalyticsConfig(sample_retention_days=1)
    usage_store = UsageStore(SqliteClient(str(tmp_path / "purge.db")), config)
    usage_store.start()
    try:
        usage_store.record_sample(make_sample(sampled_at=datetime(2020, 1, 1, tzinfo=UTC)))

        removed = usage_store.purge_older_than()  # no explicit days

        assert removed == 1
    finally:
        usage_store.stop()


class _RaisingSqliteClient(SqliteClient):
    """Matches the project's established "_Raising*-style local test
    double" pattern (tests/unit/scheduler/test_calendar_store.py et al.)
    — a real SqliteClient whose query() can be switched to fail on
    demand, after start() has already succeeded."""

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.raise_on_query = False

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self.raise_on_query:
            raise RuntimeError("sqlite query exploded")
        return super().query(sql, params)


def test_purge_older_than_degrades_to_zero_on_a_sqlite_failure(tmp_path):
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    usage_store = UsageStore(client, AnalyticsConfig())
    usage_store.start()
    try:
        usage_store.record_sample(make_sample())
        client.raise_on_query = True

        assert usage_store.purge_older_than(days=1) == 0
    finally:
        client.raise_on_query = False
        usage_store.stop()
