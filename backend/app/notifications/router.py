"""Notifications router — Feature #9 Notification Center.

REST endpoints (all under /api/v1/notifications):
  GET    /api/v1/notifications              — list (unread_only, limit, offset)
  GET    /api/v1/notifications/count        — unread count
  POST   /api/v1/notifications/{id}/read   — mark one as read
  POST   /api/v1/notifications/read-all    — mark all as read
  GET    /api/v1/notifications/stream      — SSE stream

WebSocket endpoint (existing, kept unchanged):
  GET /ws/notifications — real-time WebSocket push (per-tenant broadcast)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.notifications import service as svc
from app.notifications.schemas import (
    MarkAllReadResponse,
    NotificationCreate,
    NotificationRead,
    UnreadCountResponse,
)

from .manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()

# Heartbeat interval (seconds).  Must be < typical load-balancer idle timeout (60s).
_PING_INTERVAL = 25


@router.websocket("/ws/notifications")
async def notifications_ws(
    websocket: WebSocket,
    request: Request,
) -> None:
    """Real-time notification stream for the authenticated tenant.

    Args:
        websocket: The WebSocket connection object (injected by FastAPI).
        request: The HTTP request used to extract tenant context from middleware state.

    Raises:
        WebSocketDisconnect: Raised by Starlette when the client closes the connection.
    """
    # TenantMiddleware has already validated the JWT cookie and set scope["state"].
    tenant_id: UUID | None = getattr(request.state, "tenant_id", None)
    user_id: UUID | None = getattr(request.state, "user_id", None)

    if tenant_id is None:
        # Middleware should reject unauthenticated requests before reaching here,
        # but we defend against misconfiguration.
        await websocket.close(code=4001, reason="Not authenticated")
        return

    await manager.connect(tenant_id, websocket)

    try:
        # Send initial connected confirmation
        await websocket.send_json(
            {
                "type": "connected",
                "tenant_id": str(tenant_id),
                "user_id": str(user_id) if user_id else None,
            }
        )

        # Concurrent tasks:
        # 1. heartbeat_task — sends a ping every _PING_INTERVAL seconds
        # 2. receive_task   — receives client frames (pong, future commands)
        async def heartbeat() -> None:
            """Send periodic pings to keep the connection alive."""
            while True:
                await asyncio.sleep(_PING_INTERVAL)
                await websocket.send_json(
                    {"type": "ping", "ts": int(time.time() * 1000)}
                )

        async def receive_loop() -> None:
            """Drain incoming frames so the client doesn't get backpressured."""
            while True:
                data = await websocket.receive_json()
                if data.get("type") == "pong":
                    logger.debug(
                        "WS pong received",
                        extra={"tenant_id": str(tenant_id)},
                    )
                # Extend here with client-initiated event types if needed

        heartbeat_task = asyncio.create_task(heartbeat())
        receive_task = asyncio.create_task(receive_loop())

        # Wait until either task raises (disconnect or error)
        done, pending = await asyncio.wait(
            [heartbeat_task, receive_task],
            return_when=asyncio.FIRST_EXCEPTION,
        )

        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        logger.info(
            "WebSocket client disconnected",
            extra={"tenant_id": str(tenant_id)},
        )
    except Exception as exc:
        logger.warning(
            "WebSocket handler error: %s",
            exc,
            extra={"tenant_id": str(tenant_id)},
        )
    finally:
        manager.disconnect(tenant_id, websocket)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

_SSE_KEEPALIVE_INTERVAL = 25  # seconds between SSE keepalive comments


@router.get("/api/v1/notifications", response_model=list[NotificationRead], tags=["notifications"])
async def list_notifications(
    request: Request,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    user: object = Depends(get_current_active_user),
    db=Depends(get_db),
) -> list[NotificationRead]:
    """List notifications for the authenticated user's tenant.

    Args:
        request: Starlette request (unused, kept for middleware state).
        unread_only: If true, return only unread notifications.
        limit: Maximum rows (capped at 200 inside the service).
        offset: Pagination offset.
        user: Authenticated user ORM object (from JWT).
        db: Async database session.

    Returns:
        List of NotificationRead objects, newest first.
    """
    return await svc.list_notifications(
        db,
        tenant_id=user.org_id,
        user_id=user.id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )


@router.get("/api/v1/notifications/count", response_model=UnreadCountResponse, tags=["notifications"])
async def unread_count(
    user: object = Depends(get_current_active_user),
    db=Depends(get_db),
) -> UnreadCountResponse:
    """Return the number of unread notifications for the authenticated user.

    Args:
        user: Authenticated user ORM object.
        db: Async database session.

    Returns:
        UnreadCountResponse with the ``unread`` field.
    """
    return await svc.get_unread_count(db, tenant_id=user.org_id, user_id=user.id)


@router.post(
    "/api/v1/notifications/{notification_id}/read",
    response_model=NotificationRead,
    tags=["notifications"],
)
async def mark_notification_read(
    notification_id: UUID,
    user: object = Depends(get_current_active_user),
    db=Depends(get_db),
) -> NotificationRead:
    """Mark a single notification as read.

    Args:
        notification_id: Target notification primary key.
        user: Authenticated user ORM object.
        db: Async database session.

    Returns:
        Updated NotificationRead.

    Raises:
        HTTPException: 404 if notification not found or owned by another tenant.
    """
    notif = await svc.mark_as_read(db, notification_id, tenant_id=user.org_id)
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationRead.model_validate(notif)


@router.post(
    "/api/v1/notifications/read-all",
    response_model=MarkAllReadResponse,
    tags=["notifications"],
)
async def mark_all_notifications_read(
    user: object = Depends(get_current_active_user),
    db=Depends(get_db),
) -> MarkAllReadResponse:
    """Mark all unread notifications as read for the authenticated user.

    Args:
        user: Authenticated user ORM object.
        db: Async database session.

    Returns:
        MarkAllReadResponse with the count of rows updated.
    """
    return await svc.mark_all_as_read(db, tenant_id=user.org_id, user_id=user.id)


@router.get("/api/v1/notifications/stream", tags=["notifications"])
async def notifications_stream(
    request: Request,
    user: object = Depends(get_current_active_user),
) -> StreamingResponse:
    """Server-Sent Events stream for real-time notification push.

    The client subscribes once; the server pushes ``data: {...}`` lines
    whenever a new notification is created for the authenticated user.

    Keepalive comments ('': '') are sent every 25 seconds so the
    connection survives idle TCP timeouts.

    Args:
        request: Starlette request — used to detect client disconnect.
        user: Authenticated user ORM object.

    Returns:
        A text/event-stream StreamingResponse.
    """
    user_id: UUID = user.id

    async def event_generator() -> AsyncGenerator[str, None]:
        q = svc.sse_subscribe(user_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=_SSE_KEEPALIVE_INTERVAL)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive comment — prevents proxy idle-timeout
                    yield ": keepalive\n\n"
        finally:
            svc.sse_unsubscribe(user_id, q)
            logger.debug("SSE stream closed for user=%s", user_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

