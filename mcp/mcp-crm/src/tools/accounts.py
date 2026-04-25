from __future__ import annotations

import httpx

from config import Settings
from errors import (
    validate_tenant_id,
    validate_uuid_field,
    validate_required_str,
    validate_positive_int,
    success_response,
    CrmMcpError,
    tool,
)
from http_client import call_backend

_BASE = "/internal/v1/crm/accounts"


@tool
async def get_account(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """GET /internal/v1/crm/accounts/{account_id}"""
    tenant_id = validate_tenant_id(params.get("tenant_id"))
    account_id = validate_uuid_field(params, "account_id")

    data = await call_backend(client, "GET", f"{_BASE}/{account_id}", tenant_id)
    return success_response({"account": data})


@tool
async def search_accounts(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """GET /internal/v1/crm/accounts?query=...&industry=...&page=...&page_size=..."""
    tenant_id = validate_tenant_id(params.get("tenant_id"))

    page = validate_positive_int(params, "page", default=1, min_val=1)
    page_size = validate_positive_int(
        params, "page_size", default=20, min_val=1, max_val=100
    )

    query_params: dict = {"page": page, "page_size": page_size}
    if params.get("query"):
        query_params["query"] = str(params["query"])
    if params.get("industry"):
        query_params["industry"] = str(params["industry"])

    data = await call_backend(client, "GET", _BASE, tenant_id, params=query_params)
    return success_response(data)


@tool
async def create_account(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """POST /internal/v1/crm/accounts"""
    tenant_id = validate_tenant_id(params.get("tenant_id"))

    name = validate_required_str(params, "name")
    created_by = validate_uuid_field(params, "created_by")

    body: dict = {"name": name, "created_by": created_by}
    for opt_field in ("domain", "industry", "size"):
        if params.get(opt_field):
            body[opt_field] = str(params[opt_field])

    data = await call_backend(client, "POST", _BASE, tenant_id, json=body)
    return success_response({"account": data})


@tool
async def update_account(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """PUT /internal/v1/crm/accounts/{account_id}"""
    tenant_id = validate_tenant_id(params.get("tenant_id"))
    account_id = validate_uuid_field(params, "account_id")

    body: dict = {}
    for str_field in ("name", "domain", "industry", "size", "arr", "status"):
        if params.get(str_field) is not None:
            body[str_field] = str(params[str_field])

    if not body:
        raise CrmMcpError(
            "VALIDATION_ERROR", "At least one field must be provided for update"
        )

    data = await call_backend(
        client, "PUT", f"{_BASE}/{account_id}", tenant_id, json=body
    )
    return success_response({"account": data})
