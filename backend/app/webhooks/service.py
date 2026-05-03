"""Webhook service — CRUD, event publishing, and delivery worker.

The delivery pipeline uses a Redis List as a simple queue:
  - Producers (CRM service) call ``publish_event`` which does LPUSH.
  - The background worker (``run_worker``) does BRPOP + dispatches HTTP POST.

HMAC-SHA256 signature is added as ``X-Revops-Signature: sha256=<hex>`` on
every delivery so receivers can verify authenticity.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from app.common.utils import utcnow
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.webhook import WebhookDeliveryLog, WebhookEndpoint

logger = logging.getLogger(__name__)

REDIS_QUEUE_KEY = "webhooks:events"
# Maximum time (seconds) to wait for delivery before aborting.
_DELIVERY_TIMEOUT = 10
# How long a worker blocks waiting for a Redis item (seconds).
_BRPOP_TIMEOUT = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_secret() -> str:
    """Generate a 32-byte (64 hex chars) HMAC secret for a new endpoint.

    Returns:
        A hex-encoded 64-character random string.
    """
    return secrets.token_hex(32)


def _sign_payload(secret: str, raw_body: bytes) -> str:
    """Compute HMAC-SHA256 of ``raw_body`` using ``secret``.

    Args:
        secret: Hex-encoded 64-char webhook secret.
        raw_body: The serialised JSON payload as bytes.

    Returns:
        Signature string in the form ``sha256=<hex_digest>``.
    """
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_endpoint(
    db: AsyncSession,
    tenant_id: UUID,
    event_type: str,
    url: str,
) -> WebhookEndpoint:
    """Create a new webhook endpoint subscription.

    Args:
        db: Async SQLAlchemy session.
        tenant_id: Tenant that owns the endpoint.
        event_type: RevOps event to subscribe to.
        url: HTTPS URL to deliver events to.

    Returns:
        The newly created ``WebhookEndpoint`` ORM instance (includes secret).
    """
    endpoint = WebhookEndpoint(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        event_type=event_type,
        url=url,
        secret=_generate_secret(),
        active=True,
    )
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return endpoint


async def list_endpoints(db: AsyncSession, tenant_id: UUID) -> list[WebhookEndpoint]:
    """List all webhook endpoints for a tenant.

    Args:
        db: Async SQLAlchemy session.
        tenant_id: Tenant UUID to scope the query.

    Returns:
        List of ``WebhookEndpoint`` instances.
    """
    result = await db.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.tenant_id == tenant_id)
        .order_by(WebhookEndpoint.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_endpoint(db: AsyncSession, endpoint_id: UUID, tenant_id: UUID) -> bool:
    """Delete (revoke) a webhook endpoint.

    Args:
        db: Async SQLAlchemy session.
        endpoint_id: UUID of the endpoint to delete.
        tenant_id: Tenant UUID used to enforce ownership.

    Returns:
        True if the endpoint was found and deleted, False otherwise.
    """
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id,
            WebhookEndpoint.tenant_id == tenant_id,
        )
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        return False
    await db.delete(endpoint)
    await db.commit()
    return True


async def list_logs(
    db: AsyncSession,
    endpoint_id: UUID,
    tenant_id: UUID,
    limit: int = 50,
) -> list[WebhookDeliveryLog]:
    """Retrieve delivery logs for one endpoint.

    Args:
        db: Async SQLAlchemy session.
        endpoint_id: UUID of the webhook endpoint.
        tenant_id: Tenant UUID used to enforce ownership.
        limit: Maximum number of log entries to return (default 50).

    Returns:
        List of ``WebhookDeliveryLog`` instances, newest first.
    """
    result = await db.execute(
        select(WebhookDeliveryLog)
        .where(
            WebhookDeliveryLog.endpoint_id == endpoint_id,
            WebhookDeliveryLog.tenant_id == tenant_id,
        )
        .order_by(WebhookDeliveryLog.delivered_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Event publishing (enqueue)
# ---------------------------------------------------------------------------


async def publish_event(tenant_id: UUID, event_type: str, payload: dict[str, Any]) -> None:
    """Enqueue a webhook event for background delivery.

    Silently skips if Redis is unavailable (fail-open). Producers must not
    block on this call; any exception is caught and logged.

    Args:
        tenant_id: Tenant UUID that triggered the event.
        event_type: RevOps event type (e.g. ``"deal.won"``).
        payload: Arbitrary dict with event data (will be JSON-serialised).
    """
    try:
        import redis.asyncio as aioredis  # lazy import — avoids hard dep at module load
    except ImportError:
        logger.debug("webhooks: redis package not available, skipping event publish")
        return

    redis_url = settings.redis_url
    if not redis_url:
        return

    message = json.dumps(
        {
            "tenant_id": str(tenant_id),
            "event_type": event_type,
            "payload": payload,
            "ts": utcnow().isoformat(),
        }
    )
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        await r.lpush(REDIS_QUEUE_KEY, message)
        await r.aclose()
    except Exception as exc:  # pragma: no cover — Redis down is expected in CI
        logger.warning("webhooks: failed to enqueue event %s: %s", event_type, exc)


# ---------------------------------------------------------------------------
# Delivery worker (background task)
# ---------------------------------------------------------------------------


async def _deliver_one(
    db_factory: Any,
    tenant_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    ts: str,
) -> None:
    """Fetch matching endpoints and POST the event to each one.

    Args:
        db_factory: Async context manager that yields an ``AsyncSession``.
        tenant_id: Tenant UUID that triggered the event.
        event_type: Event type string.
        payload: Original event payload dict.
        ts: ISO-8601 timestamp of the event.
    """
    async with db_factory() as db:
        result = await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.tenant_id == tenant_id,
                WebhookEndpoint.event_type == event_type,
                WebhookEndpoint.active.is_(True),
            )
        )
        endpoints: list[WebhookEndpoint] = list(result.scalars().all())

    if not endpoints:
        return

    body: dict[str, Any] = {
        "event": event_type,
        "tenant_id": str(tenant_id),
        "ts": ts,
        "data": payload,
    }
    raw_body = json.dumps(body, default=str).encode()

    async with httpx.AsyncClient(timeout=_DELIVERY_TIMEOUT) as client:
        for ep in endpoints:
            signature = _sign_payload(ep.secret, raw_body)
            status_code: int | None = None
            error: str | None = None
            try:
                resp = await client.post(
                    ep.url,
                    content=raw_body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Revops-Signature": signature,
                        "X-Revops-Event": event_type,
                    },
                )
                status_code = resp.status_code
                if not resp.is_success:
                    error = f"Non-2xx response: {resp.status_code}"
            except Exception as exc:
                error = str(exc)
                logger.warning(
                    "webhooks: delivery failed for endpoint %s: %s", ep.id, error
                )

            log = WebhookDeliveryLog(
                id=uuid.uuid4(),
                endpoint_id=ep.id,
                tenant_id=tenant_id,
                event_type=event_type,
                payload=body,
                response_status=status_code,
                error=error,
                delivered_at=utcnow(),
            )
            async with db_factory() as db:
                db.add(log)
                await db.commit()


async def run_worker(db_factory: Any) -> None:
    """Long-running background task that pops and delivers webhook events.

    Runs until the task is cancelled (e.g. on FastAPI shutdown). Uses
    BRPOP with a timeout so the loop can be interrupted cleanly.

    Args:
        db_factory: Callable that returns an async context manager yielding
            an ``AsyncSession`` (typically ``get_db`` wrapped with
            ``contextlib.asynccontextmanager``).
    """
    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning("webhooks: redis package missing, worker not started")
        return

    redis_url = settings.redis_url
    if not redis_url:
        logger.info("webhooks: no REDIS_URL configured, worker not started")
        return

    r = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("webhooks: worker started, listening on %s", REDIS_QUEUE_KEY)
    try:
        while True:
            item = await r.brpop(REDIS_QUEUE_KEY, timeout=_BRPOP_TIMEOUT)
            if item is None:
                continue
            _, raw = item
            try:
                msg = json.loads(raw)
                await _deliver_one(
                    db_factory=db_factory,
                    tenant_id=UUID(msg["tenant_id"]),
                    event_type=msg["event_type"],
                    payload=msg["payload"],
                    ts=msg["ts"],
                )
            except Exception as exc:
                logger.error("webhooks: worker error processing message: %s", exc)
    except asyncio.CancelledError:
        logger.info("webhooks: worker shutting down")
    finally:
        await r.aclose()
