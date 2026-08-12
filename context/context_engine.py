"""Context Engine — the cross-subsystem aggregator combining conversation,
memory, current applications, calendar, and system status into one
WorkingContext snapshot. See docs/sprint_book/sprint_6/sprint_6_3.md.

A real, deliberate naming decision, made explicit because two existing
classes already occupy adjacent name-space: voice/context_manager.py's
ContextManager/ConversationContext (Sprint 2.8) already assembles
CONVERSATION-level context (recent turns, active persona, session
timing); decision/context_analyzer.py's ContextAnalyzer (Sprint 3.8)
already classifies PER-TURN sentiment/topic/urgency. Neither is being
replaced or duplicated. ContextEngine sits ABOVE both — it treats
ContextManager.current_context()'s own output as exactly one of its
several inputs, never recomputing it, and never touches ContextAnalyzer
at all.

Deliberately stateless and read-only, not a ManagedModule — it owns no
storage and no lifecycle, the same "compose already-persisted data on
demand" shape analytics/dashboard_data.py's AnalyticsDashboardService
already established. Every collaborator it reads from is independently
already lifecycle-managed by CoreManager.

Every call to build() is a fresh read — no caching, so a WorkingContext
can never silently go stale; see this sprint's own Architecture Notes
for why that's a deliberate choice, not an oversight.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from analytics.usage_store import UsageStore
from config.schema import ContextEngineConfig
from context.context_model import WorkingContext
from core.logging_setup import get_logger
from core.resource_monitor import ResourceMonitor
from memory.memory_store import MemoryStoreProtocol
from memory.models import MemoryType
from scheduler.calendar_store import CalendarStore
from voice.context_manager import ContextManager

logger = get_logger(__name__)


class ContextEngine:
    """Constructor DI: every collaborator except context_engine_config is
    optional (X | None = None) — a WorkingContext built with some
    collaborators absent simply leaves the corresponding field empty
    (never a raised exception), matching the Fail Gracefully Rule
    applied to composition rather than a live call failure.

    Sprint 6.13 correction: memory_store is typed against
    MemoryStoreProtocol, not the concrete MemoryStore this sprint file's
    own text originally named — the Runtime Refactor Sprint (completed
    2026-08-08, after this class's own Sprint 6.3) threads a
    LazyMemoryStore proxy through every real memory_store call site
    project-wide; learning/preference_learner.py's own identical
    correction already established this exact fix for the identical
    reason."""

    def __init__(
        self,
        context_manager: ContextManager | None = None,
        memory_store: MemoryStoreProtocol | None = None,
        usage_store: UsageStore | None = None,
        calendar_store: CalendarStore | None = None,
        resource_monitor: ResourceMonitor | None = None,
        context_engine_config: ContextEngineConfig | None = None,
    ) -> None:
        self._context_manager = context_manager
        self._memory_store = memory_store
        self._usage_store = usage_store
        self._calendar_store = calendar_store
        self._resource_monitor = resource_monitor
        self._config = context_engine_config or ContextEngineConfig()

    def build(self, session_id: str, active_persona_name: str) -> WorkingContext:
        """Never raises: any single collaborator being absent or raising
        degrades only that one field, logged, never the whole call."""
        return WorkingContext(
            built_at=datetime.now(UTC),
            conversation=self._read_conversation(session_id, active_persona_name),
            recent_memories=self._read_recent_memories(),
            recent_applications=self._read_recent_applications(),
            upcoming_scheduled_items=self._read_upcoming_scheduled_items(),
            resource_status=self._read_resource_status(),
        )

    def _read_conversation(self, session_id: str, active_persona_name: str):
        if self._context_manager is None:
            return None
        try:
            return self._context_manager.current_context(session_id, active_persona_name)
        except Exception:
            logger.exception("ContextEngine: failed to read conversation context.")
            return None

    def _read_recent_memories(self):
        if self._memory_store is None:
            return []
        try:
            return self._memory_store.recent(MemoryType.SHARED, self._config.memory_lookback_count)
        except Exception:
            logger.exception("ContextEngine: failed to read recent memories.")
            return []

    def _read_recent_applications(self):
        if self._usage_store is None:
            return []
        try:
            since = datetime.now(UTC) - timedelta(hours=self._config.usage_lookback_hours)
            return self._usage_store.list_sessions_since(since)
        except Exception:
            logger.exception("ContextEngine: failed to read recent application usage.")
            return []

    def _read_upcoming_scheduled_items(self):
        if self._calendar_store is None:
            return []
        try:
            window_end = datetime.now(UTC) + timedelta(
                hours=self._config.calendar_lookahead_hours
            )
            return self._calendar_store.list_due_within(window_end)
        except Exception:
            logger.exception("ContextEngine: failed to read upcoming scheduled items.")
            return []

    def _read_resource_status(self):
        if self._resource_monitor is None:
            return None
        try:
            return self._resource_monitor.sample()
        except Exception:
            logger.exception("ContextEngine: failed to read resource status.")
            return None
