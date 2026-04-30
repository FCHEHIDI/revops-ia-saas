"""
Unit tests for contact tools.
All backend HTTP calls are mocked with respx — no real backend required.
"""

from __future__ import annotations

import pytest
import httpx

from constants import (
    VALID_TENANT_ID,
    VALID_CONTACT_ID,
    VALID_USER_ID,
    MOCK_BACKEND_URL,
)
from tools.contacts import get_contact, search_contacts, create_contact, update_contact

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_url(path: str) -> str:
    return f"{MOCK_BACKEND_URL}{path}"


# ---------------------------------------------------------------------------
# get_contact
# ---------------------------------------------------------------------------


async def test_get_contact_success(mock_client, mock_contact):
    client, router = mock_client
    router.get(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
        return_value=httpx.Response(200, json=mock_contact)
    )

    result = await get_contact(
        {"tenant_id": VALID_TENANT_ID, "contact_id": VALID_CONTACT_ID},
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["contact"]["email"] == "alice@example.com"
    assert result["result"]["contact"]["id"] == VALID_CONTACT_ID


async def test_get_contact_not_found(mock_client):
    client, router = mock_client
    router.get(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
        return_value=httpx.Response(404, json={"detail": "Contact not found"})
    )

    result = await get_contact(
        {"tenant_id": VALID_TENANT_ID, "contact_id": VALID_CONTACT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("NOT_FOUND:")


async def test_get_contact_backend_500(mock_client):
    client, router = mock_client
    router.get(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
        return_value=httpx.Response(500, json={"detail": "Internal Server Error"})
    )

    result = await get_contact(
        {"tenant_id": VALID_TENANT_ID, "contact_id": VALID_CONTACT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("BACKEND_UNAVAILABLE:")


async def test_get_contact_backend_timeout(mock_client):
    client, router = mock_client
    router.get(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
        side_effect=httpx.ReadTimeout("timeout", request=None)
    )

    result = await get_contact(
        {"tenant_id": VALID_TENANT_ID, "contact_id": VALID_CONTACT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("BACKEND_UNAVAILABLE:")


async def test_get_contact_missing_tenant_id(mock_client):
    client, router = mock_client

    result = await get_contact(
        {"contact_id": VALID_CONTACT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("INVALID_TENANT:")


async def test_get_contact_invalid_tenant_id(mock_client):
    client, router = mock_client

    result = await get_contact(
        {"tenant_id": "not-a-uuid", "contact_id": VALID_CONTACT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("INVALID_TENANT:")


async def test_get_contact_missing_contact_id(mock_client):
    client, router = mock_client

    result = await get_contact(
        {"tenant_id": VALID_TENANT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


# ---------------------------------------------------------------------------
# search_contacts
# ---------------------------------------------------------------------------


async def test_search_contacts_success(mock_client, mock_contact):
    client, router = mock_client
    router.get("/internal/v1/crm/contacts").mock(
        return_value=httpx.Response(
            200,
            json={"contacts": [mock_contact], "total": 1, "page": 1, "page_size": 20},
        )
    )

    result = await search_contacts(
        {"tenant_id": VALID_TENANT_ID, "query": "Alice"},
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["total"] == 1
    assert len(result["result"]["contacts"]) == 1


async def test_search_contacts_invalid_page_size(mock_client):
    client, router = mock_client

    result = await search_contacts(
        {"tenant_id": VALID_TENANT_ID, "page_size": -1},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_search_contacts_invalid_status_enum(mock_client):
    client, router = mock_client

    result = await search_contacts(
        {"tenant_id": VALID_TENANT_ID, "status": "INVALID_STATUS"},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_search_contacts_missing_tenant(mock_client):
    client, router = mock_client

    result = await search_contacts({}, client, None)

    assert result["result"] is None
    assert result["error"].startswith("INVALID_TENANT:")


# ---------------------------------------------------------------------------
# create_contact
# ---------------------------------------------------------------------------


async def test_create_contact_success(mock_client, mock_contact):
    client, router = mock_client
    router.post("/internal/v1/crm/contacts").mock(
        return_value=httpx.Response(201, json=mock_contact)
    )

    result = await create_contact(
        {
            "tenant_id": VALID_TENANT_ID,
            "first_name": "Alice",
            "last_name": "Dupont",
            "email": "alice@example.com",
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["contact"]["id"] == VALID_CONTACT_ID


async def test_create_contact_missing_email(mock_client):
    client, router = mock_client

    result = await create_contact(
        {
            "tenant_id": VALID_TENANT_ID,
            "first_name": "Alice",
            "last_name": "Dupont",
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


async def test_create_contact_duplicate_email(mock_client):
    client, router = mock_client
    router.post("/internal/v1/crm/contacts").mock(
        return_value=httpx.Response(409, json={"detail": "Email already exists"})
    )

    result = await create_contact(
        {
            "tenant_id": VALID_TENANT_ID,
            "first_name": "Alice",
            "last_name": "Dupont",
            "email": "alice@example.com",
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("CONFLICT:")


async def test_create_contact_forbidden(mock_client):
    client, router = mock_client
    router.post("/internal/v1/crm/contacts").mock(
        return_value=httpx.Response(403, json={"detail": "Insufficient permissions"})
    )

    result = await create_contact(
        {
            "tenant_id": VALID_TENANT_ID,
            "first_name": "Alice",
            "last_name": "Dupont",
            "email": "alice@example.com",
            "created_by": VALID_USER_ID,
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("FORBIDDEN:")


# ---------------------------------------------------------------------------
# update_contact
# ---------------------------------------------------------------------------


async def test_update_contact_success(mock_client, mock_contact):
    client, router = mock_client
    updated = {**mock_contact, "job_title": "CTO"}
    router.put(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
        return_value=httpx.Response(200, json=updated)
    )

    result = await update_contact(
        {
            "tenant_id": VALID_TENANT_ID,
            "contact_id": VALID_CONTACT_ID,
            "job_title": "CTO",
        },
        client,
        None,
    )

    assert result["error"] is None
    assert result["result"]["contact"]["job_title"] == "CTO"


async def test_update_contact_not_found(mock_client):
    client, router = mock_client
    router.put(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
        return_value=httpx.Response(404, json={"detail": "Not found"})
    )

    result = await update_contact(
        {
            "tenant_id": VALID_TENANT_ID,
            "contact_id": VALID_CONTACT_ID,
            "phone": "+33600000099",
        },
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("NOT_FOUND:")


async def test_update_contact_no_fields(mock_client):
    client, router = mock_client

    result = await update_contact(
        {"tenant_id": VALID_TENANT_ID, "contact_id": VALID_CONTACT_ID},
        client,
        None,
    )

    assert result["result"] is None
    assert result["error"].startswith("VALIDATION_ERROR:")


# ---------------------------------------------------------------------------
# Tenant isolation — verify X-Tenant-ID and X-Internal-API-Key headers
# ---------------------------------------------------------------------------


async def test_get_contact_forwards_tenant_id_header(mock_client, mock_contact):
    """Verifies that X-Tenant-ID is forwarded verbatim to the backend."""
    client, router = mock_client
    route = router.get(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
        return_value=httpx.Response(200, json=mock_contact)
    )

    await get_contact(
        {"tenant_id": VALID_TENANT_ID, "contact_id": VALID_CONTACT_ID},
        client,
        None,
    )

    assert route.called
    sent_request = route.calls[0].request
    assert sent_request.headers["x-tenant-id"] == VALID_TENANT_ID


async def test_get_contact_forwards_internal_api_key(mock_client, mock_contact):
    """Verifies that X-Internal-API-Key is always sent to the backend."""
    client, router = mock_client
    route = router.get(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
        return_value=httpx.Response(200, json=mock_contact)
    )

    await get_contact(
        {"tenant_id": VALID_TENANT_ID, "contact_id": VALID_CONTACT_ID},
        client,
        None,
    )

    assert route.called
    sent_request = route.calls[0].request
    assert sent_request.headers["x-internal-api-key"] == "test-internal-key"


async def test_tenant_a_does_not_bleed_to_tenant_b(mock_client, mock_contact):
    """Two consecutive calls with different tenant IDs must use distinct X-Tenant-ID headers."""
    tenant_a = VALID_TENANT_ID
    tenant_b = "00000000-0000-0000-0000-000000000002"

    client, router = mock_client

    # Single route handles both calls — we inspect headers per call
    route = router.get(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
        return_value=httpx.Response(200, json=mock_contact)
    )

    await get_contact(
        {"tenant_id": tenant_a, "contact_id": VALID_CONTACT_ID}, client, None
    )
    await get_contact(
        {"tenant_id": tenant_b, "contact_id": VALID_CONTACT_ID}, client, None
    )

    assert len(route.calls) == 2
    tenant_ids_sent = [c.request.headers["x-tenant-id"] for c in route.calls]
    assert tenant_ids_sent[0] == tenant_a
    assert tenant_ids_sent[1] == tenant_b
