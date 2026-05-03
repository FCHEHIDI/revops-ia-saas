"""Tests for the API Keys feature.

Covers:
- Key generation format and uniqueness
- Key hashing determinism
- Scope validation
- CRUD via HTTP (dependency_overrides)
- Bearer token auth path (unit-level)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api_keys.service import generate_raw_key, hash_key
from app.api_keys.schemas import VALID_SCOPES
from app.auth.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.api_key import ApiKey
from app.auth.service import create_access_token
from tests.conftest import make_user, TENANT_A_ID


# ---------------------------------------------------------------------------
# Unit tests — pure functions
# ---------------------------------------------------------------------------


def test_generate_raw_key_format() -> None:
    key = generate_raw_key()
    assert key.startswith("rk_live_")
    assert len(key) > 40


def test_generate_raw_key_is_unique() -> None:
    keys = {generate_raw_key() for _ in range(50)}
    assert len(keys) == 50


def test_hash_key_is_deterministic() -> None:
    key = generate_raw_key()
    assert hash_key(key) == hash_key(key)


def test_hash_key_length_is_64() -> None:
    assert len(hash_key("rk_live_test")) == 64


def test_valid_scopes_set() -> None:
    assert "crm:read" in VALID_SCOPES
    assert "crm:write" in VALID_SCOPES
    assert "billing:read" in VALID_SCOPES
    assert "analytics:read" in VALID_SCOPES
    assert "sequences:write" in VALID_SCOPES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_key_obj(tenant_id, user_id, name="Test key", scopes=None):
    obj = MagicMock(spec=ApiKey)
    obj.id = uuid4()
    obj.tenant_id = tenant_id
    obj.created_by = user_id
    obj.name = name
    obj.scopes = scopes or ["crm:read"]
    obj.key_hash = hash_key("rk_live_dummy")
    obj.last_used_at = None
    obj.expires_at = None
    obj.active = True
    obj.created_at = datetime.now(timezone.utc)
    return obj


@pytest.fixture
def authed_user():
    """Override both auth dependencies with a mock user."""
    user = make_user(TENANT_A_ID)

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override
    app.dependency_overrides[get_current_active_user] = _override
    yield user
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


# ---------------------------------------------------------------------------
# HTTP integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_api_key_returns_plaintext_key_once(authed_user) -> None:
    key_obj = _make_api_key_obj(TENANT_A_ID, authed_user.id)
    raw_key = "rk_live_testrawkey"

    with patch(
        "app.api_keys.router.service.create_api_key",
        new_callable=AsyncMock,
        return_value=(key_obj, raw_key),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/api/v1/api-keys",
                json={"name": "Test key", "scopes": ["crm:read"]},
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["key"] == raw_key
    assert data["name"] == "Test key"


@pytest.mark.asyncio
async def test_create_api_key_rejects_invalid_scopes(authed_user) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/v1/api-keys",
            json={"name": "Bad key", "scopes": ["admin:all"]},
        )

    assert resp.status_code == 422
    assert "Invalid scopes" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_api_keys_no_plaintext(authed_user) -> None:
    keys = [_make_api_key_obj(TENANT_A_ID, authed_user.id, f"key-{i}") for i in range(3)]

    with patch(
        "app.api_keys.router.service.list_api_keys",
        new_callable=AsyncMock,
        return_value=keys,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/v1/api-keys")

    assert resp.status_code == 200
    assert len(resp.json()) == 3
    for item in resp.json():
        assert "key" not in item


@pytest.mark.asyncio
async def test_revoke_api_key_not_found(authed_user) -> None:
    with patch(
        "app.api_keys.router.service.revoke_api_key",
        new_callable=AsyncMock,
        return_value=False,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.delete(f"/api/v1/api-keys/{uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_api_key_success(authed_user) -> None:
    with patch(
        "app.api_keys.router.service.revoke_api_key",
        new_callable=AsyncMock,
        return_value=True,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.delete(f"/api/v1/api-keys/{uuid4()}")

    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Bearer token auth — unit test on the dependency function directly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bearer_api_key_calls_resolve() -> None:
    """get_current_user must call _resolve_api_key for rk_live_ bearer tokens."""
    user = make_user(TENANT_A_ID)
    raw_key = "rk_live_validtestkey"

    with patch(
        "app.auth.dependencies._resolve_api_key",
        new_callable=AsyncMock,
        return_value=user,
    ) as mock_resolve:
        from app.auth.dependencies import get_current_user as dep
        from fastapi import Request

        mock_db = AsyncMock()
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}
        mock_request.headers = {"Authorization": f"Bearer {raw_key}"}

        result = await dep(request=mock_request, db=mock_db)

    mock_resolve.assert_awaited_once_with(raw_key, mock_db)
    assert result is user
