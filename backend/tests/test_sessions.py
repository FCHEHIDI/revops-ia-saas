"""Comprehensive session endpoint tests.

Coverage:
- POST /sessions/                — create session (happy path + no auth)
- GET  /sessions/                — list sessions
- GET  /sessions/{id}            — get single session + tenant isolation
- DELETE /sessions/{id}          — delete (owner, wrong owner, cross-tenant, not found)
- POST /sessions/{id}/messages   — batch persist (happy path, cross-tenant 403, 404)
- POST /sessions/{id}/chat       — chat proxy: 404 on missing/cross-tenant session,
                                   happy path with mocked orchestrator SSE

All tests use dependency_overrides (get_current_user + get_db) to bypass real DB and auth.
The JWT middleware still runs — tests supply a valid cookie to pass it, then the
overridden get_current_user governs what user state the handler actually sees.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.auth.service import create_access_token
from app.common.db import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.user import User
from app.sessions.models import UserSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_user(user_id: UUID, tenant_id: UUID) -> User:
    """Return a MagicMock User suitable for create_access_token."""
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = f"user_{user_id}@test.io"
    u.tenant_id = tenant_id
    u.is_active = True
    u.full_name = "Test User"
    return u  # type: ignore[return-value]


def _jwt_cookie(user_id: UUID, tenant_id: UUID) -> dict[str, str]:
    """Create a signed JWT cookie to satisfy TenantMiddleware."""
    token = create_access_token(_make_mock_user(user_id, tenant_id))
    return {"access_token": token}


def _user_state(user_id: UUID, tenant_id: UUID) -> dict:
    """Return the dict get_current_user normally produces."""
    return {"user_id": user_id, "tenant_id": tenant_id, "permissions": []}


def _make_session(user_id: UUID, org_id: UUID, messages: list | None = None) -> UserSession:
    """Instantiate a real (not mock) UserSession ORM object."""
    return UserSession(
        id=uuid4(),
        user_id=user_id,
        org_id=org_id,
        title="Test session",
        messages=messages or [],
        created_at=datetime.now(timezone.utc),
    )


def _db_mock(session: UserSession | None) -> tuple:
    """Return (async_override_fn, mock_db_session).

    Configures the async session mock so that:
    - execute().scalar_one_or_none() -> session (or None)
    - execute().scalars().all()      -> [session] (or [])
    - add / commit / refresh / delete are AsyncMock no-ops
    """
    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = session
    result.scalars.return_value = MagicMock(
        all=MagicMock(return_value=[session] if session else [])
    )
    mock_db.execute = AsyncMock(return_value=result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()
    mock_db.rollback = AsyncMock()

    async def _override():
        yield mock_db

    return _override, mock_db


@pytest.fixture(autouse=True)
def _cleanup_overrides():
    """Restore dependency_overrides after every test."""
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# POST /sessions/ — create session
# ---------------------------------------------------------------------------

async def test_create_session_returns_201(client: AsyncClient) -> None:
    """POST /sessions/ with a valid auth creates a session (201)."""
    uid, tid = uuid4(), uuid4()
    db_override, _ = _db_mock(None)  # create_session never calls get_session

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.post(
        "/api/v1/sessions/",
        cookies=_jwt_cookie(uid, tid),
        json={"title": "My chat"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My chat"
    assert data["messages"] == []


async def test_create_session_without_cookie_returns_401(client: AsyncClient) -> None:
    """POST /sessions/ without a JWT cookie is rejected by TenantMiddleware (401)."""
    resp = await client.post("/api/v1/sessions/", json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /sessions/ — list sessions
# ---------------------------------------------------------------------------

async def test_list_sessions_returns_200(client: AsyncClient) -> None:
    """GET /sessions/ returns 200 with a list."""
    uid, tid = uuid4(), uuid4()
    session = _make_session(uid, tid)
    db_override, _ = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.get("/api/v1/sessions/", cookies=_jwt_cookie(uid, tid))

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# GET /sessions/{id} — tenant isolation
# ---------------------------------------------------------------------------

async def test_get_owned_session_returns_200(client: AsyncClient) -> None:
    """GET /sessions/{id} returns 200 with session data when the user owns it."""
    uid, tid = uuid4(), uuid4()
    session = _make_session(uid, tid)
    db_override, _ = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.get(f"/api/v1/sessions/{session.id}", cookies=_jwt_cookie(uid, tid))

    assert resp.status_code == 200
    assert resp.json()["id"] == str(session.id)
    assert resp.json()["title"] == "Test session"


async def test_get_session_cross_tenant_returns_404(client: AsyncClient) -> None:
    """Tenant B cannot read Tenant A's session — 404 (no information leakage)."""
    uid_a, tid_a = uuid4(), uuid4()
    uid_b, tid_b = uuid4(), uuid4()

    session = _make_session(uid_a, tid_a)
    db_override, _ = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid_b, tid_b)
    app.dependency_overrides[get_db] = db_override

    resp = await client.get(f"/api/v1/sessions/{session.id}", cookies=_jwt_cookie(uid_b, tid_b))

    assert resp.status_code == 404


async def test_get_nonexistent_session_returns_404(client: AsyncClient) -> None:
    uid, tid = uuid4(), uuid4()
    db_override, _ = _db_mock(None)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.get(f"/api/v1/sessions/{uuid4()}", cookies=_jwt_cookie(uid, tid))

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /sessions/{id}
# ---------------------------------------------------------------------------

async def test_delete_owned_session_returns_204(client: AsyncClient) -> None:
    """DELETE /sessions/{id} returns 204 and actually calls db.delete."""
    uid, tid = uuid4(), uuid4()
    session = _make_session(uid, tid)
    db_override, mock_db = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.delete(f"/api/v1/sessions/{session.id}", cookies=_jwt_cookie(uid, tid))

    assert resp.status_code == 204
    mock_db.delete.assert_called_once_with(session)
    mock_db.commit.assert_called()


async def test_delete_session_wrong_user_same_tenant_returns_404(client: AsyncClient) -> None:
    """User cannot delete another user's session even within the same tenant."""
    tid = uuid4()
    owner_uid = uuid4()
    other_uid = uuid4()

    session = _make_session(owner_uid, tid)
    db_override, mock_db = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(other_uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.delete(
        f"/api/v1/sessions/{session.id}", cookies=_jwt_cookie(other_uid, tid)
    )

    assert resp.status_code == 404
    mock_db.delete.assert_not_called()


async def test_delete_session_cross_tenant_returns_404(client: AsyncClient) -> None:
    """Tenant B cannot delete Tenant A's session."""
    uid_a, tid_a = uuid4(), uuid4()
    uid_b, tid_b = uuid4(), uuid4()

    session = _make_session(uid_a, tid_a)
    db_override, mock_db = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid_b, tid_b)
    app.dependency_overrides[get_db] = db_override

    resp = await client.delete(f"/api/v1/sessions/{session.id}", cookies=_jwt_cookie(uid_b, tid_b))

    assert resp.status_code == 404
    mock_db.delete.assert_not_called()


async def test_delete_nonexistent_session_returns_404(client: AsyncClient) -> None:
    uid, tid = uuid4(), uuid4()
    db_override, _ = _db_mock(None)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.delete(f"/api/v1/sessions/{uuid4()}", cookies=_jwt_cookie(uid, tid))

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /sessions/{id}/messages — batch persist
# ---------------------------------------------------------------------------

async def test_batch_persist_appends_messages(client: AsyncClient) -> None:
    """POST /sessions/{id}/messages appends messages and returns updated session."""
    uid, tid = uuid4(), uuid4()
    session = _make_session(uid, tid)
    db_override, mock_db = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    payload = {
        "messages": [
            {"role": "user", "content": "Hello Xenito"},
            {"role": "assistant", "content": "Hello! How can I help?"},
        ]
    }

    resp = await client.post(
        f"/api/v1/sessions/{session.id}/messages",
        cookies=_jwt_cookie(uid, tid),
        json=payload,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "Hello Xenito"
    assert data["messages"][1]["role"] == "assistant"
    mock_db.commit.assert_called()


async def test_batch_persist_empty_list_returns_200(client: AsyncClient) -> None:
    """An empty messages array is valid and returns 200."""
    uid, tid = uuid4(), uuid4()
    session = _make_session(uid, tid)
    db_override, _ = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.post(
        f"/api/v1/sessions/{session.id}/messages",
        cookies=_jwt_cookie(uid, tid),
        json={"messages": []},
    )

    assert resp.status_code == 200


async def test_batch_persist_cross_tenant_returns_403(client: AsyncClient) -> None:
    """User from Tenant B cannot write to Tenant A's session — 403."""
    uid_a, tid_a = uuid4(), uuid4()
    uid_b, tid_b = uuid4(), uuid4()

    session = _make_session(uid_a, tid_a)
    db_override, _ = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid_b, tid_b)
    app.dependency_overrides[get_db] = db_override

    resp = await client.post(
        f"/api/v1/sessions/{session.id}/messages",
        cookies=_jwt_cookie(uid_b, tid_b),
        json={"messages": [{"role": "user", "content": "Injection attempt"}]},
    )

    assert resp.status_code == 403


async def test_batch_persist_nonexistent_session_returns_404(client: AsyncClient) -> None:
    uid, tid = uuid4(), uuid4()
    db_override, _ = _db_mock(None)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.post(
        f"/api/v1/sessions/{uuid4()}/messages",
        cookies=_jwt_cookie(uid, tid),
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /sessions/{id}/chat — orchestrator proxy (SSE)
# ---------------------------------------------------------------------------

async def test_chat_session_not_found_returns_404(client: AsyncClient) -> None:
    """Chat on a non-existent session returns 404 before hitting the orchestrator."""
    uid, tid = uuid4(), uuid4()
    db_override, _ = _db_mock(None)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    resp = await client.post(
        f"/api/v1/sessions/{uuid4()}/chat",
        cookies=_jwt_cookie(uid, tid),
        json={"role": "user", "content": "Hello"},
    )

    assert resp.status_code == 404


async def test_chat_cross_tenant_session_returns_404(client: AsyncClient) -> None:
    """Tenant B cannot chat through Tenant A's session — 404."""
    uid_a, tid_a = uuid4(), uuid4()
    uid_b, tid_b = uuid4(), uuid4()

    session = _make_session(uid_a, tid_a)
    db_override, _ = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid_b, tid_b)
    app.dependency_overrides[get_db] = db_override

    resp = await client.post(
        f"/api/v1/sessions/{session.id}/chat",
        cookies=_jwt_cookie(uid_b, tid_b),
        json={"role": "user", "content": "Injection attempt"},
    )

    assert resp.status_code == 404


async def test_chat_streams_orchestrator_sse(client: AsyncClient) -> None:
    """Happy path: orchestrator SSE tokens are forwarded to the caller."""
    uid, tid = uuid4(), uuid4()
    session = _make_session(uid, tid)
    db_override, _ = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    # Simulated orchestrator SSE output
    sse_lines = [
        'data: {"type":"token","content":"Hello"}',
        'data: {"type":"token","content":" world"}',
        'data: {"type":"done","usage":{"input_tokens":5,"output_tokens":2}}',
    ]

    async def _aiter_lines():
        for line in sse_lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = _aiter_lines

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_http_client = MagicMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    # Mock AsyncSessionLocal so the persist-assistant finalizer doesn't open a real connection
    persist_session = AsyncMock()
    persist_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=session))
    )
    persist_session.add = MagicMock()
    persist_session.commit = AsyncMock()
    persist_session.refresh = AsyncMock()

    mock_sl_ctx = AsyncMock()
    mock_sl_ctx.__aenter__ = AsyncMock(return_value=persist_session)
    mock_sl_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("httpx.AsyncClient", return_value=mock_client_ctx),
        patch("app.common.db.AsyncSessionLocal", return_value=mock_sl_ctx),
    ):
        resp = await client.post(
            f"/api/v1/sessions/{session.id}/chat",
            cookies=_jwt_cookie(uid, tid),
            json={"role": "user", "content": "Hi Xenito"},
        )

    assert resp.status_code == 200
    body = resp.text
    assert "Hello" in body
    assert "world" in body


async def test_chat_orchestrator_error_streams_error_event(client: AsyncClient) -> None:
    """When the orchestrator returns non-200, an SSE error event is forwarded."""
    uid, tid = uuid4(), uuid4()
    session = _make_session(uid, tid)
    db_override, _ = _db_mock(session)

    app.dependency_overrides[get_current_user] = lambda: _user_state(uid, tid)
    app.dependency_overrides[get_db] = db_override

    mock_resp = MagicMock()
    mock_resp.status_code = 503

    async def _empty_lines():
        return
        yield  # make it a valid async generator

    mock_resp.aiter_lines = _empty_lines

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_http_client = MagicMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client_ctx):
        resp = await client.post(
            f"/api/v1/sessions/{session.id}/chat",
            cookies=_jwt_cookie(uid, tid),
            json={"role": "user", "content": "Hello"},
        )

    # The endpoint returns 200 with a streaming body; error details are inside the stream
    assert resp.status_code == 200
    assert "error" in resp.text
    assert "503" in resp.text
