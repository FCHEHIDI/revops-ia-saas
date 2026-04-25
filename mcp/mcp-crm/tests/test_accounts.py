"""
Unit tests for account tools.
All backend HTTP calls are mocked with respx — no real backend required.
"""

from __future__ import annotations

import pytest
import httpx

from constants import (
    VALID_TENANT_ID,
    VALID_ACCOUNT_ID,
    VALID_USER_ID,
)
from tools.accounts import get_account, search_accounts, create_account, update_account

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------


async def test_get_account_success(mock_client, mock_account):
    client, router = mock_client
    router.get(f"/internal/v1/crm/accounts/{VALID_ACCOUNT_ID}").mock(
        return_value=httpx.Response(200, json=mock_account)
    )

    result = await get_account(
        {"tenant_id": VALID_TENANT_ID, "account_id": VALID_ACCOUNT_ID},
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["account"]["name"] == "Acme Corp"
    assert result["result"]["account"]["id"] == VALID_ACCOUNT_ID


async def test_get_account_not_found(mock_client):
    client, router = mock_client
    router.get(f"/internal/v1/crm/accounts/{VALID_ACCOUNT_ID}").mock(
        return_value=httpx.Response(404, json={"detail": "Account not found"})
    )

    result = await get_account(
        {"tenant_id": VALID_TENANT_ID, "account_id": VALID_ACCOUNT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("NOT_FOUND:")


async def test_get_account_backend_timeout(mock_client):
    client, router = mock_client
    router.get(f"/internal/v1/crm/accounts/{VALID_ACCOUNT_ID}").mock(
        side_effect=httpx.ReadTimeout("timeout", request=None)
    )

    result = await get_account(
        {"tenant_id": VALID_TENANT_ID, "account_id": VALID_ACCOUNT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("BACKEND_UNAVAILABLE:")


async def test_get_account_missing_tenant_id(mock_client):
    client, router = mock_client

    result = await get_account(
        {"account_id": VALID_ACCOUNT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("INVALID_TENANT:")


async def test_get_account_invalid_tenant_id(mock_client):
    client, router = mock_client

    result = await get_account(
        {"tenant_id": "bad-uuid", "account_id": VALID_ACCOUNT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("INVALID_TENANT:")


# ---------------------------------------------------------------------------
# search_accounts
# ---------------------------------------------------------------------------


async def test_search_accounts_success(mock_client, mock_account):
    client, router = mock_client
    router.get("/internal/v1/crm/accounts").mock(
        return_value=httpx.Response(
            200,
            json={"accounts": [mock_account], "total": 1, "page": 1, "page_size": 20},
        )
    )

    result = await search_accounts(
        {"tenant_id": VALID_TENANT_ID, "query": "Acme"},
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["total"] == 1


async def test_search_accounts_page_size_exceeds_max(mock_client):
    client, router = mock_client

    result = await search_accounts(
        {"tenant_id": VALID_TENANT_ID, "page_size": 200},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_search_accounts_missing_tenant(mock_client):
    client, router = mock_client

    result = await search_accounts({}, client, None)

    assert result["result"] is None
    assert result["error"].startswith("INVALID_TENANT:")


# ---------------------------------------------------------------------------
# create_account
# ---------------------------------------------------------------------------


async def test_create_account_success(mock_client, mock_account):
    client, router = mock_client
    router.post("/internal/v1/crm/accounts").mock(
        return_value=httpx.Response(201, json=mock_account)
    )

    result = await create_account(
        {
            "tenant_id": VALID_TENANT_ID,
            "name": "Acme Corp",
            "domain": "acme.com",
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["account"]["name"] == "Acme Corp"


async def test_create_account_missing_name(mock_client):
    client, router = mock_client

    result = await create_account(
        {"tenant_id": VALID_TENANT_ID, "created_by": VALID_USER_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_create_account_conflict(mock_client):
    client, router = mock_client
    router.post("/internal/v1/crm/accounts").mock(
        return_value=httpx.Response(409, json={"detail": "Account already exists"})
    )

    result = await create_account(
        {
            "tenant_id": VALID_TENANT_ID,
            "name": "Acme Corp",
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("CONFLICT:")


async def test_create_account_forbidden(mock_client):
    client, router = mock_client
    router.post("/internal/v1/crm/accounts").mock(
        return_value=httpx.Response(403, json={"detail": "Insufficient permissions"})
    )

    result = await create_account(
        {
            "tenant_id": VALID_TENANT_ID,
            "name": "Acme Corp",
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("FORBIDDEN:")


# ---------------------------------------------------------------------------
# update_account
# ---------------------------------------------------------------------------


async def test_update_account_success(mock_client, mock_account):
    client, router = mock_client
    updated = {**mock_account, "industry": "FinTech"}
    router.put(f"/internal/v1/crm/accounts/{VALID_ACCOUNT_ID}").mock(
        return_value=httpx.Response(200, json=updated)
    )

    result = await update_account(
        {
            "tenant_id": VALID_TENANT_ID,
            "account_id": VALID_ACCOUNT_ID,
            "industry": "FinTech",
        },
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["account"]["industry"] == "FinTech"


async def test_update_account_not_found(mock_client):
    client, router = mock_client
    router.put(f"/internal/v1/crm/accounts/{VALID_ACCOUNT_ID}").mock(
        return_value=httpx.Response(404, json={"detail": "Account not found"})
    )

    result = await update_account(
        {
            "tenant_id": VALID_TENANT_ID,
            "account_id": VALID_ACCOUNT_ID,
            "name": "New Name",
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("NOT_FOUND:")


async def test_update_account_no_fields(mock_client):
    client, router = mock_client

    result = await update_account(
        {"tenant_id": VALID_TENANT_ID, "account_id": VALID_ACCOUNT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")
