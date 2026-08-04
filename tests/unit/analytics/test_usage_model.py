"""Unit tests for analytics.usage_model."""

from datetime import UTC, datetime

from analytics.usage_model import AppFocusSample, UsageSession


def test_app_focus_sample_generates_a_sample_id_when_not_supplied():
    sample = AppFocusSample(
        process_name="devenv.exe",
        window_title="JARMINEI - Visual Studio",
        sampled_at=datetime(2026, 8, 4, 9, 0, 0, tzinfo=UTC),
    )
    assert sample.sample_id
    assert isinstance(sample.sample_id, str)


def test_app_focus_sample_accepts_an_explicit_sample_id():
    sample = AppFocusSample(
        process_name="devenv.exe",
        window_title="JARMINEI - Visual Studio",
        sampled_at=datetime(2026, 8, 4, 9, 0, 0, tzinfo=UTC),
        sample_id="explicit-id",
    )
    assert sample.sample_id == "explicit-id"


def test_two_default_sample_ids_are_distinct():
    now = datetime(2026, 8, 4, 9, 0, 0, tzinfo=UTC)
    first = AppFocusSample(process_name="a.exe", window_title="A", sampled_at=now)
    second = AppFocusSample(process_name="b.exe", window_title="B", sampled_at=now)
    assert first.sample_id != second.sample_id


def test_usage_session_construction():
    session = UsageSession(
        process_name="devenv.exe",
        category="coding",
        started_at=datetime(2026, 8, 4, 9, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 8, 4, 9, 30, 0, tzinfo=UTC),
        sample_count=5,
    )
    assert session.process_name == "devenv.exe"
    assert session.category == "coding"
    assert session.sample_count == 5


def test_usage_session_allows_no_category():
    session = UsageSession(
        process_name="unmapped.exe",
        category=None,
        started_at=datetime(2026, 8, 4, 9, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 8, 4, 9, 0, 0, tzinfo=UTC),
        sample_count=1,
    )
    assert session.category is None
