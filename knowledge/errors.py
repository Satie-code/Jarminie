"""Knowledge Graph errors."""


class TooManyRelationshipsError(Exception):
    """Raised by KnowledgeGraphStore.add_relationship() when adding the
    relationship would push either endpoint's own relationship count
    beyond KnowledgeGraphConfig.max_relationships_per_entity — the same
    defensive-bound-enforced-at-the-write-boundary discipline
    planning/task_graph.py's CyclicDependencyError already established
    for max_task_dependencies."""
