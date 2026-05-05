"""Tests unitaires du module auth — router, cookies, service."""

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

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
    assert resp.json().get("detail") == "Incorrect email or password"


@pytest.mark.asyncio
@patch("app.auth.router.create_refresh_token", new_callable=AsyncMock)
@patch("app.auth.router.authenticate_user", new_callable=AsyncMock)
async def test_login_ignores_empty_mfa_code(
    mock_authenticate: AsyncMock,
    mock_create_refresh: AsyncMock,
    client: AsyncClient,
    user_tenant_a: User,
) -> None:
    mock_authenticate.return_value = user_tenant_a
    mock_create_refresh.return_value = "raw_refresh_token_value"

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": str(user_tenant_a.email),
            "password": "testpass",
            "mfa_code": "",
        },
    )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["email"] == str(user_tenant_a.email)


@pytest.mark.asyncio
@patch("app.auth.router.authenticate_user", new_callable=AsyncMock)
async def test_login_requires_mfa_code_when_enabled(
    mock_authenticate: AsyncMock,
    client: AsyncClient,
) -> None:
    user = User(
        id=uuid4(),
        email="sales@acme.io",
        password_hash="fake",
        full_name="Sales",
        org_id=uuid4(),
        is_active=True,
        mfa_enabled=True,
        mfa_secret="BASE32SECRET",
    )
    mock_authenticate.return_value = user

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "sales@acme.io", "password": "acme1234"},
    )

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert resp.json().get("detail") == "MFA code required"


@pytest.mark.asyncio
@patch("app.auth.router.authenticate_user", new_callable=AsyncMock)
async def test_login_requires_valid_mfa_code(
    mock_authenticate: AsyncMock,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        id=uuid4(),
        email="sales@acme.io",
        password_hash="fake",
        full_name="Sales",
        org_id=uuid4(),
        is_active=True,
        mfa_enabled=True,
        mfa_secret="BASE32SECRET",
    )
    mock_authenticate.return_value = user
    monkeypatch.setattr("app.auth.router.verify_mfa_code", lambda secret, code: False)

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "sales@acme.io", "password": "acme1234", "mfa_code": "000000"},
    )

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert resp.json().get("detail") == "Invalid MFA code"


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

    user_tenant_a.roles = ["sales"]
    user_tenant_a.permissions = ["crm:accounts:read"]

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
    payload = resp.json()
    assert payload["roles"] == ["sales"]
    assert payload["permissions"] == ["crm:accounts:read"]


@pytest.mark.asyncio
async def test_me_permissions_admin_debug_disabled_returns_404(
    client: AsyncClient,
    user_tenant_a: User,
    auth_cookies_tenant_a: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.auth import router as auth_router
    from app.auth.dependencies import get_current_active_user
    from app.main import app as fastapi_app

    user_tenant_a.roles = ["admin"]
    user_tenant_a.permissions = ["read:reports"]

    async def override_active_user() -> User:
        return user_tenant_a

    fastapi_app.dependency_overrides[get_current_active_user] = override_active_user
    monkeypatch.setattr(auth_router.settings, "admin_debug_enabled", False)
    try:
        resp = await client.get(
            "/api/v1/auth/me/permissions",
            cookies=auth_cookies_tenant_a,
        )
    finally:
        fastapi_app.dependency_overrides.pop(get_current_active_user, None)

    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_me_permissions_with_admin_debug_enabled_forbidden_for_non_admin(
    client: AsyncClient,
    user_tenant_a: User,
    auth_cookies_tenant_a: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.auth import router as auth_router
    from app.auth.dependencies import get_current_active_user
    from app.main import app as fastapi_app

    user_tenant_a.roles = ["sales"]
    user_tenant_a.permissions = ["crm:accounts:read"]

    async def override_active_user() -> User:
        return user_tenant_a

    fastapi_app.dependency_overrides[get_current_active_user] = override_active_user
    monkeypatch.setattr(auth_router.settings, "admin_debug_enabled", True)
    try:
        resp = await client.get(
            "/api/v1/auth/me/permissions",
            cookies=auth_cookies_tenant_a,
        )
    finally:
        fastapi_app.dependency_overrides.pop(get_current_active_user, None)

    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_me_permissions_with_admin_debug_enabled_returns_permissions(
    client: AsyncClient,
    user_tenant_a: User,
    auth_cookies_tenant_a: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.auth import router as auth_router
    from app.auth.dependencies import get_current_active_user
    from app.main import app as fastapi_app

    user_tenant_a.roles = ["admin"]
    user_tenant_a.permissions = ["read:reports"]

    async def override_active_user() -> User:
        return user_tenant_a

    fastapi_app.dependency_overrides[get_current_active_user] = override_active_user
    monkeypatch.setattr(auth_router.settings, "admin_debug_enabled", True)
    try:
        resp = await client.get(
            "/api/v1/auth/me/permissions",
            cookies=auth_cookies_tenant_a,
        )
    finally:
        fastapi_app.dependency_overrides.pop(get_current_active_user, None)

    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == ["read:reports"]


@pytest.mark.asyncio
async def test_me_roles_with_admin_debug_enabled_returns_roles(
    client: AsyncClient,
    user_tenant_a: User,
    auth_cookies_tenant_a: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.auth import router as auth_router
    from app.auth.dependencies import get_current_active_user
    from app.main import app as fastapi_app

    user_tenant_a.roles = ["admin"]
    user_tenant_a.permissions = ["read:reports"]

    async def override_active_user() -> User:
        return user_tenant_a

    fastapi_app.dependency_overrides[get_current_active_user] = override_active_user
    monkeypatch.setattr(auth_router.settings, "admin_debug_enabled", True)
    try:
        resp = await client.get(
            "/api/v1/auth/me/roles",
            cookies=auth_cookies_tenant_a,
        )
    finally:
        fastapi_app.dependency_overrides.pop(get_current_active_user, None)

    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == ["admin"]


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


def test_validate_password_format_rejects_weak_password() -> None:
    from app.auth.validation import validate_password_format

    with pytest.raises(ValueError):
        validate_password_format("simplepass")


def test_generate_and_verify_mfa_code() -> None:
    from app.auth.service import generate_mfa_secret, get_totp, verify_mfa_code

    secret = generate_mfa_secret()
    code = get_totp(secret).now()

    assert verify_mfa_code(secret, code)
    assert not verify_mfa_code(secret, "000000")

@pytest.mark.asyncio
async def test_authenticate_user_requires_mfa_code_when_enabled(
    user_tenant_a: User,
) -> None:
    from app.auth.service import authenticate_user, generate_mfa_secret, get_password_hash, get_totp

    user_tenant_a.email = "mfa@example.com"
    user_tenant_a.password_hash = get_password_hash("StrongPass123!")
    user_tenant_a.mfa_enabled = True
    user_tenant_a.mfa_secret = generate_mfa_secret()

    class DummyResult:
        def __init__(self, value: User) -> None:
            self._value = value

        def scalar_one_or_none(self) -> User:
            return self._value

    class DummyDB:
        async def execute(self, query):
            return DummyResult(user_tenant_a)

    assert (
        await authenticate_user(
            DummyDB(), user_tenant_a.email, "StrongPass123!", None
        )
        is None
    )
    assert (
        await authenticate_user(
            DummyDB(), user_tenant_a.email, "StrongPass123!", get_totp(user_tenant_a.mfa_secret).now()
        )
        == user_tenant_a
    )


def test_permissions_for_roles_combines_permissions() -> None:
    from app.auth.roles import permissions_for_roles

    permissions = permissions_for_roles(["admin", "sales"])

    assert "crm:accounts:read" in permissions
    assert "analytics:view" in permissions
    assert "crm:deals:write" in permissions
    assert len(permissions) == len(set(permissions))
    assert permissions == sorted(permissions)
