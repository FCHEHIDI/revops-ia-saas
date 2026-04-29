import secrets
from uuid import UUID

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth.service import verify_access_token

BYPASS_PATHS = ["/api/v1/auth", "/health", "/internal/sessions", "/internal/llm"]
# Routes under /internal/v1/ use the internal-API-key fast-path (sets tenant context).
INTERNAL_API_PREFIX = "/internal/v1/"


class TenantMiddleware:
    """Pure ASGI middleware for tenant context injection.

    Replaces BaseHTTPMiddleware to avoid asyncpg
    "cannot perform operation: another operation is in progress" errors that
    occur when BaseHTTPMiddleware runs call_next in a background task while an
    asyncpg connection is already in use.

    IMPORTANT: scope["state"] must be a plain dict (not a starlette.State object).
    Starlette 0.38+ does State(scope["state"]) internally — passing a State instance
    would make _state point to another State, breaking subscript access.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Starlette 0.38+: scope["state"] must be a plain dict so that
        # HTTPConnection.state creates State(scope["state"]) with a proper _state dict.
        scope.setdefault("state", {})

        path: str = scope.get("path", "")
        raw_headers: dict[bytes, bytes] = {
            k.lower(): v for k, v in scope.get("headers", [])
        }

        # ── Internal API fast-path ──────────────────────────────────────────
        if path.startswith(INTERNAL_API_PREFIX):
            from app.config import settings

            api_key = raw_headers.get(b"x-internal-api-key", b"").decode()
            tenant_raw = raw_headers.get(b"x-tenant-id", b"").decode()
            user_raw = raw_headers.get(b"x-user-id", b"").decode()

            expected = getattr(settings, "internal_api_key", "")
            if not api_key or not expected or not secrets.compare_digest(api_key, expected):
                resp = JSONResponse(status_code=401, content={"detail": "Invalid internal API key"})
                await resp(scope, receive, send)
                return

            try:
                scope["state"]["tenant_id"] = UUID(tenant_raw)
            except Exception:
                resp = JSONResponse(status_code=400, content={"detail": "Invalid X-Tenant-ID (must be UUID)"})
                await resp(scope, receive, send)
                return

            try:
                scope["state"]["user_id"] = UUID(user_raw) if user_raw else None
            except Exception:
                scope["state"]["user_id"] = None

            await self.app(scope, receive, send)
            return

        # ── Bypass paths ────────────────────────────────────────────────────
        for bypass in BYPASS_PATHS:
            if path.startswith(bypass):
                await self.app(scope, receive, send)
                return

        # ── JWT cookie auth ─────────────────────────────────────────────────
        cookie_header = raw_headers.get(b"cookie", b"").decode("utf-8", errors="replace")
        token: str | None = None
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("access_token="):
                token = part[len("access_token="):]
                break

        if not token:
            resp = JSONResponse(status_code=401, content={"detail": "Not authenticated"})
            await resp(scope, receive, send)
            return

        try:
            payload = verify_access_token(token)
            scope["state"]["tenant_id"] = payload.tenant_id
            scope["state"]["user_id"] = payload.sub
        except Exception:  # nosec B110 — catch all — middleware cannot propagate
            resp = JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})
            await resp(scope, receive, send)
            return

        await self.app(scope, receive, send)
