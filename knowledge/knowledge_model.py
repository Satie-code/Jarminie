"""Knowledge Graph data model — Entity/Relationship, the structural map
of what things exist in the user's life (projects, people, goals, files,
topics) and how they relate. See docs/sprint_book/sprint_6/sprint_6_6.md.

**A real, deliberate boundary against memory/models.py's MemoryType**:
MemoryStore's five MemoryTypes (Sprint 3.1) are locked — ConfidenceScorer's/
PersonaScopedMemory's own scoring/scoping rules are written specifically
around those five, the same reasoning that already kept LearnedPattern
(Sprint 5.21) out of MemoryType and gave it its own PatternStore instead.
Entity/Relationship follow that identical precedent: a structural map
("what exists, how does it relate"), never a sixth MemoryType answering
a fundamentally different question ("what was said/observed, and how
confident/permanent is it").

Field order below places every required field before any defaulted one,
a plain Python dataclass necessity — this sprint file's own prose lists
Entity's fields in a different order (description before created_at)
that is not valid as literal declaration order, the identical "prose
order vs. valid declaration order" gap Sprint 6.1's Task/Goal already
disclosed. The set of fields, types, and defaults is unchanged, only the
declaration order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EntityType(Enum):
    """Exactly the five nouns the brief names ("Projects. People. Goals.
    ... Files. Topics."), in that order — no speculative sixth member
    added without textual basis."""

    PROJECT = "project"
    PERSON = "person"
    GOAL = "goal"
    FILE = "file"
    TOPIC = "topic"


class RelationshipType(Enum):
    """Five general-purpose relationship shapes covering the brief's own
    "Relationships... Dependencies" language without over-fitting to one
    imagined use case — a narrower or richer taxonomy has no textual
    basis yet."""

    DEPENDS_ON = "depends_on"
    RELATES_TO = "relates_to"
    OWNS = "owns"
    PART_OF = "part_of"
    MENTIONED_IN = "mentioned_in"


@dataclass
class Entity:
    """last_referenced_at is updated whenever a caller decides a real
    reference happened (e.g. a workflow step actually opening a
    project) — never inferred automatically from a mere lookup; see
    knowledge/knowledge_graph_store.py's own docstring for why."""

    entity_id: str
    entity_type: EntityType
    name: str
    created_at: datetime
    last_referenced_at: datetime
    description: str = ""


@dataclass
class Relationship:
    from_entity_id: str
    to_entity_id: str
    relationship_type: RelationshipType
    created_at: datetime
