"""CRM indexing Redis Streams consumer.

Subscribes to ``rag:index:jobs`` (default) using a Redis consumer group
(``rag-indexer-group``) and, for every successfully read entry:

1. Decodes the payload published by ``backend/app/crm/rag_publisher.py``.
2. Runs the chunk -> embed -> upsert pipeline in the per-tenant Qdrant
   namespace (``tenant_<tenant_id>``), preserving multi-tenant isolation.
3. ACKs the message on success.
4. On failure, increments a retry counter; once it exceeds
   ``crm_index_max_retries`` the entry is pushed to the DLQ
   (``rag:index:jobs:dlq``) and ACKed to release the PEL slot.

Payload fields produced by the backend:
    job_id          str (job_crm_<uuid4>)
    schema_version  str ("1.0")
    type            str ("crm_entity_index")
    priority        str ("low")
    tenant_id       str (UUID)
    entity_type     str ("deal_note")
    entity_id       str (deal UUID)
    content         str (deal notes)
    metadata        str (JSON: {deal_id, account_id, stage})

Notes
-----
Redis Streams XREADGROUP returns a list of (stream_name, [(id, {field: value})])
tuples. Field/values are bytes by default; we decode via ``decode_responses=True``
so this module can stay free of byte/str juggling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Mapping
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from app.config import settings
from app.embeddings.embedder import EmbeddingService
from app.indexing.chunker import TextChunker
from app.queue.dlq import push_to_dlq, retry_counter_key
from app.vector_store.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)

_SHUTDOWN_TIMEOUT = 5.0
_RETRY_KEY_TTL_SECONDS = 60 * 60 * 24  # 1 day


class CrmStreamConsumer:
    """Consume CRM indexing jobs from a Redis stream with at-least-once delivery."""

    def __init__(
        self,
        vector_store: QdrantVectorStore,
        embedder: EmbeddingService,
        chunker: TextChunker,
        *,
        consumer_name: str | None = None,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder
        self._chunker = chunker
        self._consumer_name = (
            consumer_name or f"{socket.gethostname()}-{uuid4().hex[:8]}"
        )
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
        await self._ensure_group()
        self._running = True
        self._task = asyncio.create_task(self._run(), name="crm-stream-consumer")
        logger.info(
            "CRM stream consumer started — stream=%s group=%s consumer=%s",
            settings.crm_index_stream,
            settings.crm_index_group,
            self._consumer_name,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=_SHUTDOWN_TIMEOUT)
            except asyncio.TimeoutError:
                self._task.cancel()
        if self._redis:
            await self._redis.aclose()
        logger.info("CRM stream consumer stopped")

    async def _ensure_group(self) -> None:
        """Create the consumer group if it does not yet exist (idempotent)."""
        assert self._redis is not None
        try:
            await self._redis.xgroup_create(
                settings.crm_index_stream,
                settings.crm_index_group,
                id="$",
                mkstream=True,
            )
            logger.info(
                "Created consumer group %s on stream %s",
                settings.crm_index_group,
                settings.crm_index_stream,
            )
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.debug(
                    "Consumer group %s already exists", settings.crm_index_group
                )
                return
            raise

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        assert self._redis is not None
        while self._running:
            try:
                response = await self._redis.xreadgroup(
                    groupname=settings.crm_index_group,
                    consumername=self._consumer_name,
                    streams={settings.crm_index_stream: ">"},
                    count=settings.crm_index_count,
                    block=settings.crm_index_block_ms,
                )
            except asyncio.CancelledError:
                break
            except aioredis.ResponseError as exc:
                if "NOGROUP" in str(exc):
                    logger.warning(
                        "Consumer group lost (Redis restart?), recreating …"
                    )
                    try:
                        await self._ensure_group()
                    except Exception as eg:
                        logger.error("Failed to recreate consumer group: %s", eg)
                else:
                    logger.error("XREADGROUP failed: %s", exc, exc_info=True)
                await asyncio.sleep(1)
                continue
            except Exception as exc:
                logger.error("XREADGROUP failed: %s", exc, exc_info=True)
                await asyncio.sleep(1)
                continue

            if not response:
                continue

            for _stream, entries in response:
                for entry_id, fields in entries:
                    await self._handle_entry(entry_id, fields)

    # ------------------------------------------------------------------
    # Entry handling
    # ------------------------------------------------------------------

    async def _handle_entry(self, entry_id: str, fields: Mapping[str, str]) -> None:
        assert self._redis is not None
        try:
            await self.process_job(fields)
        except Exception as exc:
            attempts = await self._redis.incr(retry_counter_key(entry_id))
            await self._redis.expire(
                retry_counter_key(entry_id), _RETRY_KEY_TTL_SECONDS
            )
            logger.warning(
                "Job %s failed (attempt %d/%d): %s",
                entry_id,
                attempts,
                settings.crm_index_max_retries,
                exc,
            )
            if attempts >= settings.crm_index_max_retries:
                await push_to_dlq(
                    self._redis,
                    original_id=entry_id,
                    payload=dict(fields),
                    error=f"{type(exc).__name__}: {exc}",
                    attempts=attempts,
                )
                await self._ack(entry_id)
                await self._redis.delete(retry_counter_key(entry_id))
            return

        # success → ACK + reset retry counter
        await self._ack(entry_id)
        await self._redis.delete(retry_counter_key(entry_id))

    async def _ack(self, entry_id: str) -> None:
        assert self._redis is not None
        await self._redis.xack(
            settings.crm_index_stream, settings.crm_index_group, entry_id
        )

    # ------------------------------------------------------------------
    # Job processing (public for test seams)
    # ------------------------------------------------------------------

    async def process_job(self, fields: Mapping[str, str]) -> None:
        """Decode the payload and run chunk → embed → upsert.

        Raises any underlying exception so the caller can apply retry / DLQ
        logic. This method is the natural seam for unit tests.
        """

        tenant_id_raw = fields.get("tenant_id")
        if not tenant_id_raw:
            raise ValueError("missing tenant_id in CRM index job")
        tenant_id = UUID(tenant_id_raw)

        entity_type = fields.get("entity_type", "unknown")
        entity_id_raw = fields.get("entity_id")
        if not entity_id_raw:
            raise ValueError("missing entity_id in CRM index job")
        entity_id = UUID(entity_id_raw)

        content = fields.get("content", "")
        if not content.strip():
            logger.info(
                "Skip empty content for tenant=%s entity=%s/%s",
                tenant_id,
                entity_type,
                entity_id,
            )
            return

        # `metadata` is a JSON string per ADR-008.
        try:
            metadata = json.loads(fields.get("metadata") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON metadata: {exc}") from exc

        namespace = f"tenant_{tenant_id}"
        document_type = entity_type  # e.g. "deal_note"

        chunks = self._chunker.split(content, document_type=document_type)
        if not chunks:
            logger.info(
                "No chunks produced for tenant=%s entity=%s/%s — skipping",
                tenant_id,
                entity_type,
                entity_id,
            )
            return

        texts = [c.text for c in chunks]
        embeddings = await self._embedder.embed(texts)

        # entity_id doubles as document_id so updates overwrite previous chunks.
        # The current `QdrantVectorStore.upsert_chunks` signature does not
        # accept extra metadata; deal-specific fields (account_id, stage…) are
        # logged for now and will be plumbed through the store payload in a
        # follow-up commit when the schema evolves.
        if metadata:
            logger.debug(
                "CRM index extra metadata (not yet stored on points): %s",
                metadata,
            )
        await self._store.delete_document(namespace, entity_id)
        count = await self._store.upsert_chunks(
            namespace=namespace,
            document_id=entity_id,
            filename=f"{entity_type}-{entity_id}",
            document_type=document_type,
            chunks=texts,
            embeddings=embeddings,
        )

        logger.info(
            "Indexed %s for tenant=%s entity_id=%s (%d chunks) into %s",
            entity_type,
            tenant_id,
            entity_id,
            count,
            namespace,
        )
