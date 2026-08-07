"""Unit tests for context.context_engine."""

from datetime import UTC, datetime

from analytics.usage_model import UsageSession
from context.context_engine import ContextEngine
from core.resource_monitor import ResourceSnapshot
from memory.models import MemoryRecord, MemoryType
from scheduler.scheduler_model import ItemType, ScheduledItem
from voice.context_manager import ConversationContext


class FakeContextManager:
    def __init__(self, result: ConversationContext | None = None, error: Exception | None = None):
        self._result = result
        self._error = error

    def current_context(self, session_id: str, active_persona_name: str) -> ConversationContext:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class FakeMemoryStore:
    def __init__(self, result: list[MemoryRecord] | None = None, error: Exception | None = None):
        self._result = result if result is not None else []
        self._error = error
        self.calls: list[tuple[MemoryType, int]] = []

    def recent(self, memory_type: MemoryType, limit: int) -> list[MemoryRecord]:
        self.calls.append((memory_type, limit))
        if self._error is not None:
            raise self._error
        return self._result


class FakeUsageStore:
    def __init__(self, result: list[UsageSession] | None = None, error: Exception | None = None):
        self._result = result if result is not None else []
        self._error = error

    def list_sessions_since(self, since: datetime) -> list[UsageSession]:
        if self._error is not None:
            raise self._error
        return self._result


class FakeCalendarStore:
    def __init__(self, result: list[ScheduledItem] | None = None, error: Exception | None = None):
        self._result = result if result is not None else []
        self._error = error

    def list_due_within(self, window_end: datetime, **kwargs) -> list[ScheduledItem]:
        if self._error is not None:
            raise self._error
        return self._result


class FakeResourceMonitor:
    def __init__(self, result: ResourceSnapshot | None = None, error: Exception | None = None):
        self._result = result
        self._error = error

    def sample(self) -> ResourceSnapshot:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def make_conversation() -> ConversationContext:
    now = datetime.now(UTC)
    return ConversationContext(
        session_id="session-1",
        active_persona_name="jarvis",
        recent_turns=[],
        session_started_at=now,
        last_activity_at=now,
    )


def make_resource_snapshot() -> ResourceSnapshot:
    return ResourceSnapshot(
        cpu_percent=10.0, ram_percent=20.0, disk_percent=30.0, battery_percent=90.0,
        timestamp=datetime.now(UTC),
    )


def make_scheduled_item() -> ScheduledItem:
    now = datetime.now(UTC)
    return ScheduledItem(
        item_id="item-1", item_type=ItemType.EVENT, title="Standup",
        scheduled_at=now, created_at=now,
    )


# --- full success path -------------------------------------------------------------------


def test_build_composes_every_collaborators_real_data_when_all_present():
    conversation = make_conversation()
    memory_record = MemoryRecord(memory_type=MemoryType.SHARED, content="a shared memory")
    session = UsageSession(
        process_name="code.exe", category="coding",
        started_at=datetime.now(UTC), ended_at=datetime.now(UTC), sample_count=3,
    )
    scheduled_item = make_scheduled_item()
    resource_snapshot = make_resource_snapshot()

    engine = ContextEngine(
        context_manager=FakeContextManager(result=conversation),
        memory_store=FakeMemoryStore(result=[memory_record]),
        usage_store=FakeUsageStore(result=[session]),
        calendar_store=FakeCalendarStore(result=[scheduled_item]),
        resource_monitor=FakeResourceMonitor(result=resource_snapshot),
    )

    working_context = engine.build("session-1", "jarvis")

    assert working_context.conversation is conversation
    assert working_context.recent_memories == [memory_record]
    assert working_context.recent_applications == [session]
    assert working_context.upcoming_scheduled_items == [scheduled_item]
    assert working_context.resource_status is resource_snapshot
    assert working_context.known_projects == []
    assert working_context.built_at is not None


# --- absent collaborators ----------------------------------------------------------------


def test_build_with_every_collaborator_absent_returns_a_fully_degraded_but_valid_context():
    engine = ContextEngine()

    working_context = engine.build("session-1", "jarvis")

    assert working_context.conversation is None
    assert working_context.recent_memories == []
    assert working_context.recent_applications == []
    assert working_context.upcoming_scheduled_items == []
    assert working_context.resource_status is None
    assert working_context.known_projects == []


def test_build_with_only_context_manager_absent_still_populates_the_rest():
    memory_record = MemoryRecord(memory_type=MemoryType.SHARED, content="x")
    engine = ContextEngine(
        memory_store=FakeMemoryStore(result=[memory_record]),
        usage_store=FakeUsageStore(),
        calendar_store=FakeCalendarStore(),
        resource_monitor=FakeResourceMonitor(result=make_resource_snapshot()),
    )

    working_context = engine.build("session-1", "jarvis")

    assert working_context.conversation is None
    assert len(working_context.recent_memories) == 1
    assert working_context.resource_status is not None


# --- raising collaborators -----------------------------------------------------------------


def test_build_degrades_a_single_raising_collaborator_without_aborting_the_whole_build():
    conversation = make_conversation()
    resource_snapshot = make_resource_snapshot()
    engine = ContextEngine(
        context_manager=FakeContextManager(result=conversation),
        memory_store=FakeMemoryStore(error=RuntimeError("memory store exploded")),
        usage_store=FakeUsageStore(error=RuntimeError("usage store exploded")),
        calendar_store=FakeCalendarStore(error=RuntimeError("calendar store exploded")),
        resource_monitor=FakeResourceMonitor(result=resource_snapshot),
    )

    working_context = engine.build("session-1", "jarvis")  # must not raise

    assert working_context.conversation is conversation
    assert working_context.recent_memories == []
    assert working_context.recent_applications == []
    assert working_context.upcoming_scheduled_items == []
    assert working_context.resource_status is resource_snapshot


def test_build_degrades_a_raising_conversation_read_to_none():
    engine = ContextEngine(context_manager=FakeContextManager(error=RuntimeError("boom")))

    working_context = engine.build("session-1", "jarvis")

    assert working_context.conversation is None


def test_build_degrades_a_raising_resource_read_to_none():
    engine = ContextEngine(resource_monitor=FakeResourceMonitor(error=RuntimeError("boom")))

    working_context = engine.build("session-1", "jarvis")

    assert working_context.resource_status is None


# --- recent_memories scoping (privacy) ------------------------------------------------------


def test_build_only_ever_requests_shared_memories_regardless_of_active_persona():
    fake_memory_store = FakeMemoryStore(result=[])
    engine = ContextEngine(memory_store=fake_memory_store)

    engine.build("session-1", "minie")

    assert len(fake_memory_store.calls) == 1
    requested_type, _ = fake_memory_store.calls[0]
    assert requested_type is MemoryType.SHARED


def test_build_passes_memory_lookback_count_from_config():
    from config.schema import ContextEngineConfig

    fake_memory_store = FakeMemoryStore(result=[])
    engine = ContextEngine(
        memory_store=fake_memory_store,
        context_engine_config=ContextEngineConfig(memory_lookback_count=42),
    )

    engine.build("session-1", "jarvis")

    assert fake_memory_store.calls[0] == (MemoryType.SHARED, 42)


# --- built_at ---------------------------------------------------------------------------


def test_build_at_reflects_real_call_time():
    before = datetime.now(UTC)
    engine = ContextEngine()

    working_context = engine.build("session-1", "jarvis")

    after = datetime.now(UTC)
    assert before <= working_context.built_at <= after
