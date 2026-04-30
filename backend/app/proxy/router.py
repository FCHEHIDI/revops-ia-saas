"""Proxy routes — forwards MCP tool calls to mcp-billing, mcp-analytics, mcp-sequences.

All routes require a valid JWT session (tenant_id + user_id injected by TenantMiddleware).
The internal API key is forwarded automatically via the X-Internal-API-Key header.

Route convention:
  POST /api/v1/billing/call          → POST http://<MCP_BILLING_URL>/mcp/call
  POST /api/v1/analytics/call        → POST http://<MCP_ANALYTICS_URL>/mcp/call
  POST /api/v1/sequences/call        → POST http://<MCP_SEQUENCES_URL>/mcp/call
  GET  /api/v1/{service}/health      → GET  http://<MCP_URL>/health

Request body (JSON):
  {
    "tool": "<tool_name>",
    "params": { ... }   // tenant_id / user_id are injected automatically from the JWT
  }
"""

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Internal base URLs — can be overridden via env vars
# ---------------------------------------------------------------------------

_BILLING_URL = os.getenv("MCP_BILLING_URL", "http://localhost:19002")
_ANALYTICS_URL = os.getenv("MCP_ANALYTICS_URL", "http://localhost:19003")
_SEQUENCES_URL = os.getenv("MCP_SEQUENCES_URL", "http://localhost:19004")
_FILESYSTEM_URL = os.getenv("MCP_FILESYSTEM_URL", "http://localhost:19005")

_MCP_URLS: dict[str, str] = {
    "billing": _BILLING_URL,
    "analytics": _ANALYTICS_URL,
    "sequences": _SEQUENCES_URL,
    "filesystem": _FILESYSTEM_URL,
}

# NOTE: _INTERNAL_HEADERS is built lazily via _get_internal_headers() so that
# settings.mcp_inter_service_secret (loaded from .env by Pydantic) is used.


def _get_internal_headers() -> dict[str, str]:
    """Return headers including the MCP inter-service key from settings."""
    return {
        "X-Internal-API-Key": settings.mcp_inter_service_secret,
    }



_CLIENT: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient, creating it on first call.

    Returns:
        The shared httpx.AsyncClient instance.
    """
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    return _CLIENT


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class McpCallRequest(BaseModel):
    """Body for a proxied MCP tool call.

    Attributes:
        tool: Name of the MCP tool to invoke.
        params: Parameters forwarded to the MCP service.
            ``tenant_id`` and ``user_id`` are always injected from the JWT,
            overriding any caller-supplied values.
    """

    tool: str
    params: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


async def _proxy_call(
    service: str,
    tool: str,
    params: dict[str, Any],
) -> Any:
    """Forward a tool call to the target MCP service.

    Args:
        service: One of ``billing``, ``analytics``, ``sequences``.
        tool: MCP tool name.
        params: Tool parameters, already enriched with tenant/user context.

    Returns:
        The JSON response body from the MCP service.

    Raises:
        HTTPException: 502 if the MCP service is unreachable or returns an error.
        HTTPException: 503 if the service name is unknown.
    """
    base_url = _MCP_URLS.get(service)
    if base_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unknown service: {service}",
        )

    url = f"{base_url}/mcp/call"
    payload = {"tool": tool, "params": params}

    try:
        resp = await _get_client().post(url, json=payload, headers=_get_internal_headers())
    except httpx.RequestError as exc:
        logger.error("MCP proxy error [%s] %s: %s", service, tool, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP service '{service}' unreachable",
        ) from exc

    if resp.status_code >= 500:
        logger.error(
            "MCP upstream error [%s] %s → HTTP %d: %s",
            service,
            tool,
            resp.status_code,
            resp.text[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP service '{service}' returned {resp.status_code}",
        )

    return resp.json()


async def _proxy_health(service: str) -> Any:
    """Forward a health-check to the target MCP service.

    Args:
        service: One of ``billing``, ``analytics``, ``sequences``.

    Returns:
        The JSON health response from the MCP service.

    Raises:
        HTTPException: 502 if the MCP service is unreachable.
    """
    base_url = _MCP_URLS.get(service)
    if base_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unknown service: {service}",
        )

    try:
        resp = await _get_client().get(
            f"{base_url}/health", headers=_get_internal_headers()
        )
        return resp.json()
    except httpx.RequestError as exc:
        logger.error("Health check error [%s]: %s", service, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP service '{service}' unreachable",
        ) from exc


# ---------------------------------------------------------------------------
# Billing routes
# ---------------------------------------------------------------------------


@router.get("/billing/health", tags=["billing"])
async def billing_health() -> Any:
    """Health check for mcp-billing.

    Returns:
        Health status from mcp-billing.
    """
    return await _proxy_health("billing")


@router.post("/billing/call", tags=["billing"])
async def billing_call(
    body: McpCallRequest,
    current_user: dict = Depends(get_current_user),
) -> Any:
    """Invoke a mcp-billing tool.

    Args:
        body: Tool name and parameters.
        current_user: Authenticated user context from JWT.

    Returns:
        MCP tool result.

    Example:
        POST /api/v1/billing/call
        {
          "tool": "list_invoices",
          "params": {}
        }
    """
    params = {
        **body.params,
        "tenant_id": str(current_user["tenant_id"]),
        "user_id": str(current_user["user_id"]),
    }
    return await _proxy_call("billing", body.tool, params)


# ---------------------------------------------------------------------------
# Analytics routes
# ---------------------------------------------------------------------------


@router.get("/analytics/health", tags=["analytics"])
async def analytics_health() -> Any:
    """Health check for mcp-analytics.

    Returns:
        Health status from mcp-analytics.
    """
    return await _proxy_health("analytics")


@router.post("/analytics/call", tags=["analytics"])
async def analytics_call(
    body: McpCallRequest,
    current_user: dict = Depends(get_current_user),
) -> Any:
    """Invoke a mcp-analytics tool.

    Args:
        body: Tool name and parameters.
        current_user: Authenticated user context from JWT.

    Returns:
        MCP tool result.

    Example:
        POST /api/v1/analytics/call
        {
          "tool": "get_pipeline_metrics",
          "params": {}
        }
    """
    params = {
        **body.params,
        "tenant_id": str(current_user["tenant_id"]),
        "user_id": str(current_user["user_id"]),
    }
    return await _proxy_call("analytics", body.tool, params)


# ---------------------------------------------------------------------------
# Sequences routes
# ---------------------------------------------------------------------------


@router.get("/sequences/health", tags=["sequences"])
async def sequences_health() -> Any:
    """Health check for mcp-sequences.

    Returns:
        Health status from mcp-sequences.
    """
    return await _proxy_health("sequences")


@router.post("/sequences/call", tags=["sequences"])
async def sequences_call(
    body: McpCallRequest,
    current_user: dict = Depends(get_current_user),
) -> Any:
    """Invoke a mcp-sequences tool.

    Args:
        body: Tool name and parameters.
        current_user: Authenticated user context from JWT.

    Returns:
        MCP tool result.

    Example:
        POST /api/v1/sequences/call
        {
          "tool": "list_sequences",
          "params": {}
        }
    """
    params = {
        **body.params,
        "tenant_id": str(current_user["tenant_id"]),
        "user_id": str(current_user["user_id"]),
    }
    return await _proxy_call("sequences", body.tool, params)


# ---------------------------------------------------------------------------
# Filesystem routes
# ---------------------------------------------------------------------------


@router.get("/filesystem/health", tags=["filesystem"])
async def filesystem_health() -> Any:
    """Health check for mcp-filesystem.

    Returns:
        Health status from mcp-filesystem.
    """
    return await _proxy_health("filesystem")


@router.post("/filesystem/call", tags=["filesystem"])
async def filesystem_call(
    body: McpCallRequest,
    current_user: dict = Depends(get_current_user),
) -> Any:
    """Invoke a mcp-filesystem tool.

    Args:
        body: Tool name and parameters.
        current_user: Authenticated user context from JWT.

    Returns:
        MCP tool result.

    Example:
        POST /api/v1/filesystem/call
        {
          "tool": "list_documents",
          "params": {}
        }
    """
    params = {
        **body.params,
        "tenant_id": str(current_user["tenant_id"]),
        "user_id": str(current_user["user_id"]),
    }
    return await _proxy_call("filesystem", body.tool, params)
