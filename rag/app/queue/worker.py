"""Redis ingestion worker.

Consumes jobs pushed to ``rag:indexing`` by ``mcp-filesystem`` after a
successful ``upload_report`` call.  Each job triggers the full ingestion
pipeline: read → chunk → embed → upsert into Qdrant.

Expected job JSON format (pushed by mcp-filesystem):
  {
    "tenant_id": "<uuid>",
    "file_path": "tenants/<uuid>/reports/<doc_id>/<filename>",
    "file_name": "Q4-forecast.pdf",
    "content_type": "text/plain",
    "document_id": "<uuid>",   // optional
    "document_type": "report"  // optional
  }
"""

import asyncio
import json
import logging
import os
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from app.config import settings
from app.embeddings.embedder import EmbeddingService
from app.indexing.chunker import TextChunker
from app.models.schemas import RedisIngestJob
from app.vector_store.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)

_WORKER_SHUTDOWN_TIMEOUT = 5.0


class RedisIngestionWorker:
    """Long-running background worker that polls a Redis list for ingest jobs.

    Uses ``BLPOP`` with a short timeout so the loop can be interrupted cleanly
    on application shutdown.
    """

    def __init__(
        self,
        vector_store: QdrantVectorStore,
        embedder: EmbeddingService,
        chunker: TextChunker,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder
        self._chunker = chunker
        self._redis: aioredis.Redis | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        self._running = True
        self._task = asyncio.create_task(self._run(), name="redis-ingestion-worker")
        logger.info(
            "Redis ingestion worker started — queue='%s'",
            settings.indexing_queue_name,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=_WORKER_SHUTDOWN_TIMEOUT)
            except asyncio.TimeoutError:
                self._task.cancel()
        if self._redis:
            await self._redis.aclose()
        logger.info("Redis ingestion worker stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while self._running:
            try:
                result = await self._redis.blpop(  # type: ignore[union-attr]
                    settings.indexing_queue_name,
                    timeout=2,
                )
                if result is None:
                    continue
                _, raw = result
                await self._process(raw)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Worker loop error: %s", exc, exc_info=True)
                await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Job processing
    # ------------------------------------------------------------------

    async def _process(self, raw: str) -> None:
        try:
            data = json.loads(raw)
            job = RedisIngestJob.model_validate(data)
        except Exception as exc:
            logger.error("Failed to parse Redis job payload: %s — %s", raw[:200], exc)
            return

        logger.info(
            "Processing ingest job: tenant=%s file=%s",
            job.tenant_id,
            job.file_name,
        )

        try:
            content = await self._read_content(job)
        except Exception as exc:
            logger.error(
                "Cannot read content for job tenant=%s file=%s: %s",
                job.tenant_id,
                job.file_path,
                exc,
            )
            return

        if not content.strip():
            logger.warning("Empty content for job file=%s — skipping", job.file_name)
            return

        document_id = UUID(job.document_id) if job.document_id else uuid4()
        document_type = job.document_type or "other"
        namespace = f"tenant_{job.tenant_id}"

        await self._ingest_content(
            namespace=namespace,
            document_id=document_id,
            filename=job.file_name,
            document_type=document_type,
            content=content,
        )

    async def _read_content(self, job: RedisIngestJob) -> str:
        """Read file content from the shared storage volume."""
        full_path = os.path.join(settings.storage_base_path, job.file_path)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _read_file, full_path)

    async def _ingest_content(
        self,
        namespace: str,
        document_id: UUID,
        filename: str,
        document_type: str,
        content: str,
    ) -> None:
        """Full ingestion pipeline: chunk → embed → store."""
        chunks = self._chunker.split(content, document_type=document_type)
        if not chunks:
            logger.warning("No chunks produced for document %s", document_id)
            return

        texts = [c.text for c in chunks]
        embeddings = await self._embedder.embed(texts)

        # Delete stale chunks from previous version before upserting
        await self._store.delete_document(namespace, document_id)

        count = await self._store.upsert_chunks(
            namespace=namespace,
            document_id=document_id,
            filename=filename,
            document_type=document_type,
            chunks=texts,
            embeddings=embeddings,
        )
        logger.info(
            "Ingested document %s → %d chunks in namespace '%s'",
            document_id,
            count,
            namespace,
        )


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()
