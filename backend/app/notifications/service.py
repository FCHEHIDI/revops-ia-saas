"""Business logic for the Notification Center (Feature #9).

Responsibilities
----------------
1. CRUD helpers (create, list, count unread, mark read) operating on the
   ``notifications`` DB table.
2. In-process SSE pub/sub: callers subscribe to a per-user asyncio.Queue;
   ``create_notification`` pushes to all matching queues and to the
   existing WebSocket manager.

SSE pub/sub is intentionally in-process (no Redis required for MVP).
In production you would replace ``_sse_queues`` with a Redis pub/sub channel.
"""

from __future__ import annotations

import asyncio
import logging
from app.common.utils import utcnow
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.notifications.schemas import (
    MarkAllReadResponse,
    NotificationCreate,
    NotificationRead,
    UnreadCountResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process SSE pub/sub
# ---------------------------------------------------------------------------

# Maps user_id → list of asyncio.Queue instances (one per active SSE connection).
_sse_queues: dict[UUID, list[asyncio.Queue]] = {}


def sse_subscribe(user_id: UUID) -> asyncio.Queue:
    """Register a new SSE queue for *user_id* and return it.

    Args:
        user_id: The user subscribing to the SSE stream.

    Returns:
        An asyncio.Queue that will receive notification dicts.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_queues.setdefault(user_id, []).append(q)
    logger.debug("SSE subscribe user=%s queues=%d", user_id, len(_sse_queues[user_id]))
    return q


def sse_unsubscribe(user_id: UUID, q: asyncio.Queue) -> None:
    """Remove *q* from the subscriber list for *user_id*.

    Args:
        user_id: The user whose queue is being removed.
        q: The specific queue to remove.
    """
    qs = _sse_queues.get(user_id, [])
    if q in qs:
        qs.remove(q)
    if not qs and user_id in _sse_queues:
        del _sse_queues[user_id]
    logger.debug("SSE unsubscribe user=%s", user_id)


def _push_sse(user_id: UUID, payload: dict[str, Any]) -> None:
    """Push *payload* to all active SSE queues for *user_id*.

    Silently drops the event if a queue is full (back-pressure).

    Args:
        user_id: Target user.
        payload: JSON-serialisable dict to push.
    """
    for q in list(_sse_queues.get(user_id, [])):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for user=%s — event dropped", user_id)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_notification(
    db: AsyncSession,
    data: NotificationCreate,
    *,
    push: bool = True,
) -> Notification:
    """Persist a new notification and push it to live connections.

    Args:
        db: Async database session.
        data: Validated creation payload.
        push: If True, broadcast via WebSocket manager and SSE queues.

    Returns:
        The newly created Notification ORM instance.
    """
    notif = Notification(
        id=uuid4(),
        tenant_id=data.tenant_id,
        user_id=data.user_id,
        type=data.type,
        title=data.title,
        body=data.body,
        data=data.data,
    )
    db.add(notif)
    await db.flush()
    await db.refresh(notif)

    if push:
        # WebSocket broadcast to every connected client in the tenant
        try:
            from app.notifications.manager import manager  # avoid circular import

            ws_payload: dict[str, Any] = {
                "type": "notification",
                "id": str(notif.id),
                "notification_type": notif.type,
                "title": notif.title,
                "body": notif.body,
                "created_at": notif.created_at.isoformat()
                if notif.created_at
                else None,
            }
            asyncio.ensure_future(manager.broadcast(data.tenant_id, ws_payload))
        except Exception as exc:  # noqa: BLE001
            logger.warning("WebSocket broadcast failed: %s", exc)

        # SSE push to specific user (if targeting a user)
        if data.user_id:
            sse_payload: dict[str, Any] = {
                "type": "notification",
                "id": str(notif.id),
                "notification_type": notif.type,
                "title": notif.title,
                "body": notif.body,
                "data": notif.data,
                "created_at": notif.created_at.isoformat()
                if notif.created_at
                else None,
            }
            _push_sse(data.user_id, sse_payload)

    logger.info(
        "Notification created type=%s tenant=%s user=%s",
        notif.type,
        notif.tenant_id,
        notif.user_id,
    )
    return notif


async def list_notifications(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: Optional[UUID] = None,
    *,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[NotificationRead]:
    """Return notifications for *tenant_id*, optionally filtered.

    Rows targeted at *user_id* OR at the whole tenant (user_id IS NULL)
    are both returned when *user_id* is given.

    Args:
        db: Async database session.
        tenant_id: Owning tenant.
        user_id: Filter to rows for this user or tenant-wide.  None = all rows.
        unread_only: If True, exclude already-read notifications.
        limit: Maximum rows to return (capped at 200).
        offset: Pagination offset.

    Returns:
        List of NotificationRead Pydantic objects.
    """
    q = select(Notification).where(Notification.tenant_id == tenant_id)
    if user_id is not None:
        q = q.where(
            or_(Notification.user_id == user_id, Notification.user_id.is_(None))
        )
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    q = (
        q.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
    )
    rows = await db.execute(q)
    return [NotificationRead.model_validate(n) for n in rows.scalars().all()]


async def get_unread_count(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: Optional[UUID] = None,
) -> UnreadCountResponse:
    """Return the number of unread notifications for the given scope.

    Args:
        db: Async database session.
        tenant_id: Owning tenant.
        user_id: If given, count rows for this user or tenant-wide.

    Returns:
        UnreadCountResponse with the unread count.
    """
    q = select(func.count()).select_from(Notification).where(
        Notification.tenant_id == tenant_id,
        Notification.read_at.is_(None),
    )
    if user_id is not None:
        q = q.where(
            or_(Notification.user_id == user_id, Notification.user_id.is_(None))
        )
    count = (await db.execute(q)).scalar_one()
    return UnreadCountResponse(unread=count)


async def mark_as_read(
    db: AsyncSession,
    notification_id: UUID,
    tenant_id: UUID,
) -> Optional[Notification]:
    """Mark a single notification as read (idempotent).

    Args:
        db: Async database session.
        notification_id: Target notification primary key.
        tenant_id: Must match the notification's tenant (RLS guard).

    Returns:
        Updated Notification, or None if not found / wrong tenant.
    """
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == tenant_id,
        )
    )
    notif = result.scalar_one_or_none()
    if notif is None:
        return None
    if notif.read_at is None:
        notif.read_at = utcnow()
        await db.commit()
        await db.refresh(notif)
    return notif


async def mark_all_as_read(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: Optional[UUID] = None,
) -> MarkAllReadResponse:
    """Mark all unread notifications as read for the given scope.

    Args:
        db: Async database session.
        tenant_id: Owning tenant.
        user_id: If given, limit scope to this user's + tenant-wide rows.

    Returns:
        MarkAllReadResponse with the number of rows updated.
    """
    stmt = (
        update(Notification)
        .where(
            Notification.tenant_id == tenant_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=utcnow())
    )
    if user_id is not None:
        stmt = stmt.where(
            or_(Notification.user_id == user_id, Notification.user_id.is_(None))
        )
    result = await db.execute(stmt)
    await db.commit()
    return MarkAllReadResponse(updated=result.rowcount)
