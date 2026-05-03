"""Playbook MCP tools for mcp-crm.

Provides:
- list_playbooks: List active playbooks for a tenant.
- trigger_playbook: Manually trigger a specific playbook.
"""

from __future__ import annotations

import httpx

from config import Settings
from errors import (
    success_response,
    tool,
    validate_tenant_id,
    validate_uuid_field,
)
from http_client import call_backend


@tool
async def list_playbooks(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """List active automation playbooks for a tenant.

    Calls ``GET /internal/v1/playbooks?tenant_id=<id>`` on the backend.

    Args:
        params: Tool parameters.
            - tenant_id (str, required): Tenant UUID.
        client: Shared httpx AsyncClient (injected by server).
        settings: Application settings (injected by server).

    Returns:
        success_response dict with:
            - playbooks (list): Active playbook definitions.
    """
    tenant_id = validate_tenant_id(params.get("tenant_id"))

    data = await call_backend(
        client,
        "GET",
        "/internal/v1/playbooks",
        tenant_id,
        params={"tenant_id": tenant_id},
    )
    return success_response({"playbooks": data})


@tool
async def trigger_playbook(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """Manually trigger a playbook execution for a CRM entity.

    Calls ``POST /internal/v1/playbooks/trigger`` on the backend and returns
    the resulting run record.

    Args:
        params: Tool parameters.
            - tenant_id (str, required): Tenant UUID.
            - playbook_id (str, required): Playbook UUID to execute.
            - entity_type (str, optional): Type of entity (deal, contact, account).
            - entity_id (str, optional): UUID of the entity.
            - event_payload (dict, optional): Additional context passed to actions.
        client: Shared httpx AsyncClient (injected by server).
        settings: Application settings (injected by server).

    Returns:
        success_response dict with:
            - run (dict): PlaybookRun record including status and result.
    """
    tenant_id = validate_tenant_id(params.get("tenant_id"))
    playbook_id = validate_uuid_field(params, "playbook_id")

    body: dict = {"playbook_id": playbook_id}
    if params.get("entity_type"):
        body["entity_type"] = params["entity_type"]
    if params.get("entity_id"):
        body["entity_id"] = params["entity_id"]
    if params.get("event_payload"):
        body["event_payload"] = params["event_payload"]

    data = await call_backend(
        client,
        "POST",
        "/internal/v1/playbooks/trigger",
        tenant_id,
        json=body,
    )
    return success_response({"run": data})
