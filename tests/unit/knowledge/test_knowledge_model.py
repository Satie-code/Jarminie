"""Unit tests for knowledge.knowledge_model."""

from datetime import UTC, datetime

from knowledge.knowledge_model import Entity, EntityType, Relationship, RelationshipType


def test_entity_defaults_description_to_empty_string():
    now = datetime.now(UTC)
    entity = Entity(
        entity_id="e1", entity_type=EntityType.PROJECT, name="JARMINEI", created_at=now,
        last_referenced_at=now,
    )

    assert entity.description == ""


def test_entity_can_carry_a_description():
    now = datetime.now(UTC)
    entity = Entity(
        entity_id="e1",
        entity_type=EntityType.PERSON,
        name="Ada",
        created_at=now,
        last_referenced_at=now,
        description="A collaborator",
    )

    assert entity.description == "A collaborator"


def test_relationship_carries_from_to_type_and_created_at():
    now = datetime.now(UTC)
    relationship = Relationship(
        from_entity_id="e1", to_entity_id="e2", relationship_type=RelationshipType.DEPENDS_ON,
        created_at=now,
    )

    assert relationship.from_entity_id == "e1"
    assert relationship.to_entity_id == "e2"
    assert relationship.relationship_type is RelationshipType.DEPENDS_ON
    assert relationship.created_at == now


def test_entity_type_has_exactly_the_five_expected_members():
    assert {member.value for member in EntityType} == {
        "project",
        "person",
        "goal",
        "file",
        "topic",
    }


def test_relationship_type_has_exactly_the_five_expected_members():
    assert {member.value for member in RelationshipType} == {
        "depends_on",
        "relates_to",
        "owns",
        "part_of",
        "mentioned_in",
    }
