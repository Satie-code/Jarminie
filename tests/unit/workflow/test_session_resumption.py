"""Unit tests for workflow.session_resumption.

KnowledgeGraphStore is faked (only find_entities()/related_entities()
are needed, matching this codebase's own "fake at the boundary"
convention) — its own real persistence/traversal logic is already
covered by tests/unit/knowledge/test_knowledge_graph_store.py.
ContextEngine is accepted but never called (see session_resumption.py's
own docstring) — a bare sentinel stands in for it.
"""

from datetime import UTC, datetime, timedelta

from config.schema import WorkflowConfig
from device_control.action_engine import ActionType
from knowledge.knowledge_model import Entity, EntityType
from workflow.session_resumption import SessionResumption

_NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
_UNUSED_CONTEXT_ENGINE = object()
"""SessionResumption never calls context_engine this sprint — see that
module's own docstring."""


class FakeKnowledgeGraphStore:
    def __init__(self, entities: list[Entity], relationships: dict[str, list[Entity]]) -> None:
        self._entities = entities
        self._relationships = relationships

    def find_entities(self, entity_type=None, name_contains=None) -> list[Entity]:
        return [e for e in self._entities if entity_type is None or e.entity_type is entity_type]

    def related_entities(self, entity_id, relationship_type=None, depth=1) -> list[Entity]:
        return self._relationships.get(entity_id, [])


def _project(entity_id: str, name: str, last_referenced_at: datetime) -> Entity:
    return Entity(
        entity_id=entity_id,
        entity_type=EntityType.PROJECT,
        name=name,
        created_at=last_referenced_at - timedelta(days=30),
        last_referenced_at=last_referenced_at,
    )


def _file(entity_id: str, name: str) -> Entity:
    return Entity(
        entity_id=entity_id,
        entity_type=EntityType.FILE,
        name=name,
        created_at=_NOW,
        last_referenced_at=_NOW,
    )


def _resumption(store: FakeKnowledgeGraphStore) -> SessionResumption:
    return SessionResumption(store, _UNUSED_CONTEXT_ENGINE, WorkflowConfig())


# --- no project entity -----------------------------------------------------------------------


def test_build_workflow_returns_none_when_no_project_entity_exists():
    store = FakeKnowledgeGraphStore(entities=[], relationships={})
    resumption = _resumption(store)

    assert resumption.build_workflow(created_by="test") is None


def test_build_workflow_returns_none_when_only_non_project_entities_exist():
    goal_entity = Entity(
        entity_id="g1",
        entity_type=EntityType.GOAL,
        name="Learn to code",
        created_at=_NOW,
        last_referenced_at=_NOW,
    )
    store = FakeKnowledgeGraphStore(entities=[goal_entity], relationships={})
    resumption = _resumption(store)

    assert resumption.build_workflow(created_by="test") is None


# --- a populated knowledge graph -------------------------------------------------------------


def test_build_workflow_picks_the_most_recently_referenced_project():
    older = _project("p1", "Old Project", _NOW - timedelta(days=30))
    newer = _project("p2", "JARMINEI", _NOW - timedelta(days=1))
    store = FakeKnowledgeGraphStore(entities=[older, newer], relationships={})
    resumption = _resumption(store)

    workflow = resumption.build_workflow(created_by="test")

    assert workflow is not None
    assert "JARMINEI" in workflow.name


def test_build_workflow_builds_steps_from_related_file_entities():
    project = _project("p1", "JARMINEI", _NOW)
    file_entity = _file("f1", "main.py")
    store = FakeKnowledgeGraphStore(
        entities=[project], relationships={"p1": [file_entity]}
    )
    resumption = _resumption(store)

    workflow = resumption.build_workflow(created_by="test")

    assert workflow is not None
    assert len(workflow.steps) == 1
    assert workflow.steps[0].action_type is ActionType.LAUNCH_APPLICATION
    assert workflow.steps[0].parameters == {"executable_path": "main.py"}
    assert "main.py" in workflow.steps[0].description


def test_build_workflow_classifies_a_url_shaped_file_name_as_open_url():
    project = _project("p1", "JARMINEI", _NOW)
    file_entity = _file("f1", "https://example.com/docs")
    store = FakeKnowledgeGraphStore(
        entities=[project], relationships={"p1": [file_entity]}
    )
    resumption = _resumption(store)

    workflow = resumption.build_workflow(created_by="test")

    assert workflow.steps[0].action_type is ActionType.OPEN_URL
    assert workflow.steps[0].parameters == {"url": "https://example.com/docs"}


def test_build_workflow_ignores_non_file_related_entities():
    project = _project("p1", "JARMINEI", _NOW)
    person_entity = Entity(
        entity_id="e1",
        entity_type=EntityType.PERSON,
        name="Ada",
        created_at=_NOW,
        last_referenced_at=_NOW,
    )
    store = FakeKnowledgeGraphStore(
        entities=[project], relationships={"p1": [person_entity]}
    )
    resumption = _resumption(store)

    workflow = resumption.build_workflow(created_by="test")

    assert workflow is not None
    assert workflow.steps == []


def test_build_workflow_with_a_project_but_no_related_files_returns_a_real_empty_workflow():
    project = _project("p1", "JARMINEI", _NOW)
    store = FakeKnowledgeGraphStore(entities=[project], relationships={})
    resumption = _resumption(store)

    workflow = resumption.build_workflow(created_by="test")

    assert workflow is not None
    assert workflow.steps == []


def test_build_workflow_carries_created_by_and_a_real_id():
    project = _project("p1", "JARMINEI", _NOW)
    store = FakeKnowledgeGraphStore(entities=[project], relationships={})
    resumption = _resumption(store)

    workflow = resumption.build_workflow(created_by="voice_turn")

    assert workflow.created_by == "voice_turn"
    assert workflow.workflow_id
