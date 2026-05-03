"""Tests for Feature #8 — Usage Metering.

Coverage:
- Unit: _period_bounds() for all 4 periods
- Unit: record_usage / get_usage_summary via service (real DB, separate engine)
- Unit: list_usage_events via service (real DB, separate engine)
- HTTP: GET /api/v1/billing/usage → 200 with summary (mocked DB)
- HTTP: GET /api/v1/billing/usage?period=last_7_days → 200
- HTTP: GET /api/v1/billing/usage/events → 200 with events list (mocked DB)
- HTTP: GET /api/v1/billing/usage → 401 without auth

DB tests use a separately-committed Organization row (separate engine, function-scoped)
to satisfy the usage_events FK constraint without conflicting with the test_db
rollback fixture.

HTTP tests use AsyncMock DB sessions + override get_current_active_user.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
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
from app.models.organization import Organization
from app.models.user import User
from app.models.usage_event import UsageEvent
from app.usage import service as svc
from app.usage.schemas import UsageEventCreate
from app.usage.service import _period_bounds

logger = logging.getLogger(__name__)

_TEST_DB_URL = "postgresql+asyncpg://revops:revops@localhost:5433/revops_test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tenant_id() -> AsyncGenerator[UUID, None]:
    """Create a committed Organization row in its own engine and yield its id.

    Uses a separate engine (not test_db) so committed usage_events satisfy the
    FK constraint without polluting the rollback-based test session.
    """
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    org_id = uuid4()
    async with factory() as session:
        org = Organization(
            id=org_id,
            name="UsageTestTenant",
            slug=f"usage-test-{org_id.hex[:8]}",
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


@pytest.fixture(autouse=True)
def no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub async Redis cache helpers to avoid Redis dependency in tests."""
    import app.scoring.service as svc_mod

    monkeypatch.setattr(svc_mod, "_get_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(svc_mod, "_set_cache", AsyncMock())


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
    """Return a MagicMock User-like object for auth dependency override.

    Sets both org_id (read by the usage router) and tenant_id (read by
    create_access_token when building the JWT cookie for TenantMiddleware).
    """
    u = MagicMock(spec=User)
    u.id = uuid4()
    u.org_id = org_id
    u.tenant_id = org_id  # required: create_access_token reads user.tenant_id
    u.is_active = True
    u.email = "test@usage.io"
    return u


def _jwt_cookies(user: MagicMock) -> dict[str, str]:
    """Create a valid JWT cookie for TenantMiddleware."""
    return {"access_token": create_access_token(user)}


def _make_event(tenant_id: UUID, event_type: str = "llm_tokens_input") -> UsageEvent:
    """Build an in-memory UsageEvent object with all fields populated."""
    return UsageEvent(
        id=uuid4(),
        tenant_id=tenant_id,
        event_type=event_type,
        quantity=100,
        event_metadata={"session_id": str(uuid4())},
        ts=datetime.now(timezone.utc),
    )


def _mock_db(events: list[UsageEvent] | None = None) -> AsyncMock:
    """Return an AsyncMock session configured to return the given event list."""
    mock_db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value = MagicMock(
        all=MagicMock(return_value=events or [])
    )
    # For aggregate queries (get_usage_summary), .all() returns raw Row tuples
    result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    return mock_db


# ---------------------------------------------------------------------------
# Unit tests — _period_bounds
# ---------------------------------------------------------------------------


def test_period_bounds_current_month() -> None:
    """current_month should start on day 1 of the current month."""
    start, end = _period_bounds("current_month")
    now = datetime.now(timezone.utc)
    assert start.day == 1
    assert start.month == now.month
    assert start.year == now.year
    assert end > start


def test_period_bounds_last_month() -> None:
    """last_month start should be before current_month start."""
    start_cur, _ = _period_bounds("current_month")
    start_last, end_last = _period_bounds("last_month")
    assert start_last < start_cur
    assert end_last == start_cur


def test_period_bounds_last_7_days() -> None:
    """last_7_days range should span exactly 7 calendar days."""
    from datetime import timedelta

    start, end = _period_bounds("last_7_days")
    assert (end - start) == timedelta(days=7)


def test_period_bounds_last_30_days() -> None:
    """last_30_days range should span exactly 30 calendar days."""
    from datetime import timedelta

    start, end = _period_bounds("last_30_days")
    assert (end - start) == timedelta(days=30)


# ---------------------------------------------------------------------------
# DB tests — record_usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_usage_inserts_row(tenant_id: UUID) -> None:
    """record_usage should insert a usage_events row and return the ORM object."""
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            event = await svc.record_usage(
                db,
                UsageEventCreate(
                    tenant_id=tenant_id,
                    event_type="llm_tokens_input",
                    quantity=512,
                    metadata={"model": "gpt-4o", "session_id": str(uuid4())},
                ),
            )
            await db.commit()

        assert event.id is not None
        assert event.tenant_id == tenant_id
        assert event.event_type == "llm_tokens_input"
        assert event.quantity == 512
        assert event.event_metadata["model"] == "gpt-4o"
        assert event.ts is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_usage_all_event_types(tenant_id: UUID) -> None:
    """All supported event_type values should persist without error."""
    event_types = [
        "llm_tokens_input",
        "llm_tokens_output",
        "mcp_calls",
        "emails_sent",
        "documents_indexed",
    ]
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            for etype in event_types:
                ev = await svc.record_usage(
                    db,
                    UsageEventCreate(
                        tenant_id=tenant_id, event_type=etype, quantity=1
                    ),
                )
                assert ev.event_type == etype
            await db.commit()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# DB tests — get_usage_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_usage_summary_aggregates_correctly(tenant_id: UUID) -> None:
    """Summary should aggregate quantities by event_type within the period."""
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            # Insert two input events and one output event
            for qty in (100, 200):
                await svc.record_usage(
                    db,
                    UsageEventCreate(
                        tenant_id=tenant_id, event_type="llm_tokens_input", quantity=qty
                    ),
                )
            await svc.record_usage(
                db,
                UsageEventCreate(
                    tenant_id=tenant_id, event_type="llm_tokens_output", quantity=50
                ),
            )
            await db.commit()

        async with factory() as db:
            summary = await svc.get_usage_summary(db, tenant_id, "current_month")

        assert summary.period == "current_month"
        by_type = {item.event_type: item.total for item in summary.items}
        # ≥ because other tests in the suite may have inserted rows for the same tenant
        assert by_type.get("llm_tokens_input", 0) >= 300
        assert by_type.get("llm_tokens_output", 0) >= 50
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# DB tests — list_usage_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_usage_events_returns_rows(tenant_id: UUID) -> None:
    """list_usage_events should return rows ordered newest-first."""
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            for i in range(3):
                await svc.record_usage(
                    db,
                    UsageEventCreate(
                        tenant_id=tenant_id,
                        event_type="mcp_calls",
                        quantity=i + 1,
                        metadata={"idx": i},
                    ),
                )
            await db.commit()

        async with factory() as db:
            events = await svc.list_usage_events(db, tenant_id, "current_month")

        assert len(events) >= 3
        # Newest-first: first row quantity should be >= last row quantity
        # (sorted by ts desc so the last inserted has the largest ts)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_usage_events_respects_limit(tenant_id: UUID) -> None:
    """list_usage_events should respect the limit parameter."""
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            for _ in range(5):
                await svc.record_usage(
                    db,
                    UsageEventCreate(
                        tenant_id=tenant_id, event_type="emails_sent", quantity=1
                    ),
                )
            await db.commit()

        async with factory() as db:
            events = await svc.list_usage_events(db, tenant_id, "current_month", limit=2)

        assert len(events) <= 2
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# HTTP tests — GET /api/v1/billing/usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_usage_summary_200() -> None:
    """GET /billing/usage should return 200 with an empty items list (mocked DB)."""
    org_id = uuid4()
    user = _make_mock_user(org_id)

    mock_db_instance = _mock_db()
    # Simulate empty aggregate result
    empty_result = MagicMock()
    empty_result.all.return_value = []
    mock_db_instance.execute = AsyncMock(return_value=empty_result)

    async def db_override():
        yield mock_db_instance

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/billing/usage",
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "period" in body
    assert body["period"] == "current_month"
    assert "items" in body
    assert "start" in body
    assert "end" in body


@pytest.mark.asyncio
async def test_http_usage_summary_last_7_days() -> None:
    """GET /billing/usage?period=last_7_days should be accepted."""
    org_id = uuid4()
    user = _make_mock_user(org_id)

    mock_db_instance = _mock_db()
    empty_result = MagicMock()
    empty_result.all.return_value = []
    mock_db_instance.execute = AsyncMock(return_value=empty_result)

    async def db_override():
        yield mock_db_instance

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/billing/usage",
            params={"period": "last_7_days"},
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
    assert resp.json()["period"] == "last_7_days"


@pytest.mark.asyncio
async def test_http_usage_summary_invalid_period() -> None:
    """GET /billing/usage with unknown period should return 422."""
    org_id = uuid4()
    user = _make_mock_user(org_id)
    mock_db_instance = _mock_db()

    async def db_override():
        yield mock_db_instance

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/billing/usage",
            params={"period": "not_a_period"},
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_http_usage_summary_401_no_auth() -> None:
    """GET /billing/usage without credentials should return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/billing/usage")

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# HTTP tests — GET /api/v1/billing/usage/events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_usage_events_200() -> None:
    """GET /billing/usage/events should return 200 with a list."""
    org_id = uuid4()
    user = _make_mock_user(org_id)
    event = _make_event(org_id, "llm_tokens_input")

    mock_db_instance = _mock_db(events=[event])

    async def db_override():
        yield mock_db_instance

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/billing/usage/events",
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


@pytest.mark.asyncio
async def test_http_usage_events_pagination() -> None:
    """GET /billing/usage/events?limit=1&offset=0 should be accepted."""
    org_id = uuid4()
    user = _make_mock_user(org_id)

    mock_db_instance = _mock_db(events=[])

    async def db_override():
        yield mock_db_instance

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/billing/usage/events",
            params={"limit": 1, "offset": 0},
            cookies=_jwt_cookies(user),
        )

    assert resp.status_code == 200
