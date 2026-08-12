"""Unit tests for knowledge.knowledge_graph_store."""

from datetime import UTC, datetime

import pytest

from config.schema import KnowledgeGraphConfig
from database.sqlite_client import SqliteClient
from knowledge.errors import TooManyRelationshipsError
from knowledge.knowledge_graph_store import KnowledgeGraphStore
from knowledge.knowledge_model import Entity, EntityType, Relationship, RelationshipType

_NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
_LATER = datetime(2026, 8, 9, 13, 0, 0, tzinfo=UTC)


def make_entity(
    entity_id: str,
    entity_type: EntityType = EntityType.PROJECT,
    name: str = "JARMINEI",
    description: str = "",
    created_at: datetime = _NOW,
    last_referenced_at: datetime = _NOW,
) -> Entity:
    return Entity(
        entity_id=entity_id,
        entity_type=entity_type,
        name=name,
        created_at=created_at,
        last_referenced_at=last_referenced_at,
        description=description,
    )


def make_relationship(
    from_entity_id: str,
    to_entity_id: str,
    relationship_type: RelationshipType = RelationshipType.RELATES_TO,
) -> Relationship:
    return Relationship(
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        relationship_type=relationship_type,
        created_at=_NOW,
    )


@pytest.fixture
def store(tmp_path) -> KnowledgeGraphStore:
    client = SqliteClient(str(tmp_path / "knowledge.db"))
    knowledge_graph_store = KnowledgeGraphStore(client, KnowledgeGraphConfig())
    knowledge_graph_store.start()
    yield knowledge_graph_store
    knowledge_graph_store.stop()


# --- save_entity()/get_entity() -----------------------------------------------------------


def test_save_get_round_trip_preserves_every_field(store):
    entity = make_entity("e1", description="The main project")

    store.save_entity(entity)
    fetched = store.get_entity("e1")

    assert fetched is not None
    assert fetched.entity_id == "e1"
    assert fetched.entity_type is EntityType.PROJECT
    assert fetched.name == "JARMINEI"
    assert fetched.description == "The main project"
    assert fetched.created_at == _NOW
    assert fetched.last_referenced_at == _NOW


def test_get_nonexistent_entity_returns_none(store):
    assert store.get_entity("does-not-exist") is None


def test_save_entity_update_refreshes_description_and_last_referenced_at(store):
    store.save_entity(make_entity("e1", description="original", last_referenced_at=_NOW))

    store.save_entity(make_entity("e1", description="updated", last_referenced_at=_LATER))
    fetched = store.get_entity("e1")

    assert fetched.description == "updated"
    assert fetched.last_referenced_at == _LATER


def test_save_entity_update_preserves_original_created_at(store):
    store.save_entity(make_entity("e1", created_at=_NOW))

    store.save_entity(make_entity("e1", created_at=_LATER))
    fetched = store.get_entity("e1")

    assert fetched.created_at == _NOW


def test_save_entity_update_does_not_change_entity_type_or_name(store):
    store.save_entity(make_entity("e1", entity_type=EntityType.PROJECT, name="Original Name"))

    store.save_entity(make_entity("e1", entity_type=EntityType.GOAL, name="Different Name"))
    fetched = store.get_entity("e1")

    assert fetched.entity_type is EntityType.PROJECT
    assert fetched.name == "Original Name"


# --- find_entities() -----------------------------------------------------------------------


def test_find_entities_with_no_filters_returns_everything(store):
    store.save_entity(make_entity("e1", entity_type=EntityType.PROJECT))
    store.save_entity(make_entity("e2", entity_type=EntityType.PERSON, name="Ada"))

    result = store.find_entities()

    assert {e.entity_id for e in result} == {"e1", "e2"}


def test_find_entities_filters_by_entity_type(store):
    store.save_entity(make_entity("e1", entity_type=EntityType.PROJECT))
    store.save_entity(make_entity("e2", entity_type=EntityType.PERSON, name="Ada"))

    result = store.find_entities(entity_type=EntityType.PERSON)

    assert {e.entity_id for e in result} == {"e2"}


def test_find_entities_filters_by_name_substring(store):
    store.save_entity(make_entity("e1", name="JARMINEI Project"))
    store.save_entity(make_entity("e2", name="Some Other Thing"))

    result = store.find_entities(name_contains="jarminei")

    assert {e.entity_id for e in result} == {"e1"}


def test_find_entities_combines_type_and_name_filters(store):
    store.save_entity(make_entity("e1", entity_type=EntityType.PROJECT, name="JARMINEI"))
    store.save_entity(make_entity("e2", entity_type=EntityType.GOAL, name="JARMINEI launch"))

    result = store.find_entities(entity_type=EntityType.PROJECT, name_contains="JARMINEI")

    assert {e.entity_id for e in result} == {"e1"}


# --- add_relationship() ---------------------------------------------------------------------


def test_add_relationship_succeeds_up_to_the_configured_max(tmp_path):
    client = SqliteClient(str(tmp_path / "knowledge.db"))
    store = KnowledgeGraphStore(client, KnowledgeGraphConfig(max_relationships_per_entity=2))
    store.start()
    store.save_entity(make_entity("hub"))
    for i in range(2):
        store.save_entity(make_entity(f"leaf{i}"))
        store.add_relationship(make_relationship("hub", f"leaf{i}"))  # must not raise
    store.stop()


def test_add_relationship_rejects_beyond_the_configured_max(tmp_path):
    client = SqliteClient(str(tmp_path / "knowledge.db"))
    store = KnowledgeGraphStore(client, KnowledgeGraphConfig(max_relationships_per_entity=2))
    store.start()
    store.save_entity(make_entity("hub"))
    for i in range(2):
        store.save_entity(make_entity(f"leaf{i}"))
        store.add_relationship(make_relationship("hub", f"leaf{i}"))
    store.save_entity(make_entity("leaf2"))

    with pytest.raises(TooManyRelationshipsError):
        store.add_relationship(make_relationship("hub", "leaf2"))
    store.stop()


def test_add_relationship_rejection_does_not_partially_apply(tmp_path):
    client = SqliteClient(str(tmp_path / "knowledge.db"))
    store = KnowledgeGraphStore(client, KnowledgeGraphConfig(max_relationships_per_entity=1))
    store.start()
    store.save_entity(make_entity("hub"))
    store.save_entity(make_entity("leaf0"))
    store.add_relationship(make_relationship("hub", "leaf0"))
    store.save_entity(make_entity("leaf1"))

    with pytest.raises(TooManyRelationshipsError):
        store.add_relationship(make_relationship("hub", "leaf1"))

    assert store.related_entities("hub") == [store.get_entity("leaf0")]
    store.stop()


def test_add_relationship_counts_an_entity_as_the_to_endpoint_too(tmp_path):
    client = SqliteClient(str(tmp_path / "knowledge.db"))
    store = KnowledgeGraphStore(client, KnowledgeGraphConfig(max_relationships_per_entity=1))
    store.start()
    store.save_entity(make_entity("a"))
    store.save_entity(make_entity("b"))
    store.save_entity(make_entity("c"))
    store.add_relationship(make_relationship("a", "b"))  # "b" is now at its own limit (1)

    with pytest.raises(TooManyRelationshipsError):
        store.add_relationship(make_relationship("c", "b"))
    store.stop()


# --- related_entities() ---------------------------------------------------------------------


def test_related_entities_at_depth_1_returns_direct_neighbors(store):
    store.save_entity(make_entity("a"))
    store.save_entity(make_entity("b"))
    store.save_entity(make_entity("c"))
    store.add_relationship(make_relationship("a", "b"))
    store.add_relationship(make_relationship("a", "c"))

    result = store.related_entities("a", depth=1)

    assert {e.entity_id for e in result} == {"b", "c"}


def test_related_entities_treats_the_graph_as_undirected(store):
    store.save_entity(make_entity("a"))
    store.save_entity(make_entity("b"))
    store.add_relationship(make_relationship("b", "a"))  # "a" is the TO endpoint

    result = store.related_entities("a", depth=1)

    assert {e.entity_id for e in result} == {"b"}


def test_related_entities_performs_real_multi_hop_traversal(store):
    store.save_entity(make_entity("a"))
    store.save_entity(make_entity("b"))
    store.save_entity(make_entity("c"))
    store.add_relationship(make_relationship("a", "b"))
    store.add_relationship(make_relationship("b", "c"))

    result = store.related_entities("a", depth=2)

    assert {e.entity_id for e in result} == {"b", "c"}


def test_related_entities_depth_1_does_not_include_second_hop(store):
    store.save_entity(make_entity("a"))
    store.save_entity(make_entity("b"))
    store.save_entity(make_entity("c"))
    store.add_relationship(make_relationship("a", "b"))
    store.add_relationship(make_relationship("b", "c"))

    result = store.related_entities("a", depth=1)

    assert {e.entity_id for e in result} == {"b"}


def test_related_entities_is_cycle_safe(store):
    store.save_entity(make_entity("a"))
    store.save_entity(make_entity("b"))
    store.save_entity(make_entity("c"))
    store.add_relationship(make_relationship("a", "b"))
    store.add_relationship(make_relationship("b", "c"))
    store.add_relationship(make_relationship("c", "a"))  # closes the cycle

    result = store.related_entities("a", depth=10)

    assert {e.entity_id for e in result} == {"b", "c"}


def test_related_entities_clamps_depth_to_the_configured_max(tmp_path):
    client = SqliteClient(str(tmp_path / "knowledge.db"))
    store = KnowledgeGraphStore(client, KnowledgeGraphConfig(max_traversal_depth=1))
    store.start()
    store.save_entity(make_entity("a"))
    store.save_entity(make_entity("b"))
    store.save_entity(make_entity("c"))
    store.add_relationship(make_relationship("a", "b"))
    store.add_relationship(make_relationship("b", "c"))

    result = store.related_entities("a", depth=10)  # requests far more than the configured max

    assert {e.entity_id for e in result} == {"b"}
    store.stop()


def test_related_entities_filters_by_relationship_type(store):
    store.save_entity(make_entity("a"))
    store.save_entity(make_entity("b"))
    store.save_entity(make_entity("c"))
    store.add_relationship(make_relationship("a", "b", RelationshipType.DEPENDS_ON))
    store.add_relationship(make_relationship("a", "c", RelationshipType.MENTIONED_IN))

    result = store.related_entities("a", relationship_type=RelationshipType.DEPENDS_ON, depth=1)

    assert {e.entity_id for e in result} == {"b"}


def test_related_entities_for_an_isolated_entity_returns_empty_list(store):
    store.save_entity(make_entity("lonely"))

    assert store.related_entities("lonely") == []


# --- real persistence across close()/reopen -------------------------------------------------


def test_persistence_survives_close_and_reopen(tmp_path):
    db_path = str(tmp_path / "persist.db")

    client1 = SqliteClient(db_path)
    store1 = KnowledgeGraphStore(client1, KnowledgeGraphConfig())
    store1.start()
    store1.save_entity(make_entity("a"))
    store1.save_entity(make_entity("b"))
    store1.add_relationship(make_relationship("a", "b"))
    store1.stop()

    client2 = SqliteClient(db_path)
    store2 = KnowledgeGraphStore(client2, KnowledgeGraphConfig())
    store2.start()
    fetched_entity = store2.get_entity("a")
    fetched_related = store2.related_entities("a")
    store2.stop()

    assert fetched_entity is not None
    assert fetched_entity.name == "JARMINEI"
    assert {e.entity_id for e in fetched_related} == {"b"}


# --- health_check() --------------------------------------------------------------------------


def test_health_check_false_before_start(tmp_path):
    client = SqliteClient(str(tmp_path / "hc.db"))
    store = KnowledgeGraphStore(client, KnowledgeGraphConfig())
    assert store.health_check() is False


def test_health_check_true_after_start(store):
    assert store.health_check() is True


# --- Sprint 6.14 hardening (scenario b): SQLite read failures ---------------------------------


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


def test_find_entities_degrades_to_empty_list_on_a_sqlite_read_failure(tmp_path):
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    knowledge_graph_store = KnowledgeGraphStore(client, KnowledgeGraphConfig())
    knowledge_graph_store.start()
    try:
        knowledge_graph_store.save_entity(make_entity("a"))
        client.raise_on_query = True

        assert knowledge_graph_store.find_entities() == []
        assert knowledge_graph_store.find_entities(entity_type=EntityType.PROJECT) == []
    finally:
        client.raise_on_query = False
        knowledge_graph_store.stop()


def test_get_entity_degrades_to_none_on_a_sqlite_read_failure(tmp_path):
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    knowledge_graph_store = KnowledgeGraphStore(client, KnowledgeGraphConfig())
    knowledge_graph_store.start()
    try:
        knowledge_graph_store.save_entity(make_entity("a"))
        client.raise_on_query = True

        assert knowledge_graph_store.get_entity("a") is None
    finally:
        client.raise_on_query = False
        knowledge_graph_store.stop()


def test_related_entities_degrades_to_empty_list_on_a_sqlite_read_failure(tmp_path):
    """_neighbor_ids() (the internal helper related_entities()'s BFS
    loop calls) degrades to an empty neighbor set on a query failure —
    the whole traversal returns [] rather than raising, since its very
    first hop already fails."""
    client = _RaisingSqliteClient(str(tmp_path / "raising.db"))
    knowledge_graph_store = KnowledgeGraphStore(client, KnowledgeGraphConfig())
    knowledge_graph_store.start()
    try:
        knowledge_graph_store.save_entity(make_entity("a"))
        knowledge_graph_store.save_entity(make_entity("b"))
        knowledge_graph_store.add_relationship(make_relationship("a", "b"))
        client.raise_on_query = True

        assert knowledge_graph_store.related_entities("a") == []
    finally:
        client.raise_on_query = False
        knowledge_graph_store.stop()
