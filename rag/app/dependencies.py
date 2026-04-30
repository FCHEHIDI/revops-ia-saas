"""FastAPI dependency injection for the RAG service."""

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import settings
from app.embeddings.embedder import EmbeddingService
from app.indexing.chunker import TextChunker
from app.retrieval.retriever import DocumentRetriever
from app.vector_store.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentication — inter-service API key
# ---------------------------------------------------------------------------


async def require_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Validate the X-Internal-API-Key header on every protected endpoint."""
    if x_internal_api_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Internal-API-Key header",
        )


# ---------------------------------------------------------------------------
# Singletons (stored on app.state at startup)
# ---------------------------------------------------------------------------


def get_vector_store(request: Request) -> QdrantVectorStore:
    return request.app.state.vector_store


def get_embedder(request: Request) -> EmbeddingService:
    return request.app.state.embedder


def get_chunker(request: Request) -> TextChunker:
    return request.app.state.chunker


def get_retriever(request: Request) -> DocumentRetriever:
    return request.app.state.retriever
