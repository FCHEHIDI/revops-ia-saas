"""
Server-level tests for mcp-crm.

Tests /health, /tools, and /mcp/call dispatch logic (UNKNOWN_TOOL, INVALID_REQUEST).
Uses FastAPI ASGI transport — no real network, no real backend.

Backend HTTP calls are intercepted by respx for tool-dispatch tests.
"""

from __future__ import annotations

import pytest
import httpx
import respx
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport

from config import get_settings
from constants import MOCK_BACKEND_URL, VALID_CONTACT_ID, VALID_TENANT_ID

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    """
    Sets required env vars and clears the lru_cache so each test gets
    fresh Settings pointing at the mock backend.
    """
    monkeypatch.setenv("BACKEND_URL", MOCK_BACKEND_URL)
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def ac():
    """
    Async ASGI test client with proper FastAPI lifespan management.

    LifespanManager sends the lifespan.startup / lifespan.shutdown ASGI events,
    which triggers the FastAPI lifespan context manager and initialises
    app.state.http_client and app.state.settings.
    """
    from server import app

    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://testserver",
        ) as client:
            yield client


# ---------------------------------------------------------------------------
# Smoke: /health
# ---------------------------------------------------------------------------


async def test_health_returns_200(ac):
    response = await ac.get("/health")
    assert response.status_code == 200


async def test_health_body(ac):
    response = await ac.get("/health")
    data = response.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Smoke: /tools
# ---------------------------------------------------------------------------


async def test_tools_returns_200(ac):
    response = await ac.get("/tools")
    assert response.status_code == 200


async def test_tools_returns_12_tools(ac):
    response = await ac.get("/tools")
    tools = response.json()
    assert len(tools) == 12


async def test_tools_names(ac):
    response = await ac.get("/tools")
    names = {t["name"] for t in response.json()}
    expected = {
        "get_contact",
        "search_contacts",
        "create_contact",
        "update_contact",
        "get_account",
        "search_accounts",
        "create_account",
        "update_account",
        "get_deal",
        "list_deals",
        "create_deal",
        "update_deal_stage",
    }
    assert names == expected


async def test_tools_each_has_tenant_id_required(ac):
    """ADR-008 rule 5: tenant_id is mandatory in every tool."""
    response = await ac.get("/tools")
    for tool in response.json():
        schema = tool.get("input_schema", {})
        assert "tenant_id" in schema.get(
            "required", []
        ), f"Tool '{tool['name']}' must declare tenant_id as required"


async def test_tools_each_has_input_schema(ac):
    response = await ac.get("/tools")
    for tool in response.json():
        assert "input_schema" in tool, f"Tool '{tool['name']}' missing input_schema"
        assert tool["input_schema"]["type"] == "object"


# ---------------------------------------------------------------------------
# /mcp/call — dispatch errors (no backend call needed)
# ---------------------------------------------------------------------------


async def test_mcp_call_unknown_tool_returns_200(ac):
    """UNKNOWN_TOOL must be returned at HTTP 200 (JSON-RPC convention)."""
    response = await ac.post(
        "/mcp/call",
        json={"tool": "nonexistent_tool", "params": {"tenant_id": VALID_TENANT_ID}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] is None
    assert data["error"].startswith("UNKNOWN_TOOL:")


async def test_mcp_call_unknown_tool_lists_available(ac):
    response = await ac.post(
        "/mcp/call",
        json={"tool": "mystery", "params": {}},
    )
    data = response.json()
    assert "get_contact" in data["error"]


async def test_mcp_call_empty_body_returns_invalid_request(ac):
    """Empty body must return INVALID_REQUEST at HTTP 200."""
    response = await ac.post(
        "/mcp/call",
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] is None
    assert "INVALID_REQUEST" in data["error"]


async def test_mcp_call_malformed_json_returns_invalid_request(ac):
    response = await ac.post(
        "/mcp/call",
        content=b"{bad json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] is None
    assert "INVALID_REQUEST" in data["error"]


async def test_mcp_call_missing_tool_field(ac):
    """Body without 'tool' key must return INVALID_REQUEST."""
    response = await ac.post(
        "/mcp/call",
        json={"params": {"tenant_id": VALID_TENANT_ID}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] is None
    assert "INVALID_REQUEST" in data["error"]


# ---------------------------------------------------------------------------
# /mcp/call — tenant_id validation propagated through dispatch
# ---------------------------------------------------------------------------


async def test_mcp_call_missing_tenant_id_returns_invalid_tenant(ac):
    """Dispatching a known tool without tenant_id must return INVALID_TENANT."""
    response = await ac.post(
        "/mcp/call",
        json={
            "tool": "get_contact",
            "params": {"contact_id": VALID_CONTACT_ID},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] is None
    assert data["error"].startswith("INVALID_TENANT:")


async def test_mcp_call_invalid_uuid_tenant_id(ac):
    response = await ac.post(
        "/mcp/call",
        json={
            "tool": "get_contact",
            "params": {"tenant_id": "not-a-uuid", "contact_id": VALID_CONTACT_ID},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] is None
    assert data["error"].startswith("INVALID_TENANT:")


# ---------------------------------------------------------------------------
# /mcp/call — successful dispatch with backend mock (tenant isolation check)
# ---------------------------------------------------------------------------


async def test_mcp_call_get_contact_success_and_tenant_header(patch_env):
    """
    End-to-end: POST /mcp/call → tool dispatch → backend call.

    The ASGI app is started INSIDE the respx.mock() context so that the
    internal httpx.AsyncClient (created during lifespan) is intercepted
    by the mock router.

    Verifies:
    - HTTP 200 with correct result payload
    - X-Tenant-ID forwarded to backend
    - X-Internal-API-Key present on every backend call
    """
    from server import app

    mock_contact = {
        "id": VALID_CONTACT_ID,
        "org_id": VALID_TENANT_ID,
        "first_name": "Alice",
        "last_name": "Dupont",
        "email": "alice@example.com",
        "phone": None,
        "job_title": None,
        "account_id": None,
        "status": "active",
        "created_by": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f8a",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with respx.mock(base_url=MOCK_BACKEND_URL, assert_all_called=True) as backend:
        route = backend.get(f"/internal/v1/crm/contacts/{VALID_CONTACT_ID}").mock(
            return_value=httpx.Response(200, json=mock_contact)
        )

        async with LifespanManager(app) as manager:
            async with AsyncClient(
                transport=ASGITransport(app=manager.app),
                base_url="http://testserver",
            ) as test_client:
                response = await test_client.post(
                    "/mcp/call",
                    json={
                        "tool": "get_contact",
                        "params": {
                            "tenant_id": VALID_TENANT_ID,
                            "contact_id": VALID_CONTACT_ID,
                        },
                        "tenant_id": VALID_TENANT_ID,
                    },
                )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None
    assert data["result"]["contact"]["id"] == VALID_CONTACT_ID

    assert route.called
    backend_request = route.calls[0].request
    assert backend_request.headers["x-tenant-id"] == VALID_TENANT_ID
    assert backend_request.headers["x-internal-api-key"] == "test-internal-key"
