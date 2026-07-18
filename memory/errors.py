"""Memory-layer error hierarchy.

Mirrors voice/errors.py's pattern (Sprint 2.1): every Level 3 memory module
raises a subclass of MemoryError rather than a bare exception. Each later
memory sprint adds its own subclass here rather than starting a parallel
hierarchy.
"""


class MemoryError(Exception):
    """Base class for any Memory Engine failure."""


class MemoryStoreError(MemoryError):
    """Raised for memory store lifecycle failures (e.g. starting before the
    underlying SQLite/Chroma backends can be opened). Individual failed
    reads/writes are logged, not raised — see MemoryStore.store()."""
