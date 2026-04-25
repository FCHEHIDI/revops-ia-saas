"""Multi-tenant Qdrant vector store.

Each tenant owns an isolated collection named ``tenant_{tenant_id}``.
All operations are scoped to a single collection — cross-tenant access
is structurally impossible because collection names are controlled
server-side and derived from the validated tenant identity.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

logger = logging.getLogger(__name__)


def _collection_name(namespace_or_tenant_id: str) -> str:
    """Normalise a namespace or raw tenant_id into a Qdrant collection name.

    Accepts both ``tenant_{uuid}`` (already formatted) and raw UUID strings.
    """
    s = namespace_or_tenant_id.strip()
    if s.startswith("tenant_"):
        return s
    return f"tenant_{s}"


class QdrantVectorStore:
    """Async wrapper around qdrant-client with per-tenant collection management."""

    def __init__(
        self,
        url: str,
        dimensions: int,
        api_key: str | None = None,
    ) -> None:
        self._url = url
        self._dimensions = dimensions
        self._client = AsyncQdrantClient(url=url, api_key=api_key)

    # ------------------------------------------------------------------
    # Collection lifecycle
    # ------------------------------------------------------------------

    async def ensure_collection(self, namespace: str) -> None:
        """Create the collection for *namespace* if it does not yet exist."""
        name = _collection_name(namespace)
        existing = {c.name for c in (await self._client.get_collections()).collections}
        if name not in existing:
            await self._client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=self._dimensions,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection '%s'", name)

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    async def upsert_chunks(
        self,
        namespace: str,
        document_id: UUID,
        filename: str,
        document_type: str,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> int:
        """Store *chunks* with their *embeddings* in the tenant collection.

        Each chunk becomes one Qdrant point.  The point payload stores all
        metadata needed to reconstruct a ``ChunkResult`` at retrieval time.
        """
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        await self.ensure_collection(namespace)
        name = _collection_name(namespace)
        now = datetime.now(timezone.utc).isoformat()

        points = [
            qmodels.PointStruct(
                id=str(uuid4()),
                vector=emb,
                payload={
                    "document_id": str(document_id),
                    "filename": filename,
                    "chunk_index": idx,
                    "content": text,
                    "document_type": document_type,
                    "page_number": None,
                    "created_at": now,
                },
            )
            for idx, (text, emb) in enumerate(zip(chunks, embeddings))
        ]

        await self._client.upsert(collection_name=name, points=points)
        logger.info(
            "Upserted %d chunks for document %s in collection '%s'",
            len(points),
            document_id,
            name,
        )
        return len(points)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        namespace: str,
        query_vector: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
        document_types: list[str] | None = None,
    ) -> list[dict]:
        """Cosine-similarity search within *namespace* collection.

        Returns raw payloads augmented with ``similarity_score``.
        """
        name = _collection_name(namespace)
        existing = {c.name for c in (await self._client.get_collections()).collections}
        if name not in existing:
            logger.warning("Collection '%s' does not exist — returning empty", name)
            return []

        query_filter: qmodels.Filter | None = None
        if document_types:
            query_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="document_type",
                        match=qmodels.MatchAny(any=document_types),
                    )
                ]
            )

        results = await self._client.search(
            collection_name=name,
            query_vector=query_vector,
            limit=top_k,
            score_threshold=min_score if min_score > 0.0 else None,
            query_filter=query_filter,
            with_payload=True,
        )

        hits = []
        for r in results:
            payload = dict(r.payload or {})
            payload["similarity_score"] = r.score
            hits.append(payload)

        return hits

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_document(self, namespace: str, document_id: UUID) -> int:
        """Delete all points belonging to *document_id* in *namespace*."""
        name = _collection_name(namespace)
        existing = {c.name for c in (await self._client.get_collections()).collections}
        if name not in existing:
            return 0

        response = await self._client.delete(
            collection_name=name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchValue(value=str(document_id)),
                        )
                    ]
                )
            ),
        )
        deleted = getattr(response, "deleted_count", 0) or 0
        logger.info(
            "Deleted %d points for document %s in collection '%s'",
            deleted,
            document_id,
            name,
        )
        return deleted

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.close()
