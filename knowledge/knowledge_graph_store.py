"""Knowledge Graph Store — persistent entity/relationship storage plus
traversal queries. See docs/sprint_book/sprint_6/sprint_6_6.md.

Owns its own two-table DDL (entities, relationships) against the shared
SqliteClient, following TaskGraphStore's/PatternStore's own "caller owns
its own DDL" precedent — no second database-access layer invented.

save_entity()'s upsert mirrors learning/pattern_store.py's own
INSERT ... ON CONFLICT DO UPDATE idiom (Sprint 5.21) exactly: on a
genuinely new entity_id, every column is inserted as-is; on a conflict,
only description/last_referenced_at are refreshed (excluded.description,
excluded.last_referenced_at) — entity_type/name/created_at all survive
untouched, per this sprint's own literal Acceptance Criteria text
("updates description/last_referenced_at while preserving the original
created_at"), which names exactly those two fields as the mutable set.
No basis in that text to also make entity_type/name updatable via this
same call — a caller needing to correct either would need a real,
different, not-yet-built operation this sprint doesn't name.

last_referenced_at is deliberately a plain, directly-settable field on
Entity, never inferred by this store from query activity — see
knowledge/knowledge_model.py's own Entity docstring and this sprint's
own Architecture Notes for why treating a mere find_entities()/
get_entity() read as a "reference" would defeat Sprint 6.8's whole
project-inactivity-detection purpose for this field.

**A real design decision this sprint's own text left open, resolved
directly and disclosed here**: "an entity's own relationship count"
(add_relationship()'s own bound) counts every relationship row touching
that entity as EITHER from_entity_id OR to_entity_id — its total graph
degree, not just outgoing edges. Unlike planning/task_graph.py's
max_task_dependencies (a directed, incoming-only bound this sprint's own
Engineering Rationale explicitly cites as its precedent shape), a general
Relationship has no single privileged direction the way a Task's own
prerequisite count does — RELATES_TO/MENTIONED_IN read naturally as
symmetric, and even the directional ones (DEPENDS_ON, OWNS) should still
count against both endpoints' own totals, since an entity accumulating
many incoming DEPENDS_ON edges is exactly as real a "too connected"
signal as accumulating many outgoing ones.

related_entities() treats the relationship graph as undirected for
traversal purposes for the identical reason: an entity's neighbors are
every entity connected via a relationship row in either direction, not
just its own outgoing edges. This sprint's own Architecture Notes
already establishes traversal must be genuinely cycle-safe ("a
Relationship graph is not guaranteed acyclic... PART_OF/RELATES_TO
relationships between real-world entities have no reason to stay a
DAG"), which only matters for a traversal that actually walks the graph
as a graph — a strictly-outgoing-only walk over TaskGraph's own directed
dependency shape would have no such need. No textual basis prefers
outgoing-only traversal, and "what's related to X" (this sprint's own
Purpose) reads most naturally as "what's connected to X," regardless of
which direction a given relationship happened to be stored in.

Deliberately NOT given Fail Gracefully hardening at this store's own
Sprint 6.6 — matching TaskGraphStore's/CalendarStore's/UsageStore's
identical precedent (no real caller existed yet to meaningfully degrade
for). Sprint 6.14 (Error Handling & Recovery Hardening, scenario b) adds
it once Sprint 6.9/6.13 gave this store a real caller
(SessionResumption.build_workflow() -> find_entities()/
related_entities()): find_entities(), _neighbor_ids(), and get_entity()
now degrade to []/set()/None respectively on a SQLite failure, matching
CalendarStore.list_due_within()'s exact idiom — save_entity()/
add_relationship() remain deliberately unhardened, still no real write
caller.
"""

from __future__ import annotations

from datetime import datetime

from config.schema import KnowledgeGraphConfig
from core.logging_setup import get_logger
from database.sqlite_client import SqliteClient
from knowledge.errors import TooManyRelationshipsError
from knowledge.knowledge_model import Entity, EntityType, Relationship, RelationshipType

logger = get_logger(__name__)

_CREATE_ENTITIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_referenced_at TEXT NOT NULL
)
"""

_CREATE_RELATIONSHIPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_entity_id TEXT NOT NULL,
    to_entity_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

_UPSERT_ENTITY_SQL = """
INSERT INTO entities (entity_id, entity_type, name, description, created_at, last_referenced_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(entity_id) DO UPDATE SET
    description = excluded.description,
    last_referenced_at = excluded.last_referenced_at
"""

_SELECT_ENTITY_COLUMNS = "entity_id, entity_type, name, description, created_at, last_referenced_at"


class KnowledgeGraphStore:
    """Constructor DI: (sqlite_client, knowledge_graph_config)."""

    def __init__(
        self, sqlite_client: SqliteClient, knowledge_graph_config: KnowledgeGraphConfig
    ) -> None:
        self._sqlite_client = sqlite_client
        self._config = knowledge_graph_config
        self._started = False

    def start(self) -> None:
        self._sqlite_client.connect()
        self._sqlite_client.execute(_CREATE_ENTITIES_TABLE_SQL)
        self._sqlite_client.execute(_CREATE_RELATIONSHIPS_TABLE_SQL)
        self._started = True
        logger.info("Knowledge graph store started.")

    def stop(self) -> None:
        self._sqlite_client.close()
        self._started = False
        logger.info("Knowledge graph store stopped.")

    def health_check(self) -> bool:
        if not self._started:
            return False
        try:
            self._sqlite_client.query("SELECT 1")
            return True
        except Exception:
            logger.exception("Knowledge graph store health check query failed.")
            return False

    def save_entity(self, entity: Entity) -> None:
        self._sqlite_client.execute(
            _UPSERT_ENTITY_SQL,
            (
                entity.entity_id,
                entity.entity_type.value,
                entity.name,
                entity.description,
                entity.created_at.isoformat(),
                entity.last_referenced_at.isoformat(),
            ),
        )

    def get_entity(self, entity_id: str) -> Entity | None:
        """Sprint 6.14 hardening (scenario b): related_entities()'s own
        real, live caller chain (SessionResumption.build_workflow(),
        6.9/6.13) calls this per discovered id — a SQLite failure
        degrades to None, indistinguishable from "not found," which that
        caller's own list comprehension already filters out."""
        try:
            rows = self._sqlite_client.query(
                f"SELECT {_SELECT_ENTITY_COLUMNS} FROM entities WHERE entity_id = ?", (entity_id,)
            )
        except Exception:
            logger.exception("Failed to query entity %r; treating as not found.", entity_id)
            return None
        if not rows:
            return None
        return self._build_entity(rows[0])

    def find_entities(
        self, entity_type: EntityType | None = None, name_contains: str | None = None
    ) -> list[Entity]:
        """Sprint 6.14 hardening (scenario b): SessionResumption.
        build_workflow() (6.9) is a real, live caller now (via
        CommunicationPipeline._resume_previous_session(), 6.13) — a
        SQLite failure degrades to [], matching TaskGraphStore.
        list_goals()'s identical treatment, and composes correctly with
        that caller's own existing "if not projects: return None" ->
        "I don't have a previous session to resume." reply, no
        pipeline.py change needed at that call site."""
        conditions: list[str] = []
        params: list[object] = []
        if entity_type is not None:
            conditions.append("entity_type = ?")
            params.append(entity_type.value)
        if name_contains is not None:
            conditions.append("name LIKE ?")
            params.append(f"%{name_contains}%")

        query = f"SELECT {_SELECT_ENTITY_COLUMNS} FROM entities"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        try:
            rows = self._sqlite_client.query(query, tuple(params))
        except Exception:
            logger.exception("Failed to query entities; treating as none found.")
            return []
        return [self._build_entity(row) for row in rows]

    def add_relationship(self, relationship: Relationship) -> None:
        """Raises TooManyRelationshipsError, without inserting anything,
        if either endpoint's own relationship count would exceed
        knowledge_graph_config.max_relationships_per_entity — see this
        module's own docstring for why both endpoints are checked."""
        for endpoint_id in (relationship.from_entity_id, relationship.to_entity_id):
            existing_count = self._relationship_count(endpoint_id)
            if existing_count + 1 > self._config.max_relationships_per_entity:
                raise TooManyRelationshipsError(
                    f"Entity {endpoint_id!r} already has {existing_count} relationship(s); "
                    "adding this one would exceed the configured max of "
                    f"{self._config.max_relationships_per_entity}."
                )
        self._sqlite_client.execute(
            "INSERT INTO relationships "
            "(from_entity_id, to_entity_id, relationship_type, created_at) VALUES (?, ?, ?, ?)",
            (
                relationship.from_entity_id,
                relationship.to_entity_id,
                relationship.relationship_type.value,
                relationship.created_at.isoformat(),
            ),
        )

    def related_entities(
        self,
        entity_id: str,
        relationship_type: RelationshipType | None = None,
        depth: int = 1,
    ) -> list[Entity]:
        """Breadth-first, cycle-safe traversal — see this module's own
        docstring for why it treats the graph as undirected. Clamped to
        knowledge_graph_config.max_traversal_depth regardless of what
        depth the caller requests; never revisits an entity already
        seen, so a cycle in the underlying relationship graph cannot
        cause an infinite or duplicated result."""
        effective_depth = max(0, min(depth, self._config.max_traversal_depth))
        visited = {entity_id}
        frontier = {entity_id}
        discovered_ids: list[str] = []

        for _ in range(effective_depth):
            next_frontier: set[str] = set()
            for current_id in frontier:
                for neighbor_id in self._neighbor_ids(current_id, relationship_type):
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        next_frontier.add(neighbor_id)
                        discovered_ids.append(neighbor_id)
            if not next_frontier:
                break
            frontier = next_frontier

        entities = [self.get_entity(discovered_id) for discovered_id in discovered_ids]
        return [entity for entity in entities if entity is not None]

    def _neighbor_ids(
        self, entity_id: str, relationship_type: RelationshipType | None
    ) -> set[str]:
        """Sprint 6.14 hardening (scenario b): a SQLite failure here
        degrades to an empty neighbor set, which related_entities()'s
        own BFS loop already treats identically to "this node has no
        more neighbors" — the traversal simply stops expanding from this
        node rather than raising, a real but honestly partial result
        (logged) instead of ending the whole session."""
        try:
            if relationship_type is None:
                rows = self._sqlite_client.query(
                    "SELECT to_entity_id FROM relationships WHERE from_entity_id = ? "
                    "UNION "
                    "SELECT from_entity_id FROM relationships WHERE to_entity_id = ?",
                    (entity_id, entity_id),
                )
            else:
                rows = self._sqlite_client.query(
                    "SELECT to_entity_id FROM relationships "
                    "WHERE from_entity_id = ? AND relationship_type = ? "
                    "UNION "
                    "SELECT from_entity_id FROM relationships "
                    "WHERE to_entity_id = ? AND relationship_type = ?",
                    (entity_id, relationship_type.value, entity_id, relationship_type.value),
                )
        except Exception:
            logger.exception(
                "Failed to query relationships for entity %r; treating as no "
                "further neighbors.",
                entity_id,
            )
            return set()
        return {row[0] for row in rows}

    def _relationship_count(self, entity_id: str) -> int:
        rows = self._sqlite_client.query(
            "SELECT COUNT(*) FROM relationships WHERE from_entity_id = ? OR to_entity_id = ?",
            (entity_id, entity_id),
        )
        return rows[0][0]

    def _build_entity(self, row: tuple) -> Entity:
        entity_id, entity_type, name, description, created_at, last_referenced_at = row
        return Entity(
            entity_id=entity_id,
            entity_type=EntityType(entity_type),
            name=name,
            created_at=datetime.fromisoformat(created_at),
            last_referenced_at=datetime.fromisoformat(last_referenced_at),
            description=description,
        )
