from __future__ import annotations

import httpx

from config import Settings
from errors import (
    validate_tenant_id,
    validate_uuid_field,
    validate_required_str,
    validate_enum_field,
    validate_positive_int,
    success_response,
    CrmMcpError,
    tool,
)
from http_client import call_backend
from schemas import DEAL_STAGE_VALUES

_BASE = "/internal/v1/crm/deals"


@tool
async def get_deal(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """GET /internal/v1/crm/deals/{deal_id}"""
    tenant_id = validate_tenant_id(params.get("tenant_id"))
    deal_id = validate_uuid_field(params, "deal_id")

    data = await call_backend(client, "GET", f"{_BASE}/{deal_id}", tenant_id)
    return success_response({"deal": data})


@tool
async def list_deals(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """GET /internal/v1/crm/deals?stage=...&owner_id=...&account_id=...&page=...&page_size=..."""
    tenant_id = validate_tenant_id(params.get("tenant_id"))

    page = validate_positive_int(params, "page", default=1, min_val=1)
    page_size = validate_positive_int(
        params, "page_size", default=20, min_val=1, max_val=100
    )
    stage = validate_enum_field(params, "stage", DEAL_STAGE_VALUES)

    query_params: dict = {"page": page, "page_size": page_size}
    if stage:
        query_params["stage"] = stage
    if params.get("owner_id"):
        query_params["owner_id"] = validate_uuid_field(params, "owner_id")
    if params.get("account_id"):
        query_params["account_id"] = validate_uuid_field(params, "account_id")

    data = await call_backend(client, "GET", _BASE, tenant_id, params=query_params)
    return success_response(data)


@tool
async def create_deal(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """POST /internal/v1/crm/deals"""
    tenant_id = validate_tenant_id(params.get("tenant_id"))

    title = validate_required_str(params, "title")
    account_id = validate_uuid_field(params, "account_id")
    stage = validate_enum_field(params, "stage", DEAL_STAGE_VALUES, required=True)
    owner_id = validate_uuid_field(params, "owner_id")
    created_by = validate_uuid_field(params, "created_by")

    body: dict = {
        "title": title,
        "account_id": account_id,
        "stage": stage,
        "owner_id": owner_id,
        "created_by": created_by,
    }

    if params.get("amount") is not None:
        body["amount"] = str(params["amount"])

    currency = params.get("currency", "USD")
    if len(str(currency)) != 3:
        raise CrmMcpError(
            "VALIDATION_ERROR", "'currency' must be a 3-character ISO 4217 code"
        )
    body["currency"] = str(currency).upper()

    if params.get("close_date") is not None:
        body["close_date"] = str(params["close_date"])
    if params.get("contact_id") is not None:
        body["contact_id"] = validate_uuid_field(params, "contact_id")
    if params.get("notes") is not None:
        body["notes"] = str(params["notes"])

    data = await call_backend(client, "POST", _BASE, tenant_id, json=body)
    return success_response({"deal": data})


@tool
async def update_deal_stage(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """
    PUT /internal/v1/crm/deals/{deal_id}
    Body: {"stage": new_stage, "notes": notes}
    Triggers RAG indexing on backend when notes are present.
    """
    tenant_id = validate_tenant_id(params.get("tenant_id"))
    deal_id = validate_uuid_field(params, "deal_id")
    new_stage = validate_enum_field(
        params, "new_stage", DEAL_STAGE_VALUES, required=True
    )

    body: dict = {"stage": new_stage}
    if params.get("notes") is not None:
        body["notes"] = str(params["notes"])

    data = await call_backend(client, "PUT", f"{_BASE}/{deal_id}", tenant_id, json=body)
    return success_response({"deal": data})
