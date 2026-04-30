"""
Unit tests for deal tools.
All backend HTTP calls are mocked with respx — no real backend required.
"""

from __future__ import annotations

import pytest
import httpx

from constants import (
    VALID_TENANT_ID,
    VALID_DEAL_ID,
    VALID_ACCOUNT_ID,
    VALID_USER_ID,
)
from tools.deals import get_deal, list_deals, create_deal, update_deal_stage

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# get_deal
# ---------------------------------------------------------------------------


async def test_get_deal_success(mock_client, mock_deal):
    client, router = mock_client
    router.get(f"/internal/v1/crm/deals/{VALID_DEAL_ID}").mock(
        return_value=httpx.Response(200, json=mock_deal)
    )

    result = await get_deal(
        {"tenant_id": VALID_TENANT_ID, "deal_id": VALID_DEAL_ID},
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["deal"]["id"] == VALID_DEAL_ID
    assert result["result"]["deal"]["stage"] == "prospecting"


async def test_get_deal_not_found(mock_client):
    client, router = mock_client
    router.get(f"/internal/v1/crm/deals/{VALID_DEAL_ID}").mock(
        return_value=httpx.Response(404, json={"detail": "Deal not found"})
    )

    result = await get_deal(
        {"tenant_id": VALID_TENANT_ID, "deal_id": VALID_DEAL_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("NOT_FOUND:")


async def test_get_deal_missing_tenant_id(mock_client):
    client, router = mock_client

    result = await get_deal(
        {"deal_id": VALID_DEAL_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("INVALID_TENANT:")


async def test_get_deal_invalid_tenant_id(mock_client):
    client, router = mock_client

    result = await get_deal(
        {"tenant_id": "123-bad", "deal_id": VALID_DEAL_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("INVALID_TENANT:")


# ---------------------------------------------------------------------------
# list_deals
# ---------------------------------------------------------------------------


async def test_list_deals_success_no_filter(mock_client, mock_deal):
    client, router = mock_client
    router.get("/internal/v1/crm/deals").mock(
        return_value=httpx.Response(
            200,
            json={"deals": [mock_deal], "total": 1, "page": 1, "page_size": 20},
        )
    )

    result = await list_deals(
        {"tenant_id": VALID_TENANT_ID},
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["total"] == 1
    assert result["result"]["deals"][0]["stage"] == "prospecting"


async def test_list_deals_with_stage_filter(mock_client, mock_deal):
    client, router = mock_client
    router.get("/internal/v1/crm/deals").mock(
        return_value=httpx.Response(
            200,
            json={"deals": [mock_deal], "total": 1, "page": 1, "page_size": 20},
        )
    )

    result = await list_deals(
        {"tenant_id": VALID_TENANT_ID, "stage": "prospecting"},
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["total"] == 1


async def test_list_deals_invalid_stage_enum(mock_client):
    client, router = mock_client

    result = await list_deals(
        {"tenant_id": VALID_TENANT_ID, "stage": "INVALID_STAGE"},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_list_deals_backend_500(mock_client):
    client, router = mock_client
    router.get("/internal/v1/crm/deals").mock(
        return_value=httpx.Response(500, json={"detail": "Internal server error"})
    )

    result = await list_deals(
        {"tenant_id": VALID_TENANT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("BACKEND_UNAVAILABLE:")


async def test_list_deals_missing_tenant(mock_client):
    client, router = mock_client

    result = await list_deals({}, client, None)

    assert result["result"] is None
    assert result["error"].startswith("INVALID_TENANT:")


# ---------------------------------------------------------------------------
# create_deal
# ---------------------------------------------------------------------------


async def test_create_deal_success(mock_client, mock_deal):
    client, router = mock_client
    router.post("/internal/v1/crm/deals").mock(
        return_value=httpx.Response(201, json=mock_deal)
    )

    result = await create_deal(
        {
            "tenant_id": VALID_TENANT_ID,
            "title": "Enterprise deal",
            "account_id": VALID_ACCOUNT_ID,
            "stage": "prospecting",
            "owner_id": VALID_USER_ID,
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["deal"]["title"] == "Enterprise deal"


async def test_create_deal_missing_account_id(mock_client):
    client, router = mock_client

    result = await create_deal(
        {
            "tenant_id": VALID_TENANT_ID,
            "title": "Enterprise deal",
            "stage": "prospecting",
            "owner_id": VALID_USER_ID,
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_create_deal_invalid_stage(mock_client):
    client, router = mock_client

    result = await create_deal(
        {
            "tenant_id": VALID_TENANT_ID,
            "title": "Deal",
            "account_id": VALID_ACCOUNT_ID,
            "stage": "INVALID",
            "owner_id": VALID_USER_ID,
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_create_deal_forbidden(mock_client):
    client, router = mock_client
    router.post("/internal/v1/crm/deals").mock(
        return_value=httpx.Response(403, json={"detail": "Insufficient permissions"})
    )

    result = await create_deal(
        {
            "tenant_id": VALID_TENANT_ID,
            "title": "Enterprise deal",
            "account_id": VALID_ACCOUNT_ID,
            "stage": "prospecting",
            "owner_id": VALID_USER_ID,
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("FORBIDDEN:")


# ---------------------------------------------------------------------------
# update_deal_stage
# ---------------------------------------------------------------------------


async def test_update_deal_stage_success(mock_client, mock_deal):
    client, router = mock_client
    updated_deal = {**mock_deal, "stage": "qualification"}
    router.put(f"/internal/v1/crm/deals/{VALID_DEAL_ID}").mock(
        return_value=httpx.Response(200, json=updated_deal)
    )

    result = await update_deal_stage(
        {
            "tenant_id": VALID_TENANT_ID,
            "deal_id": VALID_DEAL_ID,
            "new_stage": "qualification",
        },
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["deal"]["stage"] == "qualification"


async def test_update_deal_stage_with_notes(mock_client, mock_deal):
    client, router = mock_client
    updated_deal = {**mock_deal, "stage": "proposal", "notes": "Client interested"}
    router.put(f"/internal/v1/crm/deals/{VALID_DEAL_ID}").mock(
        return_value=httpx.Response(200, json=updated_deal)
    )

    result = await update_deal_stage(
        {
            "tenant_id": VALID_TENANT_ID,
            "deal_id": VALID_DEAL_ID,
            "new_stage": "proposal",
            "notes": "Client interested",
        },
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["deal"]["notes"] == "Client interested"


async def test_update_deal_stage_invalid_stage(mock_client):
    client, router = mock_client

    result = await update_deal_stage(
        {
            "tenant_id": VALID_TENANT_ID,
            "deal_id": VALID_DEAL_ID,
            "new_stage": "INVALID_STAGE",
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_update_deal_stage_missing_new_stage(mock_client):
    client, router = mock_client

    result = await update_deal_stage(
        {"tenant_id": VALID_TENANT_ID, "deal_id": VALID_DEAL_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_update_deal_stage_not_found(mock_client):
    client, router = mock_client
    router.put(f"/internal/v1/crm/deals/{VALID_DEAL_ID}").mock(
        return_value=httpx.Response(404, json={"detail": "Deal not found"})
    )

    result = await update_deal_stage(
        {
            "tenant_id": VALID_TENANT_ID,
            "deal_id": VALID_DEAL_ID,
            "new_stage": "closed_won",
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("NOT_FOUND:")


async def test_update_deal_stage_forbidden(mock_client):
    client, router = mock_client
    router.put(f"/internal/v1/crm/deals/{VALID_DEAL_ID}").mock(
        return_value=httpx.Response(403, json={"detail": "crm:deals:write required"})
    )

    result = await update_deal_stage(
        {
            "tenant_id": VALID_TENANT_ID,
            "deal_id": VALID_DEAL_ID,
            "new_stage": "closed_won",
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("FORBIDDEN:")
