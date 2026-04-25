"""Multi-tenant document retriever.

All searches are strictly scoped to a single tenant namespace — cross-tenant
retrieval is architecturally impossible because:
  1. The Qdrant collection name is derived from the tenant_id.
  2. No query can target a different collection without an explicit override,
     which the API layer never allows.
"""

import logging
from uuid import UUID

from app.embeddings.embedder import EmbeddingService
from app.models.schemas import ChunkResult
from app.vector_store.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)


class DocumentRetriever:
    def __init__(
        self,
        vector_store: QdrantVectorStore,
        embedder: EmbeddingService,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder

    async def retrieve(
        self,
        tenant_id: UUID,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        document_types: list[str] | None = None,
    ) -> list[ChunkResult]:
        """Return the *top_k* most relevant chunks for *query* within *tenant_id*.

        The ``tenant_id`` is converted to the collection namespace
        ``tenant_{tenant_id}`` before any vector store call, guaranteeing
        isolation at the infrastructure level.
        """
        namespace = f"tenant_{tenant_id}"
        query_vector = await self._embedder.embed_one(query)

        raw_hits = await self._store.search(
            namespace=namespace,
            query_vector=query_vector,
            top_k=top_k,
            min_score=min_score,
            document_types=document_types,
        )

        results: list[ChunkResult] = []
        for hit in raw_hits:
            try:
                results.append(
                    ChunkResult(
                        document_id=UUID(hit["document_id"]),
                        filename=hit.get("filename", ""),
                        chunk_index=int(hit.get("chunk_index", 0)),
                        content=hit.get("content", ""),
                        similarity_score=float(hit.get("similarity_score", 0.0)),
                        document_type=hit.get("document_type", "other"),
                        page_number=hit.get("page_number"),
                    )
                )
            except Exception as exc:
                logger.warning("Failed to parse retrieval hit: %s — %s", hit, exc)

        logger.info(
            "Retrieval for tenant=%s query='%.60s' → %d results",
            tenant_id,
            query,
            len(results),
        )
        return results

    async def search_by_namespace(
        self,
        namespace: str,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        document_types: list[str] | None = None,
    ) -> tuple[list[ChunkResult], int]:
        """Search using a pre-built namespace string (called from /search endpoint)."""
        query_vector = await self._embedder.embed_one(query)

        raw_hits = await self._store.search(
            namespace=namespace,
            query_vector=query_vector,
            top_k=top_k,
            min_score=min_score,
            document_types=document_types,
        )

        results: list[ChunkResult] = []
        for hit in raw_hits:
            try:
                results.append(
                    ChunkResult(
                        document_id=UUID(hit["document_id"]),
                        filename=hit.get("filename", ""),
                        chunk_index=int(hit.get("chunk_index", 0)),
                        content=hit.get("content", ""),
                        similarity_score=float(hit.get("similarity_score", 0.0)),
                        document_type=hit.get("document_type", "other"),
                        page_number=hit.get("page_number"),
                    )
                )
            except Exception as exc:
                logger.warning("Failed to parse search hit: %s — %s", hit, exc)

        return results, len(results)
