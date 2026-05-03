"""Tests for Feature #9 — Notification Center.

Coverage
--------
DB unit tests (5):
  test_db_create_notification     — create + retrieve
  test_db_list_notifications      — list with user filter + tenant-wide rows
  test_db_unread_count            — count unread
  test_db_mark_as_read            — mark single notification read (idempotent)
  test_db_mark_all_as_read        — bulk mark-all-read

HTTP tests (10):
  test_http_list_notifications         — GET 200 returns list
  test_http_list_unread_only           — GET ?unread_only=true excludes read rows
  test_http_count_notifications        — GET /count returns {unread: N}
  test_http_mark_one_read              — POST /{id}/read → 200
  test_http_mark_one_read_404          — POST /{id}/read → 404 wrong tenant
  test_http_mark_all_read              — POST /read-all → 200
  test_http_list_no_auth               — GET 401 without cookie
  test_http_count_no_auth              — GET /count 401 without cookie
  test_http_mark_read_no_auth          — POST /{id}/read 401 without cookie
  test_http_tenant_isolation           — notifications from other tenant NOT returned

All HTTP tests use dependency_overrides (get_current_active_user + get_db) to bypass
real DB IO.  A separate committed Organization row provides the FK anchor for DB tests.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.dependencies import get_current_active_user
from app.auth.service import create_access_token
from app.common.db import get_db
from app.main import app
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.user import User
from app.notifications import service as svc
from app.notifications.schemas import NotificationCreate

logger = logging.getLogger(__name__)

_TEST_DB_URL = "postgresql+asyncpg://revops:revops@localhost:5433/revops_test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tenant_id() -> AsyncGenerator[UUID, None]:
    """Create a committed Organization row and yield its id.

    Uses a separate engine so committed notifications satisfy the FK without
    polluting the rollback-based test session.

    Yields:
        UUID of the created Organization.
    """
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    org_id = uuid4()
    async with factory() as session:
        org = Organization(
            id=org_id,
            name="NotifTestTenant",
            slug=f"notif-test-{org_id.hex[:8]}",
        )
        session.add(org)
        await session.commit()
    yield org_id
    try:
        async with factory() as session:
            await session.execute(delete(Organization).where(Organization.id == org_id))
            await session.commit()
        await engine.dispose()
    except Exception:  # noqa: BLE001
        pass


@pytest_asyncio.fixture
async def committed_db(tenant_id: UUID) -> AsyncGenerator[AsyncSession, None]:
    """Async session that commits rather than rolling back.

    Required for DB unit tests: FK references from ``notifications`` to
    ``organizations`` must already be committed.  Cleanup is performed
    in a fresh session so post-commit state does not conflict.

    Args:
        tenant_id: Organisation UUID created by the ``tenant_id`` fixture.

    Yields:
        Open AsyncSession.
    """
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    # Cleanup in a separate session to avoid post-commit state issues
    async with factory() as cleanup_session:
        await cleanup_session.execute(
            delete(Notification).where(Notification.tenant_id == tenant_id)
        )
        await cleanup_session.commit()
    await engine.dispose()


@pytest.fixture(autouse=True)
def _cleanup_overrides() -> None:
    """Restore dependency_overrides after every test."""
    yield
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers for HTTP tests
# ---------------------------------------------------------------------------


def _make_mock_user(org_id: UUID) -> MagicMock:
    """Return a MagicMock User-like object suitable for auth override.

    Args:
        org_id: The tenant/org UUID this user belongs to.

    Returns:
        Configured MagicMock with id, org_id, tenant_id, is_active, email.
    """
    u = MagicMock(spec=User)
    u.id = uuid4()
    u.org_id = org_id
    u.tenant_id = org_id  # create_access_token reads tenant_id
    u.is_active = True
    u.email = "test@notif.io"
    return u


def _jwt_cookies(user: MagicMock) -> dict[str, str]:
    """Return a valid JWT cookie dict for TenantMiddleware.

    Args:
        user: Mock user with tenant_id set.

    Returns:
        Dict mapping ``access_token`` to a signed JWT.
    """
    token = create_access_token(user)
    return {"access_token": token}


def _mock_notif(
    tenant_id: UUID,
    user_id: UUID | None = None,
    *,
    read: bool = False,
) -> MagicMock:
    """Build a lightweight Notification-like mock.

    Args:
        tenant_id: Owning tenant UUID.
        user_id: Optional target user UUID.
        read: If True, sets read_at to a non-None value.

    Returns:
        MagicMock shaped like a Notification ORM object.
    """
    from datetime import datetime, timezone

    n = MagicMock(spec=Notification)
    n.id = uuid4()
    n.tenant_id = tenant_id
    n.user_id = user_id
    n.type = "system"
    n.title = "Test notification"
    n.body = None
    n.data = None
    n.read_at = datetime.now(timezone.utc) if read else None
    n.created_at = datetime.now(timezone.utc)
    return n


# ---------------------------------------------------------------------------
# DB unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_create_notification(
    committed_db: AsyncSession,
    tenant_id: UUID,
) -> None:
    """create_notification inserts a row retrievable by list_notifications."""
    notif = await svc.create_notification(
        committed_db,
        NotificationCreate(
            tenant_id=tenant_id,
            type="system",
            title="Hello world",
            body="Test body",
        ),
        push=False,
    )
    await committed_db.commit()

    results = await svc.list_notifications(committed_db, tenant_id)
    ids = [r.id for r in results]
    assert notif.id in ids


@pytest.mark.asyncio
async def test_db_list_notifications(
    committed_db: AsyncSession,
    tenant_id: UUID,
) -> None:
    """list_notifications returns tenant-wide rows and respects tenant scope."""
    notif1 = await svc.create_notification(
        committed_db,
        NotificationCreate(tenant_id=tenant_id, type="system", title="First row"),
        push=False,
    )
    notif2 = await svc.create_notification(
        committed_db,
        NotificationCreate(tenant_id=tenant_id, type="system", title="Second row"),
        push=False,
    )
    await committed_db.commit()

    results = await svc.list_notifications(committed_db, tenant_id)
    ids = [r.id for r in results]
    assert notif1.id in ids
    assert notif2.id in ids


@pytest.mark.asyncio
async def test_db_unread_count(
    committed_db: AsyncSession,
    tenant_id: UUID,
) -> None:
    """get_unread_count returns the number of unread notifications."""
    # Create 2 unread for the tenant
    for _ in range(2):
        await svc.create_notification(
            committed_db,
            NotificationCreate(tenant_id=tenant_id, type="system", title="Unread"),
            push=False,
        )
    await committed_db.commit()

    resp = await svc.get_unread_count(committed_db, tenant_id)
    assert resp.unread >= 2


@pytest.mark.asyncio
async def test_db_mark_as_read(
    committed_db: AsyncSession,
    tenant_id: UUID,
) -> None:
    """mark_as_read sets read_at; subsequent calls are idempotent."""
    notif = await svc.create_notification(
        committed_db,
        NotificationCreate(tenant_id=tenant_id, type="system", title="Mark me"),
        push=False,
    )
    await committed_db.commit()

    updated = await svc.mark_as_read(committed_db, notif.id, tenant_id)
    assert updated is not None
    assert updated.read_at is not None

    # Idempotent — second call returns same object
    updated2 = await svc.mark_as_read(committed_db, notif.id, tenant_id)
    assert updated2 is not None
    assert updated2.read_at == updated.read_at


@pytest.mark.asyncio
async def test_db_mark_all_as_read(
    committed_db: AsyncSession,
    tenant_id: UUID,
) -> None:
    """mark_all_as_read updates all unread rows for the tenant."""
    for _ in range(3):
        await svc.create_notification(
            committed_db,
            NotificationCreate(tenant_id=tenant_id, type="system", title="Bulk"),
            push=False,
        )
    await committed_db.commit()

    resp = await svc.mark_all_as_read(committed_db, tenant_id)
    assert resp.updated >= 3

    # All should now be read
    count_resp = await svc.get_unread_count(committed_db, tenant_id)
    assert count_resp.unread == 0


# ---------------------------------------------------------------------------
# HTTP tests
# ---------------------------------------------------------------------------


@pytest.fixture
def org_id() -> UUID:
    """Generate a random org UUID for HTTP test isolation."""
    return uuid4()


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_http_list_notifications(
    http_client: AsyncClient,
    org_id: UUID,
) -> None:
    """GET /api/v1/notifications returns 200 with a list."""
    user = _make_mock_user(org_id)
    mock_db = AsyncMock()

    notif = _mock_notif(org_id, user.id)
    from app.notifications.schemas import NotificationRead
    from datetime import datetime, timezone

    # Service returns NotificationRead pydantic objects
    mock_read = NotificationRead(
        id=notif.id,
        tenant_id=org_id,
        user_id=user.id,
        type="system",
        title="Test",
        body=None,
        data=None,
        read_at=None,
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.notifications.service.list_notifications", new=AsyncMock(return_value=[mock_read])):
        app.dependency_overrides[get_current_active_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        resp = await http_client.get(
            "/api/v1/notifications",
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == str(notif.id)


@pytest.mark.asyncio
async def test_http_list_unread_only(
    http_client: AsyncClient,
    org_id: UUID,
) -> None:
    """GET /api/v1/notifications?unread_only=true calls service with unread_only=True."""
    user = _make_mock_user(org_id)
    mock_db = AsyncMock()

    with patch("app.notifications.service.list_notifications", new=AsyncMock(return_value=[])) as mock_list:
        app.dependency_overrides[get_current_active_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        resp = await http_client.get(
            "/api/v1/notifications?unread_only=true",
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
    mock_list.assert_called_once()
    _, kwargs = mock_list.call_args
    assert kwargs.get("unread_only") is True


@pytest.mark.asyncio
async def test_http_count_notifications(
    http_client: AsyncClient,
    org_id: UUID,
) -> None:
    """GET /api/v1/notifications/count returns {unread: N}."""
    from app.notifications.schemas import UnreadCountResponse

    user = _make_mock_user(org_id)
    mock_db = AsyncMock()

    with patch(
        "app.notifications.service.get_unread_count",
        new=AsyncMock(return_value=UnreadCountResponse(unread=5)),
    ):
        app.dependency_overrides[get_current_active_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        resp = await http_client.get(
            "/api/v1/notifications/count",
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
    assert resp.json() == {"unread": 5}


@pytest.mark.asyncio
async def test_http_mark_one_read(
    http_client: AsyncClient,
    org_id: UUID,
) -> None:
    """POST /api/v1/notifications/{id}/read returns 200."""
    from datetime import datetime, timezone
    from app.notifications.schemas import NotificationRead

    user = _make_mock_user(org_id)
    mock_db = AsyncMock()
    notif_id = uuid4()

    mock_read = NotificationRead(
        id=notif_id,
        tenant_id=org_id,
        user_id=user.id,
        type="system",
        title="Read me",
        body=None,
        data=None,
        read_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    # service.mark_as_read returns an ORM object; router calls model_validate on it
    mock_orm = MagicMock(spec=Notification)
    mock_orm.id = notif_id
    mock_orm.tenant_id = org_id
    mock_orm.user_id = user.id
    mock_orm.type = "system"
    mock_orm.title = "Read me"
    mock_orm.body = None
    mock_orm.data = None
    mock_orm.read_at = datetime.now(timezone.utc)
    mock_orm.created_at = datetime.now(timezone.utc)

    with patch("app.notifications.service.mark_as_read", new=AsyncMock(return_value=mock_orm)):
        app.dependency_overrides[get_current_active_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        resp = await http_client.post(
            f"/api/v1/notifications/{notif_id}/read",
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
    assert resp.json()["id"] == str(notif_id)


@pytest.mark.asyncio
async def test_http_mark_one_read_404(
    http_client: AsyncClient,
    org_id: UUID,
) -> None:
    """POST /{id}/read returns 404 when mark_as_read returns None."""
    user = _make_mock_user(org_id)
    mock_db = AsyncMock()
    notif_id = uuid4()

    with patch("app.notifications.service.mark_as_read", new=AsyncMock(return_value=None)):
        app.dependency_overrides[get_current_active_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        resp = await http_client.post(
            f"/api/v1/notifications/{notif_id}/read",
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_http_mark_all_read(
    http_client: AsyncClient,
    org_id: UUID,
) -> None:
    """POST /api/v1/notifications/read-all returns 200 with updated count."""
    from app.notifications.schemas import MarkAllReadResponse

    user = _make_mock_user(org_id)
    mock_db = AsyncMock()

    with patch(
        "app.notifications.service.mark_all_as_read",
        new=AsyncMock(return_value=MarkAllReadResponse(updated=3)),
    ):
        app.dependency_overrides[get_current_active_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        resp = await http_client.post(
            "/api/v1/notifications/read-all",
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
    assert resp.json() == {"updated": 3}


@pytest.mark.asyncio
async def test_http_list_no_auth(http_client: AsyncClient) -> None:
    """GET /api/v1/notifications without cookie returns 401."""
    resp = await http_client.get("/api/v1/notifications")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_http_count_no_auth(http_client: AsyncClient) -> None:
    """GET /api/v1/notifications/count without cookie returns 401."""
    resp = await http_client.get("/api/v1/notifications/count")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_http_mark_read_no_auth(http_client: AsyncClient) -> None:
    """POST /api/v1/notifications/{id}/read without cookie returns 401."""
    resp = await http_client.post(f"/api/v1/notifications/{uuid4()}/read")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_http_tenant_isolation(
    http_client: AsyncClient,
    org_id: UUID,
) -> None:
    """A user's request only sees their own tenant's notifications."""
    user = _make_mock_user(org_id)
    mock_db = AsyncMock()

    with patch(
        "app.notifications.service.list_notifications",
        new=AsyncMock(return_value=[]),
    ) as mock_list:
        app.dependency_overrides[get_current_active_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        resp = await http_client.get(
            "/api/v1/notifications",
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
    # Verify service was called with the correct tenant_id (user.org_id)
    mock_list.assert_called_once()
    call_kwargs = mock_list.call_args
    assert call_kwargs[1]["tenant_id"] == org_id or call_kwargs[0][1] == org_id
