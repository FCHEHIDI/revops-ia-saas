"""Tests unitaires du module auth — router, cookies, service."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
@patch("app.auth.router.authenticate_user", new_callable=AsyncMock)
@patch("app.auth.router.create_refresh_token", new_callable=AsyncMock)
async def test_login_success(
    mock_create_refresh: AsyncMock,
    mock_authenticate: AsyncMock,
    client: AsyncClient,
    user_tenant_a: User,
) -> None:
    mock_authenticate.return_value = user_tenant_a
    mock_create_refresh.return_value = "raw_refresh_token_value"

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": str(user_tenant_a.email), "password": "testpass"},
    )

    assert resp.status_code == status.HTTP_200_OK
    set_cookie_headers = resp.headers.get_list("set-cookie")
    combined = " ".join(set_cookie_headers)
    assert "HttpOnly" in combined
    assert (
        "SameSite=lax" in combined.lower() or "samesite=lax" in combined.lower()
    )


@pytest.mark.asyncio
@patch("app.auth.router.authenticate_user", new_callable=AsyncMock)
async def test_login_wrong_credentials(
    mock_authenticate: AsyncMock,
    client: AsyncClient,
) -> None:
    mock_authenticate.return_value = None

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "bad@example.com", "password": "wrong"},
    )

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
@patch("app.auth.router.refresh_tokens", new_callable=AsyncMock)
async def test_refresh_success(
    mock_refresh_tokens: AsyncMock,
    client: AsyncClient,
) -> None:
    mock_refresh_tokens.return_value = ("new_access_token", "new_refresh_token")

    resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": "old_valid_refresh"},
    )

    assert resp.status_code == status.HTTP_200_OK
    set_cookie_headers = resp.headers.get_list("set-cookie")
    combined = " ".join(set_cookie_headers)
    assert "HttpOnly" in combined
    assert "samesite=lax" in combined.lower()


@pytest.mark.asyncio
async def test_refresh_missing_cookie(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
@patch("app.auth.router.refresh_tokens", new_callable=AsyncMock)
async def test_refresh_revoked_token(
    mock_refresh_tokens: AsyncMock,
    client: AsyncClient,
) -> None:
    from fastapi import HTTPException

    mock_refresh_tokens.side_effect = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": "revoked_token"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
@patch("app.auth.router.revoke_refresh_token", new_callable=AsyncMock)
async def test_logout_clears_cookies(
    mock_revoke: AsyncMock,
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/auth/logout",
        cookies={"refresh_token": "some_refresh"},
    )

    assert resp.status_code == status.HTTP_200_OK
    set_cookie_headers = resp.headers.get_list("set-cookie")
    combined = " ".join(set_cookie_headers)
    # Les cookies doivent être expirés (max-age=0 ou expires passé)
    assert "max-age=0" in combined.lower() or "expires=" in combined.lower()


@pytest.mark.asyncio
@patch("app.auth.router.revoke_refresh_token", new_callable=AsyncMock)
async def test_logout_without_refresh_cookie(
    mock_revoke: AsyncMock,
    client: AsyncClient,
) -> None:
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == status.HTTP_200_OK
    mock_revoke.assert_not_called()


@pytest.mark.asyncio
async def test_me_returns_user(
    client: AsyncClient,
    user_tenant_a: User,
    auth_cookies_tenant_a: dict[str, str],
) -> None:
    from app.auth.dependencies import get_current_active_user
    from app.main import app as fastapi_app

    async def override_active_user() -> User:
        return user_tenant_a

    fastapi_app.dependency_overrides[get_current_active_user] = override_active_user
    try:
        resp = await client.get(
            "/api/v1/auth/me",
            cookies=auth_cookies_tenant_a,
        )
    finally:
        fastapi_app.dependency_overrides.pop(get_current_active_user, None)

    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient) -> None:
    """Sans cookie, le middleware renvoie 401 avant même d'atteindre /me."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_service_create_access_token_contains_tenant_id(user_tenant_a: User) -> None:
    from app.auth.service import create_access_token, verify_access_token

    token = create_access_token(user_tenant_a)
    payload = verify_access_token(token)

    assert payload.sub == user_tenant_a.id
    assert payload.tenant_id == user_tenant_a.tenant_id
    assert payload.type == "access"


def test_service_verify_invalid_token_raises() -> None:
    from fastapi import HTTPException

    from app.auth.service import verify_access_token

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token("totally.invalid.token")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_service_hash_refresh_token_is_deterministic() -> None:
    from app.auth.service import _hash_refresh_token  # type: ignore[attr-defined]

    raw = "my_raw_refresh_token"
    assert _hash_refresh_token(raw) == _hash_refresh_token(raw)
    assert _hash_refresh_token(raw) != _hash_refresh_token("other_token")
