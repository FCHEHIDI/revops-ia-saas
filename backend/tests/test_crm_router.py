import os

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_crm_accounts_list() -> None:
    """Verify the internal CRM accounts endpoint is reachable with a valid API key.

    Uses GET /accounts (no write-permission dependency) so the test is not
    coupled to RBAC seed data.  Returns 200 with a paginated envelope even
    when the tenant has no accounts yet.
    """
    headers = {
        "X-Internal-API-Key": os.environ.get("INTERNAL_API_KEY", "changeme-internal-api-key"),
        "X-Tenant-ID": "00000000-0000-0000-0000-000000000001",
        "X-User-ID": "00000000-0000-0000-0000-000000000010",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        r = await ac.get("/internal/v1/crm/accounts", headers=headers)

    assert r.status_code == status.HTTP_200_OK
    data = r.json()
    # Paginated envelope must contain an items list
    assert "items" in data
    assert isinstance(data["items"], list)
