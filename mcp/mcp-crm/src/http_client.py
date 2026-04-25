from __future__ import annotations

import uuid
import logging

import httpx

from config import Settings
from errors import CrmMcpError

logger = logging.getLogger(__name__)


def build_client(settings: Settings) -> httpx.AsyncClient:
    """
    Builds the shared httpx AsyncClient for backend calls.
    Created once at server startup via FastAPI lifespan.
    """
    return httpx.AsyncClient(
        base_url=settings.BACKEND_URL,
        timeout=httpx.Timeout(
            connect=5.0,
            read=settings.HTTP_TIMEOUT,
            write=5.0,
            pool=5.0,
        ),
        headers={
            "X-Internal-API-Key": settings.INTERNAL_API_KEY,
            "Content-Type": "application/json",
        },
    )


async def call_backend(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    tenant_id: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
) -> dict:
    """
    Executes an HTTP request to the backend /internal/v1/crm/* endpoints.

    Injects:
      - X-Tenant-ID: {tenant_id}
      - X-Request-ID: freshly generated UUID4 (for distributed tracing)

    Maps HTTP error codes to CrmMcpError:
      401  → UNAUTHORIZED
      403  → FORBIDDEN
      404  → NOT_FOUND
      409  → CONFLICT
      422  → VALIDATION_ERROR
      5xx  → BACKEND_UNAVAILABLE
      Timeout / ConnectError → BACKEND_UNAVAILABLE
    """
    request_id = str(uuid.uuid4())
    headers = {
        "X-Tenant-ID": tenant_id,
        "X-Request-ID": request_id,
    }

    logger.debug(
        "Backend call: %s %s tenant=%s request_id=%s",
        method.upper(),
        path,
        tenant_id,
        request_id,
    )

    try:
        response = await client.request(
            method=method.upper(),
            url=path,
            params=params,
            json=json,
            headers=headers,
        )
    except httpx.TimeoutException as exc:
        logger.warning("Backend timeout: %s %s — %s", method, path, exc)
        raise CrmMcpError(
            "BACKEND_UNAVAILABLE",
            f"Backend request timed out: {method.upper()} {path}",
        ) from exc
    except httpx.ConnectError as exc:
        logger.warning("Backend connect error: %s %s — %s", method, path, exc)
        raise CrmMcpError(
            "BACKEND_UNAVAILABLE",
            f"Could not connect to backend: {method.upper()} {path}",
        ) from exc

    _raise_for_status(response, path)

    return response.json()


def _raise_for_status(response: httpx.Response, path: str) -> None:
    """Maps backend HTTP error codes to CrmMcpError."""
    status = response.status_code

    if status < 400:
        return

    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text

    if status == 401:
        raise CrmMcpError("UNAUTHORIZED", f"Unauthorized: {detail}")
    elif status == 403:
        raise CrmMcpError("FORBIDDEN", f"Forbidden: {detail}")
    elif status == 404:
        raise CrmMcpError("NOT_FOUND", f"Resource not found: {detail}")
    elif status == 409:
        raise CrmMcpError("CONFLICT", f"Conflict: {detail}")
    elif status == 422:
        raise CrmMcpError("VALIDATION_ERROR", f"Validation error: {detail}")
    elif status >= 500:
        logger.error("Backend server error %d on %s: %s", status, path, detail)
        raise CrmMcpError(
            "BACKEND_UNAVAILABLE",
            f"Backend returned {status}: {detail}",
        )
    else:
        raise CrmMcpError(
            "BACKEND_UNAVAILABLE",
            f"Unexpected HTTP {status} from backend: {detail}",
        )
