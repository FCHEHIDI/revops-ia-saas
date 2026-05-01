"""In-memory WebSocket connection manager.

Each tenant maintains its own set of active WebSocket connections.
The manager is a singleton imported by the router and any service
that needs to push real-time events (CRM, orchestrator callback, etc.).

Thread-safety note:
    FastAPI/Starlette runs on a single-threaded asyncio event loop so
    there is no concurrent mutation risk.  All public methods are sync
    (no I/O) and use `asyncio.ensure_future` / `await` at the call-site.
"""

import asyncio
import logging
from typing import Any
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections grouped by tenant_id.

    Args:
        None

    Example:
        manager = ConnectionManager()
        await manager.connect(tenant_id, websocket)
        await manager.broadcast(tenant_id, {"type": "ping"})
        manager.disconnect(tenant_id, websocket)
    """

    def __init__(self) -> None:
        # Maps tenant_id → set of active WebSocket connections
        self._connections: dict[UUID, set[WebSocket]] = {}

    async def connect(self, tenant_id: UUID, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection.

        Args:
            tenant_id: The tenant owning this connection.
            websocket: The WebSocket instance to register.
        """
        await websocket.accept()
        self._connections.setdefault(tenant_id, set()).add(websocket)
        logger.info(
            "WebSocket connected",
            extra={
                "tenant_id": str(tenant_id),
                "active": len(self._connections[tenant_id]),
            },
        )

    def disconnect(self, tenant_id: UUID, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active set.

        Args:
            tenant_id: The tenant owning this connection.
            websocket: The WebSocket instance to remove.
        """
        connections = self._connections.get(tenant_id)
        if connections:
            connections.discard(websocket)
            if not connections:
                del self._connections[tenant_id]
        logger.info(
            "WebSocket disconnected",
            extra={"tenant_id": str(tenant_id)},
        )

    async def broadcast(self, tenant_id: UUID, payload: dict[str, Any]) -> None:
        """Send a JSON payload to all connections for a given tenant.

        Dead connections are silently removed.

        Args:
            tenant_id: Target tenant.
            payload: Dict serialisable to JSON, e.g. {"type": "crm:contact_created", "data": {...}}.
        """
        connections = self._connections.get(tenant_id, set())
        if not connections:
            return

        dead: list[WebSocket] = []
        for ws in list(connections):
            try:
                await ws.send_json(payload)
            except Exception as exc:  # noqa: BLE001
                logger.debug("WS send failed, removing dead connection: %s", exc)
                dead.append(ws)

        for ws in dead:
            self.disconnect(tenant_id, ws)

    async def broadcast_all(self, payload: dict[str, Any]) -> None:
        """Broadcast to every connected tenant (admin/system events).

        Args:
            payload: Dict serialisable to JSON.
        """
        tasks = [
            self.broadcast(tenant_id, payload)
            for tenant_id in list(self._connections)
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def connection_count(self, tenant_id: UUID) -> int:
        """Return the number of active connections for a tenant.

        Args:
            tenant_id: The tenant to query.

        Returns:
            Number of active WebSocket connections.
        """
        return len(self._connections.get(tenant_id, set()))


# Singleton — import this instance everywhere
manager = ConnectionManager()
