"""RAG service entry point.

Exposes:
  GET  /health         — liveness + dependency status
  POST /ingest         — document ingestion (async, background task)
  POST /search         — semantic search by namespace (mcp-filesystem)
  POST /retrieve       — semantic retrieval by tenant_id (orchestrator)
  DELETE /documents/{id} — delete all chunks for a document

Port: 8002 (distinct from backend:8000 and orchestrator:8001)
Auth: X-Internal-API-Key header on all non-health endpoints
"""

import logging
import logging.config
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import require_internal_api_key
from app.embeddings.embedder import EmbeddingService
from app.indexing.chunker import TextChunker
from app.models.schemas import HealthResponse
from app.queue.worker import RedisIngestionWorker
from app.retrieval.retriever import DocumentRetriever
from app.routers import ingest, retrieve
from app.vector_store.qdrant_store import QdrantVectorStore

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting RAG service (env=%s)", settings.environment)

    # Initialise singletons
    embedder = EmbeddingService(
        model_name=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
    )
    embedder.load()

    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        dimensions=embedder.dimensions,
        api_key=settings.qdrant_api_key,
    )

    chunker = TextChunker(
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )

    retriever = DocumentRetriever(vector_store=vector_store, embedder=embedder)

    # Redis background worker
    worker = RedisIngestionWorker(
        vector_store=vector_store,
        embedder=embedder,
        chunker=chunker,
    )
    await worker.start()

    # Store on app.state for dependency injection
    app.state.embedder = embedder
    app.state.vector_store = vector_store
    app.state.chunker = chunker
    app.state.retriever = retriever
    app.state.worker = worker

    logger.info(
        "RAG service ready — model=%s dim=%d qdrant=%s",
        settings.embedding_model,
        embedder.dimensions,
        settings.qdrant_url,
    )

    yield

    logger.info("Shutting down RAG service …")
    await worker.stop()
    await vector_store.close()
    logger.info("RAG service stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RevOps RAG Service",
    description=(
        "Multi-tenant RAG layer for the RevOps IA SaaS platform. "
        "Handles document ingestion, embedding, and semantic retrieval "
        "with strict tenant isolation via per-tenant Qdrant collections."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(ingest.router)
app.include_router(retrieve.router)


# ---------------------------------------------------------------------------
# Health check (no auth required)
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Liveness + dependency health check."""
    qdrant_ok = False
    redis_ok = False

    try:
        qdrant_ok = await app.state.vector_store.ping()
    except Exception:
        pass

    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        redis_ok = True
    except Exception:
        pass

    overall = "ok" if qdrant_ok and redis_ok else "degraded"

    return HealthResponse(
        status=overall,
        qdrant="ok" if qdrant_ok else "unavailable",
        redis="ok" if redis_ok else "unavailable",
        embedding_model=settings.embedding_model,
    )
