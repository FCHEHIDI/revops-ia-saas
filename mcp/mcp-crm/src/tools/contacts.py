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
from schemas import CONTACT_STATUS_VALUES

_BASE = "/internal/v1/crm/contacts"


@tool
async def get_contact(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """GET /internal/v1/crm/contacts/{contact_id}"""
    tenant_id = validate_tenant_id(params.get("tenant_id"))
    contact_id = validate_uuid_field(params, "contact_id")

    data = await call_backend(client, "GET", f"{_BASE}/{contact_id}", tenant_id)
    return success_response({"contact": data})


@tool
async def search_contacts(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """GET /internal/v1/crm/contacts?query=...&account_id=...&status=...&page=...&page_size=..."""
    tenant_id = validate_tenant_id(params.get("tenant_id"))

    page = validate_positive_int(params, "page", default=1, min_val=1)
    page_size = validate_positive_int(
        params, "page_size", default=20, min_val=1, max_val=100
    )
    status = validate_enum_field(params, "status", CONTACT_STATUS_VALUES)

    query_params: dict = {"page": page, "page_size": page_size}
    if params.get("query"):
        query_params["query"] = str(params["query"])
    if params.get("account_id"):
        try:
            validate_uuid_field(params, "account_id")
            query_params["account_id"] = str(params["account_id"])
        except CrmMcpError:
            raise CrmMcpError("VALIDATION_ERROR", "'account_id' is not a valid UUID")
    if status:
        query_params["status"] = status

    data = await call_backend(client, "GET", _BASE, tenant_id, params=query_params)
    return success_response(data)


@tool
async def create_contact(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """POST /internal/v1/crm/contacts"""
    tenant_id = validate_tenant_id(params.get("tenant_id"))

    first_name = validate_required_str(params, "first_name")
    last_name = validate_required_str(params, "last_name")
    email = validate_required_str(params, "email")
    created_by = validate_uuid_field(params, "created_by")

    body: dict = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "created_by": created_by,
    }
    if params.get("phone"):
        body["phone"] = str(params["phone"])
    if params.get("job_title"):
        body["job_title"] = str(params["job_title"])
    if params.get("account_id"):
        body["account_id"] = validate_uuid_field(params, "account_id")
    if params.get("status"):
        body["status"] = validate_enum_field(
            params, "status", CONTACT_STATUS_VALUES, required=False
        )

    data = await call_backend(client, "POST", _BASE, tenant_id, json=body)
    return success_response({"contact": data})


@tool
async def update_contact(
    params: dict,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict:
    """PUT /internal/v1/crm/contacts/{contact_id}"""
    tenant_id = validate_tenant_id(params.get("tenant_id"))
    contact_id = validate_uuid_field(params, "contact_id")

    body: dict = {}
    for str_field in ("first_name", "last_name", "phone", "job_title"):
        if params.get(str_field) is not None:
            body[str_field] = str(params[str_field])
    if params.get("email") is not None:
        body["email"] = str(params["email"])
    if params.get("account_id") is not None:
        body["account_id"] = validate_uuid_field(params, "account_id")
    if params.get("status") is not None:
        body["status"] = validate_enum_field(
            params, "status", CONTACT_STATUS_VALUES, required=False
        )

    if not body:
        raise CrmMcpError(
            "VALIDATION_ERROR", "At least one field must be provided for update"
        )

    data = await call_backend(
        client, "PUT", f"{_BASE}/{contact_id}", tenant_id, json=body
    )
    return success_response({"contact": data})
