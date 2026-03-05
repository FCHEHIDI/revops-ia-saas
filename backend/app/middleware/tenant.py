from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Scope, Receive, Send
from app.common.security import decode_access_token
from typing import Callable, Awaitable

BYPASS_PATHS = ["/api/v1/auth", "/health"]

class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable]):
        for path in BYPASS_PATHS:
            if request.url.path.startswith(path):
                return await call_next(request)
        auth = request.headers.get("Authorization")
        if not auth or not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Not authenticated")
        token = auth.split(" ", 1)[1]
        try:
            payload = decode_access_token(token)
            request.state.tenant_id = payload.get("org_id")
            request.state.user_id = payload.get("sub")
            request.state.permissions = payload.get("permissions", [])
        except Exception as e:
            raise HTTPException(status_code=401, detail="Invalid token")
        return await call_next(request)
