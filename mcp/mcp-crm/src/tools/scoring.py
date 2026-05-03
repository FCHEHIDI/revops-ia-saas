"""score_lead MCP tool for mcp-crm.

Calls POST /internal/v1/scoring/score-lead on the backend.
Returns the AI lead score (0-100), reasoning, and recommended action.
"""

from __future__ import annotations

import httpx

from config import Settings
from errors import (
    CrmMcpError,
    success_response,
    tool,
    validate_tenant_id,
    validate_uuid_field,
)
from http_client import call_backend


@tool
async def score_lead(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """Score a CRM contact using AI (LLM or heuristic fallback).

    Calls the backend ``POST /internal/v1/scoring/score-lead`` endpoint which
    checks a Redis cache (TTL 24h) before invoking an LLM.

    Args:
        params: Tool parameters.
            - tenant_id (str, required): Tenant UUID.
            - contact_id (str, required): Contact UUID to score.
            - force_refresh (bool, optional): Bypass cache if True.
        client: Shared httpx AsyncClient (injected by server).
        settings: Application settings (injected by server).

    Returns:
        success_response dict with:
            - contact_id (str)
            - score (int, 0-100)
            - reasoning (str)
            - recommended_action (str)
            - model_used (str)
            - cached (bool)
            - created_at (str, ISO-8601)
    """
    tenant_id = validate_tenant_id(params.get("tenant_id"))
    contact_id = validate_uuid_field(params, "contact_id")

    force_refresh = bool(params.get("force_refresh", False))

    data = await call_backend(
        client,
        "POST",
        "/internal/v1/scoring/score-lead",
        tenant_id,
        json={
            "tenant_id": tenant_id,
            "contact_id": contact_id,
            "force_refresh": force_refresh,
        },
    )
    return success_response({"lead_score": data})
