"""
Vector database integration (spec section 54) using Qdrant.

Two real modes, same API on both sides:
- "embedded": Qdrant runs in-process against local disk via the official
  `qdrant-client` local mode — genuinely a real vector database (proper
  HNSW-backed similarity search under the hood), just single-process. Good
  for development and small deployments; no separate server to run.
- "server": point QDRANT_URL at a standalone Qdrant instance (e.g. the
  `qdrant/qdrant` Docker image) for production/multi-worker deployments.

Switching modes is a config change (QDRANT_MODE / QDRANT_URL), not a code
change — everything above this module talks to `VectorStore`, never to the
Qdrant client directly.
"""
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.core.config import settings

COLLECTION_NAME = "knowledge_chunks"


class VectorStore:
    def __init__(self, client: QdrantClient):
        self.client = client
        self._ensured_dim: int | None = None

    def _ensure_collection(self, dim: int) -> None:
        if self._ensured_dim == dim:
            return
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME not in existing:
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
        else:
            info = self.client.get_collection(COLLECTION_NAME)
            current_dim = info.config.params.vectors.size
            if current_dim != dim:
                # Embedding dimensionality changed (e.g. TF-IDF vocabulary
                # grew after new documents were ingested) — recreate the
                # collection; reembed_all_chunks() always repopulates it fully
                # right after calling this, so this is safe.
                self.client.delete_collection(COLLECTION_NAME)
                self.client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
        self._ensured_dim = dim

    def upsert_chunks(self, chunks: list[dict]) -> None:
        """chunks: [{"id": <int>, "vector": [...], "payload": {...}}, ...]"""
        if not chunks:
            return
        dim = len(chunks[0]["vector"])
        self._ensure_collection(dim)
        points = [PointStruct(id=c["id"], vector=c["vector"], payload=c["payload"]) for c in chunks]
        self.client.upsert(collection_name=COLLECTION_NAME, points=points)

    def clear(self) -> None:
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME in existing:
            self.client.delete_collection(COLLECTION_NAME)
        self._ensured_dim = None

    def search(self, query_vector: list[float], top_k: int, document_ids: list[str] | None = None) -> list[dict]:
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME not in existing:
            return []

        query_filter = None
        if document_ids:
            query_filter = Filter(
                should=[FieldCondition(key="document_id", match=MatchValue(value=doc_id)) for doc_id in document_ids]
            )

        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
        )
        return [
            {"chunk_id": point.payload["chunk_id"], "score": point.score, "payload": point.payload}
            for point in results.points
        ]


@lru_cache
def get_vector_store() -> VectorStore:
    if settings.QDRANT_MODE == "server" and settings.QDRANT_URL:
        client = QdrantClient(url=settings.QDRANT_URL)
    else:
        client = QdrantClient(path=settings.QDRANT_PATH)
    return VectorStore(client)
