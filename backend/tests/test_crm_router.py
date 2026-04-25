import pytest
from httpx import AsyncClient
from backend.app.main import app
from fastapi import status
from asgi_lifespan import LifespanManager

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.asyncio
async def test_crm_accounts_flow(monkeypatch):
    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Patch DB, inject headers
            headers = {
                "X-Internal-API-Key": "changeme-internal-api-key",
                "X-Tenant-ID": "00000000-0000-0000-0000-000000000001",
                "X-User-ID": "00000000-0000-0000-0000-000000000010",
            }
            body = {"name": "ACME", "domain": "acme.io"}
            r = await ac.post("/internal/v1/crm/accounts", json=body, headers=headers)
            assert r.status_code == status.HTTP_200_OK or r.status_code == 201
            data = r.json()
            account_id = data["id"]
            # GET by ID
            r = await ac.get(f"/internal/v1/crm/accounts/{account_id}", headers=headers)
            assert r.status_code == 200
            assert r.json()["name"] == "ACME"
