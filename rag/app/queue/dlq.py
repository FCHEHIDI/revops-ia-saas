"""Dead Letter Queue helpers for the CRM indexing stream.

When a job fails to be processed after `crm_index_max_retries` attempts, we
push it onto the DLQ stream `rag:index:jobs:dlq` with the original payload
plus diagnostic metadata, then ACK the original entry to release it from the
pending entries list.
"""

from __future__ import annotations

import logging
import time
from typing import Mapping

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


async def push_to_dlq(
    redis: aioredis.Redis,
    original_id: str,
    payload: Mapping[str, str],
    error: str,
    attempts: int,
) -> str:
    """Push a failed job onto the DLQ stream and return the new entry id.

    Parameters
    ----------
    redis: connected `redis.asyncio.Redis` instance.
    original_id: the entry id from the source stream (e.g. ``1700000000000-0``).
    payload: the original job fields (already decoded as ``str -> str``).
    error: short human-readable error label (exception class + message).
    attempts: number of attempts made before DLQ.
    """

    enriched = {
        **payload,
        "_dlq_original_id": original_id,
        "_dlq_error": error,
        "_dlq_attempts": str(attempts),
        "_dlq_pushed_at": str(int(time.time())),
    }
    new_id = await redis.xadd(settings.crm_index_dlq, enriched)
    logger.warning(
        "DLQ push: original_id=%s attempts=%d error=%s -> dlq_id=%s",
        original_id,
        attempts,
        error,
        new_id,
    )
    return new_id


def retry_counter_key(original_id: str) -> str:
    """Redis key used to count attempts for a given stream entry id."""
    return f"rag:index:retries:{original_id}"
