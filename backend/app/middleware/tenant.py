from typing import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.auth.service import verify_access_token

BYPASS_PATHS = ["/api/v1/auth", "/health"]
INTERNAL_API_PREFIX = "/internal/v1/"


class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ) -> JSONResponse:
        # Internal API fast-path (skip cookie/JWT, use headers + internal key)
        if request.url.path.startswith(INTERNAL_API_PREFIX):
            from app.config import settings
            import secrets
            from uuid import UUID
            api_key = request.headers.get("x-internal-api-key")
            tenant = request.headers.get("x-tenant-id")
            user = request.headers.get("x-user-id")
            if not api_key or not secrets.compare_digest(api_key, getattr(settings, "internal_api_key", "")):
                return JSONResponse(status_code=401, content={"detail": "Invalid internal API key"})
            try:
                request.state.tenant_id = UUID(tenant)
            except Exception:
                return JSONResponse(status_code=400, content={"detail": "Invalid X-Tenant-ID (must be UUID)"})
            try:
                request.state.user_id = UUID(user) if user else None
            except Exception:
                request.state.user_id = None
            return await call_next(request)

        for path in BYPASS_PATHS:
            if request.url.path.startswith(path):
                return await call_next(request)  # type: ignore[return-value]

        token = request.cookies.get("access_token")
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )

        try:
            payload = verify_access_token(token)
            request.state.tenant_id = payload.tenant_id
            request.state.user_id = payload.sub
        except (
            Exception
        ):  # nosec B110 — HTTPException cannot propagate from ASGI middleware
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"},
            )

        return await call_next(request)  # type: ignore[return-value]
