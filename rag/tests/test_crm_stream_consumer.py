"""Tests for ``app.queue.crm_stream_consumer.CrmStreamConsumer``.

We cover the contract surface of the consumer without requiring a real
Redis or Qdrant: the class exposes ``process_job`` as a public seam, and the
retry / DLQ logic lives in ``_handle_entry`` against an injected fake redis
that mimics the small subset of methods we use (incr, expire, xack, delete,
xadd).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.queue import dlq as dlq_module
from app.queue.crm_stream_consumer import CrmStreamConsumer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_consumer() -> CrmStreamConsumer:
    """Build a consumer with mock dependencies for unit tests."""
    vector_store = MagicMock()
    vector_store.delete_document = AsyncMock(return_value=None)
    vector_store.upsert_chunks = AsyncMock(return_value=3)

    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 384] * 2)

    chunk_obj = MagicMock()
    chunk_obj.text = "chunked text"
    chunker = MagicMock()
    chunker.split = MagicMock(return_value=[chunk_obj, chunk_obj])

    return CrmStreamConsumer(
        vector_store=vector_store,
        embedder=embedder,
        chunker=chunker,
        consumer_name="test-consumer",
    )


def valid_job_fields(**overrides: str) -> dict[str, str]:
    payload = {
        "job_id": "job_crm_test",
        "schema_version": "1.0",
        "type": "crm_entity_index",
        "priority": "low",
        "tenant_id": str(UUID("11111111-1111-1111-1111-111111111111")),
        "entity_type": "deal_note",
        "entity_id": str(UUID("22222222-2222-2222-2222-222222222222")),
        "content": "Note: discussed pricing with prospect.",
        "metadata": json.dumps(
            {"deal_id": "22222222-2222-2222-2222-222222222222", "stage": "negotiation"}
        ),
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# process_job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_job_runs_full_pipeline_with_tenant_namespace() -> None:
    consumer = make_consumer()
    fields = valid_job_fields()

    await consumer.process_job(fields)

    consumer._chunker.split.assert_called_once()
    consumer._embedder.embed.assert_awaited_once()
    consumer._store.delete_document.assert_awaited_once()
    consumer._store.upsert_chunks.assert_awaited_once()

    # multi-tenant isolation: the namespace must derive from tenant_id
    upsert_kwargs = consumer._store.upsert_chunks.await_args.kwargs
    assert upsert_kwargs["namespace"] == "tenant_11111111-1111-1111-1111-111111111111"
    assert upsert_kwargs["document_id"] == UUID("22222222-2222-2222-2222-222222222222")
    assert upsert_kwargs["document_type"] == "deal_note"


@pytest.mark.asyncio
async def test_process_job_skips_empty_content() -> None:
    consumer = make_consumer()
    fields = valid_job_fields(content="   \n  ")

    await consumer.process_job(fields)

    consumer._chunker.split.assert_not_called()
    consumer._embedder.embed.assert_not_awaited()
    consumer._store.upsert_chunks.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_job_rejects_invalid_metadata_json() -> None:
    consumer = make_consumer()
    fields = valid_job_fields(metadata="{not-json")

    with pytest.raises(ValueError, match="invalid JSON metadata"):
        await consumer.process_job(fields)


@pytest.mark.asyncio
async def test_process_job_requires_tenant_id() -> None:
    consumer = make_consumer()
    fields = valid_job_fields()
    del fields["tenant_id"]

    with pytest.raises(ValueError, match="missing tenant_id"):
        await consumer.process_job(fields)


@pytest.mark.asyncio
async def test_process_job_requires_entity_id() -> None:
    consumer = make_consumer()
    fields = valid_job_fields()
    del fields["entity_id"]

    with pytest.raises(ValueError, match="missing entity_id"):
        await consumer.process_job(fields)


@pytest.mark.asyncio
async def test_process_job_skips_when_chunker_returns_empty() -> None:
    consumer = make_consumer()
    consumer._chunker.split = MagicMock(return_value=[])
    fields = valid_job_fields()

    await consumer.process_job(fields)

    consumer._embedder.embed.assert_not_awaited()
    consumer._store.upsert_chunks.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_entry: retry + DLQ logic
# ---------------------------------------------------------------------------


class FakeRedis:
    """Minimal in-memory shim implementing the methods used by ``_handle_entry``."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.acked: list[tuple[str, str, str]] = []
        self.deleted: list[str] = []
        self.dlq_entries: list[tuple[str, dict[str, str]]] = []
        self.expired: list[tuple[str, int]] = []

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, ttl: int) -> bool:
        self.expired.append((key, ttl))
        return True

    async def xack(self, stream: str, group: str, entry_id: str) -> int:
        self.acked.append((stream, group, entry_id))
        return 1

    async def delete(self, *keys: str) -> int:
        self.deleted.extend(keys)
        for k in keys:
            self.counters.pop(k, None)
        return len(keys)

    async def xadd(self, stream: str, fields: dict[str, str]) -> str:
        eid = f"{stream}-{len(self.dlq_entries)}-0"
        self.dlq_entries.append((stream, dict(fields)))
        return eid


@pytest.mark.asyncio
async def test_handle_entry_acks_on_success() -> None:
    consumer = make_consumer()
    consumer._redis = FakeRedis()  # type: ignore[assignment]
    fields = valid_job_fields()

    await consumer._handle_entry("1700000000000-0", fields)

    fake = consumer._redis  # type: ignore[assignment]
    assert ("rag:index:jobs", "rag-indexer-group", "1700000000000-0") in fake.acked
    assert fake.dlq_entries == []


@pytest.mark.asyncio
async def test_handle_entry_pushes_to_dlq_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer = make_consumer()
    consumer._redis = FakeRedis()  # type: ignore[assignment]

    # Force `process_job` to raise on every attempt
    async def boom(_fields: Any) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(consumer, "process_job", boom)

    fields = valid_job_fields()
    entry_id = "1700000000001-0"

    # First (max_retries - 1) attempts must NOT push to DLQ yet.
    for _ in range(4):
        await consumer._handle_entry(entry_id, fields)

    fake = consumer._redis  # type: ignore[assignment]
    assert fake.dlq_entries == []
    assert fake.acked == []

    # 5th attempt reaches max_retries → DLQ + ACK + counter cleared.
    await consumer._handle_entry(entry_id, fields)

    assert len(fake.dlq_entries) == 1
    stream, payload = fake.dlq_entries[0]
    assert stream == "rag:index:jobs:dlq"
    assert payload["_dlq_original_id"] == entry_id
    assert "RuntimeError" in payload["_dlq_error"]
    assert payload["_dlq_attempts"] == "5"

    assert fake.acked == [("rag:index:jobs", "rag-indexer-group", entry_id)]
    assert dlq_module.retry_counter_key(entry_id) in fake.deleted


@pytest.mark.asyncio
async def test_handle_entry_resets_counter_on_eventual_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer = make_consumer()
    consumer._redis = FakeRedis()  # type: ignore[assignment]

    state = {"calls": 0}

    async def flaky(_fields: Any) -> None:
        state["calls"] += 1
        if state["calls"] < 3:
            raise RuntimeError("transient")
        return None

    monkeypatch.setattr(consumer, "process_job", flaky)

    entry_id = "1700000000002-0"
    fields = valid_job_fields()

    await consumer._handle_entry(entry_id, fields)
    await consumer._handle_entry(entry_id, fields)
    await consumer._handle_entry(entry_id, fields)  # success

    fake = consumer._redis  # type: ignore[assignment]
    assert fake.acked == [("rag:index:jobs", "rag-indexer-group", entry_id)]
    assert dlq_module.retry_counter_key(entry_id) in fake.deleted
    assert fake.dlq_entries == []
