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

import asyncio
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.auth.dependencies import get_current_active_user
from app.models.user import User

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
    current_user: User = Depends(get_current_active_user),
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
        "tenant_id": str(current_user.tenant_id),
        "user_id": str(current_user.id),
    }
    return await _proxy_call("billing", body.tool, params)


@router.get("/billing/invoices", tags=["billing"])
async def billing_list_invoices(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """List invoices for the current tenant via mcp-billing.

    Args:
        page: Page number (1-based).
        page_size: Items per page (max 100).
        status: Optional status filter (paid, pending, overdue, draft, cancelled).
        current_user: Authenticated user context from JWT.

    Returns:
        Paginated invoice list from mcp-billing with ``items`` and ``total`` keys.
    """
    limit = min(max(page_size, 1), 100)
    offset = (max(page, 1) - 1) * limit
    params: dict[str, Any] = {
        "tenant_id": str(current_user.tenant_id),
        "limit": limit,
        "offset": offset,
    }
    if status:
        params["status"] = status
    raw = await _proxy_call("billing", "list_invoices", params)
    # Normalise to {items, total} shape expected by the frontend
    result = raw.get("result") if isinstance(raw, dict) and "result" in raw else raw
    if isinstance(result, dict):
        invoices = result.get("invoices", [])
        total = result.get("total", len(invoices))
        # Map InvoiceSummary fields → frontend Invoice interface
        items = [
            {
                "id": str(inv.get("id", "")),
                "tenant_id": str(inv.get("tenant_id", "")),
                "number": inv.get("invoice_number", ""),
                "customer_name": inv.get("customer_name") or "",
                "customer_email": "",
                "amount": float(inv.get("amount", 0)),
                "currency": inv.get("currency", "USD"),
                "status": inv.get("status", "draft"),
                "due_date": inv.get("due_date", ""),
                "issued_at": inv.get("issued_at", ""),
                "paid_at": inv.get("paid_at"),
            }
            for inv in invoices
        ]
        return {"items": items, "total": total}
    return raw


@router.get("/billing/subscription", tags=["billing"])
async def billing_get_subscription(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get the active subscription for the current tenant via mcp-billing.

    Args:
        current_user: Authenticated user context from JWT.

    Returns:
        Subscription details from mcp-billing.
    """
    params: dict[str, Any] = {"tenant_id": str(current_user.tenant_id)}
    return await _proxy_call("billing", "get_subscription", params)


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
    current_user: User = Depends(get_current_active_user),
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
        "tenant_id": str(current_user.tenant_id),
        "user_id": str(current_user.id),
    }
    return await _proxy_call("analytics", body.tool, params)


@router.get("/analytics/metrics", tags=["analytics"])
async def analytics_metrics(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Aggregate KPI metrics for the dashboard by calling MRR + pipeline tools in parallel.

    Args:
        current_user: Authenticated user context from JWT.

    Returns:
        List of Metric objects with ``label``, ``value``, ``change``, ``changeType``, ``period``.
    """
    tenant_id = str(current_user.tenant_id)
    mrr_params = {"tenant_id": tenant_id, "months": 2}
    pipeline_params = {"tenant_id": tenant_id, "period": "current_month"}

    mrr_raw, pipeline_raw = await asyncio.gather(
        _proxy_call("analytics", "get_mrr_trend", mrr_params),
        _proxy_call("analytics", "get_pipeline_metrics", pipeline_params),
        return_exceptions=True,
    )

    metrics: list[dict[str, Any]] = []

    # MRR metric
    mrr_result = (mrr_raw.get("result") if isinstance(mrr_raw, dict) and "result" in mrr_raw else mrr_raw) if not isinstance(mrr_raw, Exception) else None
    if mrr_result and isinstance(mrr_result, dict):
        current_mrr = float(mrr_result.get("current_mrr", 0))
        mom = mrr_result.get("mom_growth_rate", 0.0)
        metrics.append({
            "label": "MRR",
            "value": f"{current_mrr:,.0f}",
            "unit": "€",
            "change": round(float(mom) * 100, 1),
            "changeType": "increase" if mom > 0 else ("decrease" if mom < 0 else "neutral"),
            "period": "mois en cours",
        })

    # Pipeline metrics
    pipeline_result = (pipeline_raw.get("result") if isinstance(pipeline_raw, dict) and "result" in pipeline_raw else pipeline_raw) if not isinstance(pipeline_raw, Exception) else None
    if pipeline_result and isinstance(pipeline_result, dict):
        win_rate = float(pipeline_result.get("win_rate", 0))
        deals_created = int(pipeline_result.get("deals_created", 0))
        revenue = float(pipeline_result.get("revenue_generated", 0))
        metrics.append({
            "label": "Taux de conversion",
            "value": f"{win_rate * 100:.1f}",
            "unit": "%",
            "change": None,
            "changeType": "neutral",
            "period": "mois en cours",
        })
        metrics.append({
            "label": "Deals créés",
            "value": str(deals_created),
            "change": None,
            "changeType": "neutral",
            "period": "mois en cours",
        })
        metrics.append({
            "label": "Revenus générés",
            "value": f"{revenue:,.0f}",
            "unit": "€",
            "change": None,
            "changeType": "neutral",
            "period": "mois en cours",
        })

    return metrics


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


@router.get("/sequences", tags=["sequences"])
async def sequences_list(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """List sequences for the current tenant.

    Args:
        page: 1-based page number.
        page_size: Items per page.
        current_user: Authenticated user context from JWT.

    Returns:
        PaginatedResponse with items and total.

    Example:
        GET /api/v1/sequences?page=1&page_size=20
    """
    params = {
        "tenant_id": str(current_user.tenant_id),
        "user_id": str(current_user.id),
        "page": page,
        "page_size": page_size,
    }
    raw = await _proxy_call("sequences", "list_sequences", params)
    # MCP returns {sequences: [...], total: N} — normalise to {items: [...], total: N}
    sequences = raw.get("sequences", []) if isinstance(raw, dict) else []
    total = raw.get("total", len(sequences)) if isinstance(raw, dict) else len(sequences)
    items = [
        {
            "id": str(s.get("id", "")),
            "tenant_id": str(current_user.tenant_id),
            "name": s.get("name", ""),
            "description": s.get("description"),
            "status": s.get("status", "draft"),
            "step_count": s.get("steps_count", 0),
            "enrolled_count": s.get("total_enrolled", 0),
            "completed_count": s.get("active_enrollments", 0),
            "created_at": s.get("created_at", ""),
            "updated_at": s.get("created_at", ""),
        }
        for s in sequences
    ]
    return {"items": items, "total": total}


@router.post("/sequences/call", tags=["sequences"])
async def sequences_call(
    body: McpCallRequest,
    current_user: User = Depends(get_current_active_user),
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
        "tenant_id": str(current_user.tenant_id),
        "user_id": str(current_user.id),
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
    current_user: User = Depends(get_current_active_user),
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
        "tenant_id": str(current_user.tenant_id),
        "user_id": str(current_user.id),
    }
    return await _proxy_call("filesystem", body.tool, params)
