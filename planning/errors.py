"""Planning Engine errors. See docs/sprint_book/sprint_6/sprint_6_2.md."""


class CyclicDependencyError(Exception):
    """Raised by TaskGraph.add_dependency() when the requested edge would
    create a cycle — never silently accepted, since an accepted cycle
    would make ready_tasks() return an empty list forever for the
    affected tasks with no way to recover except manual data surgery.
    Level 6's own Safe Failure design principle applied concretely:
    reject the bad input at the boundary rather than let it corrupt
    state that only manifests as a confusing silent stall later."""
