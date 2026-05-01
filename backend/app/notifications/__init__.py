"""Notifications package — WebSocket pub/sub for real-time events.

Exposes:
    router   — FastAPI router with the /api/v1/ws/notifications endpoint
    manager  — singleton ConnectionManager used by other modules to broadcast
"""

from .manager import manager
from .router import router

__all__ = ["router", "manager"]
