"""Context Engine data model — the unified, point-in-time working-context
snapshot every later Level 6 Part A sprint (Reasoning, Proactive
Assistant, Decision Engine v2, Adaptive Prioritization) composes over.
See docs/sprint_book/sprint_6/sprint_6_3.md.

WorkingContext is a frozen dataclass — a snapshot valid at built_at,
never mutated in place once built. A caller needing a fresh view calls
ContextEngine.build() again, the same "recompute fresh, never cache"
discipline voice/context_manager.py's own ContextManager.current_context()
already established for conversation-level context.

conversation/resource_status are typed X | None (never a fabricated
"empty" object when their source collaborator is absent or fails) —
recent_memories/recent_applications/upcoming_scheduled_items/
known_projects are typed as plain lists defaulting to [] instead, since
an empty collection is an honest, unambiguous "nothing found" for a
collection field in a way no single-object field can represent without
inventing fake data, which the Human First Rule rules out. This sprint
file's own Expected Classes text describes every degraded field as
"empty ([], not None)" without drawing this distinction explicitly — a
small, necessary clarification for the two singular fields, not a
change to the four collection fields' own behavior.

known_projects stays an untyped placeholder (list[object]) until Sprint
6.6 (Knowledge Graph) gives it a real Entity type and a real producer —
declared now, empty, rather than added later as a breaking dataclass
change, the same "declare the field early, populate it once its owning
sprint exists" precedent device_control/action_engine.py's own
ActionStatus.RECOVERED member already established at Sprint 4.1
(populated for real only at Sprint 4.8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from analytics.usage_model import UsageSession
from core.resource_monitor import ResourceSnapshot
from memory.models import MemoryRecord
from scheduler.scheduler_model import ScheduledItem
from voice.context_manager import ConversationContext


@dataclass(frozen=True)
class WorkingContext:
    built_at: datetime
    conversation: ConversationContext | None
    recent_memories: list[MemoryRecord]
    recent_applications: list[UsageSession]
    upcoming_scheduled_items: list[ScheduledItem]
    resource_status: ResourceSnapshot | None
    known_projects: list[object] = field(default_factory=list)
