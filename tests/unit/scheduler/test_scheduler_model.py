"""Unit tests for scheduler.scheduler_model."""

from datetime import UTC, datetime

from scheduler.scheduler_model import ItemType, ScheduledItem


def test_scheduled_item_defaults():
    item = ScheduledItem(
        item_id="item-1",
        item_type=ItemType.EVENT,
        title="Team standup",
        scheduled_at=datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 31, 0, 0, 0, tzinfo=UTC),
    )
    assert item.description is None
    assert item.is_completed is False


def test_scheduled_item_deadline_type():
    item = ScheduledItem(
        item_id="item-2",
        item_type=ItemType.DEADLINE,
        title="Submit report",
        scheduled_at=datetime(2026, 8, 5, 17, 0, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 31, 0, 0, 0, tzinfo=UTC),
        description="Quarterly report to finance",
        is_completed=True,
    )
    assert item.item_type is ItemType.DEADLINE
    assert item.description == "Quarterly report to finance"
    assert item.is_completed is True
