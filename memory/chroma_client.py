"""ChromaMemoryClient — thin wrapper around a persistent ChromaDB client,
one collection per MemoryType.

Embedding function: deliberately ChromaDB's own default (a local
all-MiniLM-L6-v2 ONNX model, bundled with chromadb, downloaded once and
cached under the user's home directory) rather than routing memory writes
through Ollama (config.models.ollama_model, reserved for Decision Engine
reasoning from Sprint 3.7 onward). This keeps semantic *storage* decoupled
from the *reasoning* runtime — see docs/sprint_book/sprint_3_1.md's
Engineering Rationale for the full justification. If embedding quality
ever proves inadequate, swapping the embedding function is contained to
this file.
"""

import chromadb
from chromadb.api.models.Collection import Collection

from config.schema import DatabaseConfig, MemoryConfig
from core.logging_setup import get_logger
from memory.models import MemoryType

logger = get_logger(__name__)


class ChromaMemoryClient:
    """Owns one chromadb.PersistentClient and one collection per
    MemoryType. Knows nothing about SQLite or MemoryRecord's full shape —
    only (record_id, content) pairs and similarity queries over them."""

    def __init__(self, memory_config: MemoryConfig, database_config: DatabaseConfig) -> None:
        self._memory_config = memory_config
        self._database_config = database_config
        self._client: chromadb.ClientAPI | None = None

    def connect(self) -> None:
        """Open the persistent client. Safe to call again after close()."""
        self._client = chromadb.PersistentClient(path=self._database_config.chroma_path)
        logger.info("ChromaMemoryClient connected: %s", self._database_config.chroma_path)

    def ensure_collections(self) -> None:
        """Create all five MemoryType collections if they don't already
        exist (idempotent)."""
        for memory_type in MemoryType:
            self._collection(memory_type)

    def add_embedding(self, memory_type: MemoryType, record_id: str, content: str) -> None:
        collection = self._collection(memory_type)
        collection.add(ids=[record_id], documents=[content])

    def query(
        self, memory_type: MemoryType, query_text: str, n_results: int
    ) -> list[tuple[str, float]]:
        """Return up to n_results (record_id, distance) pairs, nearest
        first. An empty collection or n_results <= 0 returns an empty
        list rather than erroring."""
        collection = self._collection(memory_type)
        if collection.count() == 0 or n_results <= 0:
            return []
        result = collection.query(
            query_texts=[query_text], n_results=min(n_results, collection.count())
        )
        ids = result["ids"][0]
        distances = result["distances"][0]
        return list(zip(ids, distances, strict=True))

    def delete_embedding(self, memory_type: MemoryType, record_id: str) -> None:
        self._collection(memory_type).delete(ids=[record_id])

    def close(self) -> None:
        # chromadb's PersistentClient has no explicit close/disconnect —
        # dropping the reference is the documented cleanup. Deliberate
        # no-op beyond that, not an oversight.
        self._client = None
        logger.info("ChromaMemoryClient closed.")

    def health_check(self) -> bool:
        if self._client is None:
            return False
        try:
            self._client.heartbeat()
            return True
        except Exception:
            logger.exception("ChromaMemoryClient health check failed.")
            return False

    def _collection(self, memory_type: MemoryType) -> Collection:
        client = self._require_client()
        name = f"{self._memory_config.chroma_collection_prefix}_{memory_type.value}"
        return client.get_or_create_collection(name)

    def _require_client(self) -> chromadb.ClientAPI:
        if self._client is None:
            raise RuntimeError("ChromaMemoryClient.connect() must be called before use.")
        return self._client
