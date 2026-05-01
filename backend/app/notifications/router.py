"""WebSocket router for real-time notifications.

Endpoint: GET /api/v1/ws/notifications
  Upgrades the HTTP connection to WebSocket.
  Auth: JWT `access_token` cookie (enforced by TenantMiddleware).

Protocol (JSON frames):
  Server → Client:
    {"type": "connected",  "tenant_id": "<uuid>"}
    {"type": "ping",       "ts": <epoch_ms>}
    {"type": "crm:contact_created", "data": {...}}
    {"type": "crm:contact_updated", "data": {...}}
    {"type": "crm:contact_deleted", "data": {"id": "<uuid>"}}

  Client → Server:
    {"type": "pong"} — heartbeat reply (optional, connection kept regardless)

The endpoint keeps the connection alive with periodic pings every 25 seconds.
When the client disconnects the handler exits cleanly.
"""

import asyncio
import logging
import time
from uuid import UUID

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

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
