"""Email delivery service — enqueue, worker loop, and Resend API integration.

Architecture
------------
Producer (mcp-sequences or any internal caller):
    1. Calls ``enqueue_send()`` which INSERTs an EmailSend row (status=pending)
       and pushes the row UUID to Redis list ``email:sends``.

Consumer (background worker started in app lifespan):
    2. ``run_worker()`` calls Redis BRPOP in a loop.
    3. On each item it calls ``_deliver_one()`` which:
        a. Loads the EmailSend row from DB.
        b. Appends a 1×1 tracking pixel to the HTML body.
        c. POSTs to Resend API (or logs in dev/test mode if no API key).
        d. Updates status → sent/failed + timestamps.

Tracking
--------
Open pixel: ``GET /track/{open_token}`` — returns a 1×1 transparent GIF
            and sets ``opened_at`` on the EmailSend row.
Click redirect: ``GET /click/{click_token}?url=...`` — redirects to the
                target URL and sets ``clicked_at``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_send import EmailSend

logger = logging.getLogger(__name__)

REDIS_QUEUE_KEY = "email:sends"
_BRPOP_TIMEOUT = 5
_DELIVERY_TIMEOUT = 15

# Resend API endpoint (stable v1)
_RESEND_API_URL = "https://api.resend.com/emails"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tracking_pixel_html(open_token: UUID) -> str:
    """Return a 1×1 transparent pixel IMG tag using the backend public URL.

    Args:
        open_token: The unique open-tracking UUID for this send.

    Returns:
        HTML string for the invisible tracking pixel.
    """
    base = getattr(settings, "backend_public_url", "http://localhost:18000").rstrip("/")
    return (
        f'<img src="{base}/track/{open_token}" '
        'width="1" height="1" style="display:none" alt="" />'
    )


def _inject_pixel(html: str, open_token: UUID) -> str:
    """Inject the tracking pixel before </body> or append if not found.

    Args:
        html: Original HTML email body.
        open_token: Unique open-tracking UUID.

    Returns:
        HTML with pixel injected.
    """
    pixel = _tracking_pixel_html(open_token)
    if "</body>" in html:
        return html.replace("</body>", f"{pixel}</body>", 1)
    return html + pixel


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def enqueue_send(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    to_email: str,
    subject: str,
    body_html: str,
    sequence_id: UUID | None = None,
    step_index: int | None = None,
) -> EmailSend:
    """Create a pending EmailSend row and push its ID to the Redis queue.

    Args:
        db: Async SQLAlchemy session.
        tenant_id: Owning tenant UUID.
        contact_id: CRM contact UUID.
        to_email: Recipient email address.
        subject: Email subject line.
        body_html: Fully-rendered HTML body.
        sequence_id: Optional originating sequence UUID.
        step_index: Optional step index within the sequence.

    Returns:
        The newly created ``EmailSend`` ORM instance (status=pending).
    """
    send = EmailSend(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        sequence_id=sequence_id,
        contact_id=contact_id,
        step_index=step_index,
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        open_token=uuid.uuid4(),
        click_token=uuid.uuid4(),
        status="pending",
    )
    db.add(send)
    await db.commit()
    await db.refresh(send)

    # Push to Redis queue for async delivery
    redis_url = settings.redis_url
    if redis_url:
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            r = aioredis.from_url(redis_url, decode_responses=True)
            await r.lpush(REDIS_QUEUE_KEY, str(send.id))
            await r.aclose()
        except Exception as exc:
            logger.warning("email: failed to push to Redis queue: %s", exc)
    else:
        logger.debug("email: no Redis URL configured — email %s will not be delivered", send.id)

    return send


async def _deliver_one(db: AsyncSession, send_id: UUID) -> None:
    """Fetch one pending send, call Resend, update status.

    Args:
        db: Async SQLAlchemy session.
        send_id: UUID of the EmailSend row to process.
    """
    row = await db.get(EmailSend, send_id)
    if row is None:
        logger.warning("email: send %s not found in DB — skipping", send_id)
        return
    if row.status != "pending":
        logger.debug("email: send %s already in status=%s — skipping", send_id, row.status)
        return

    html_with_pixel = _inject_pixel(row.body_html, row.open_token)

    resend_key = getattr(settings, "resend_api_key", "")
    email_from = getattr(settings, "email_from", "RevOps IA <noreply@revops.local>")

    if not resend_key:
        # Dev/test mode: log the email, mark as sent
        logger.info(
            "email [DEV] to=%s subject=%s (no RESEND_API_KEY — not delivered)",
            row.to_email,
            row.subject,
        )
        await db.execute(
            update(EmailSend)
            .where(EmailSend.id == send_id)
            .values(
                status="sent",
                sent_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        return

    payload = {
        "from": email_from,
        "to": [row.to_email],
        "subject": row.subject,
        "html": html_with_pixel,
    }

    try:
        async with httpx.AsyncClient(timeout=_DELIVERY_TIMEOUT) as client:
            resp = await client.post(
                _RESEND_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {resend_key}"},
            )
        if resp.status_code in (200, 201):
            await db.execute(
                update(EmailSend)
                .where(EmailSend.id == send_id)
                .values(
                    status="sent",
                    sent_at=datetime.now(timezone.utc),
                )
            )
            logger.info("email: sent %s to %s via Resend", send_id, row.to_email)
        else:
            err = resp.text[:500]
            logger.error("email: Resend error %s for %s: %s", resp.status_code, send_id, err)
            await db.execute(
                update(EmailSend)
                .where(EmailSend.id == send_id)
                .values(status="failed", error_message=err)
            )
    except Exception as exc:
        logger.error("email: delivery exception for %s: %s", send_id, exc)
        await db.execute(
            update(EmailSend)
            .where(EmailSend.id == send_id)
            .values(status="failed", error_message=str(exc)[:500])
        )
    await db.commit()


async def run_worker(db_factory: Any) -> None:  # noqa: ANN401
    """Long-running Redis BRPOP worker that delivers queued emails.

    Mirrors the pattern used by the webhooks worker.

    Args:
        db_factory: Async context manager that yields an ``AsyncSession``.
    """
    redis_url = settings.redis_url
    if not redis_url:
        logger.info("email worker: no REDIS_URL — worker is a no-op")
        # Stay alive so the task doesn't crash the lifespan.
        while True:
            await asyncio.sleep(60)

    import redis.asyncio as aioredis  # type: ignore[import]

    r = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("email worker: started, listening on %s", REDIS_QUEUE_KEY)

    while True:
        try:
            item = await r.brpop(REDIS_QUEUE_KEY, timeout=_BRPOP_TIMEOUT)
            if item is None:
                continue
            _, send_id_str = item
            send_id = UUID(send_id_str)
            async with db_factory() as db:
                await _deliver_one(db, send_id)
        except asyncio.CancelledError:
            logger.info("email worker: shutting down")
            await r.aclose()
            return
        except Exception as exc:
            logger.error("email worker: unhandled error: %s", exc)
            await asyncio.sleep(1)


async def mark_opened(db: AsyncSession, open_token: UUID) -> bool:
    """Set opened_at on the matching EmailSend row if not already set.

    Args:
        db: Async SQLAlchemy session.
        open_token: The open-tracking token from the pixel URL.

    Returns:
        True if the row was found and updated, False otherwise.
    """
    result = await db.execute(
        select(EmailSend).where(EmailSend.open_token == open_token)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    if row.opened_at is None:
        row.opened_at = datetime.now(timezone.utc)
        await db.commit()
        return True
    return False  # already opened


async def mark_clicked(db: AsyncSession, click_token: UUID) -> str | None:
    """Set clicked_at on the matching EmailSend row if not already set.

    Args:
        db: Async SQLAlchemy session.
        click_token: The click-tracking token from the redirect URL.

    Returns:
        The ``to_email`` of the matched row (for logging), or None if not found.
    """
    result = await db.execute(
        select(EmailSend).where(EmailSend.click_token == click_token)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    if row.clicked_at is None:
        row.clicked_at = datetime.now(timezone.utc)
        await db.commit()
    return row.to_email
