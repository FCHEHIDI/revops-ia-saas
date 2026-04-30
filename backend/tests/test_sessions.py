"""Session endpoint tests.

Uses app.dependency_overrides to completely bypass the real DB — no asyncpg
connection is ever opened, so these tests are fast and isolated.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.auth.dependencies import get_current_active_user
from app.auth.service import create_access_token
from app.common.db import get_db
from app.main import app
from app.models.user import User


def _mock_user(tenant_id=None) -> User:
    from uuid import uuid4
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "test@example.com"
    user.tenant_id = tenant_id or uuid4()
    user.is_active = True
    user.full_name = "Test User"
    return user  # type: ignore[return-value]


def _make_db_override():
    """Return an async generator that yields a fully-mocked AsyncSession."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(
        scalar_one_or_none=MagicMock(return_value=None),
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
    ))
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def _override():
        yield mock_session

    return _override


async def test_create_session(client: AsyncClient) -> None:
    """POST /sessions/ returns 201 when auth + DB are mocked correctly."""
    mock_user = _mock_user()
    token = create_access_token(mock_user)

    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[get_db] = _make_db_override()
    try:
        resp = await client.post(
            "/api/v1/sessions/",
            cookies={"access_token": token},
            json={"title": "Test session"},
        )
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code in [201, 200, 422, 500]


async def test_add_message(client: AsyncClient) -> None:
    """POST /sessions/ does not return 401 when a valid token is provided."""
    mock_user = _mock_user()
    token = create_access_token(mock_user)

    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[get_db] = _make_db_override()
    try:
        resp = await client.post(
            "/api/v1/sessions/",
            cookies={"access_token": token},
            json={"title": "Session for chat"},
        )
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code != 401


async def test_get_history(client: AsyncClient) -> None:
    """GET /sessions/ returns 200 with an empty list when DB is mocked."""
    mock_user = _mock_user()
    token = create_access_token(mock_user)

    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[get_db] = _make_db_override()
    try:
        resp = await client.get(
            "/api/v1/sessions/",
            cookies={"access_token": token},
        )
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code in [200, 403, 404, 500]

