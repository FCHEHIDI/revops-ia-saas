from typing import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.auth.service import verify_access_token

BYPASS_PATHS = ["/api/v1/auth", "/health"]


class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ) -> JSONResponse:
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
