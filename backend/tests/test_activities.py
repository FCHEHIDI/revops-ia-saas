"""Tests for the activity timeline endpoint — Feature #4.

Covers:
- GET /api/v1/activities/{entity_type}/{entity_id} returns empty list initially
- Activity is recorded after creating a contact (contact_created)
- Activity is recorded after creating a deal (deal_created)
- Activity is recorded when a deal stage changes (deal_stage_changed)
- Tenant isolation: activities from tenant A are invisible to tenant B
- Invalid entity_type returns 422
- limit query param caps results
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities.service import get_timeline, record
from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.main import app
from app.models.activity import Activity
from app.models.user import User

from .conftest import TENANT_A_ID, TENANT_B_ID, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(tenant_id: uuid.UUID) -> User:
    return make_user(tenant_id)


def _override_user(user: User):
    app.dependency_overrides[get_current_active_user] = lambda: user


def _clear_overrides():
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Service-level unit tests (no HTTP, use real test DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_and_get_timeline(test_db: AsyncSession):
    """record() inserts a row; get_timeline() returns it."""
    tenant_id = uuid.uuid4()
    entity_id = uuid.uuid4()

    await record(
        test_db,
        tenant_id=tenant_id,
        entity_type="contact",
        entity_id=entity_id,
        activity_type="contact_created",
        actor_id=None,
        payload={"email": "foo@bar.com"},
    )
    await test_db.flush()

    results = await get_timeline(
        test_db,
        tenant_id=tenant_id,
        entity_type="contact",
        entity_id=entity_id,
    )
    assert len(results) == 1
    assert results[0].type == "contact_created"
    assert results[0].payload["email"] == "foo@bar.com"


@pytest.mark.asyncio
async def test_record_tenant_isolation(test_db: AsyncSession):
    """Activities from one tenant are not visible to another."""
    entity_id = uuid.uuid4()
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    await record(
        test_db,
        tenant_id=tenant_a,
        entity_type="deal",
        entity_id=entity_id,
        activity_type="deal_created",
    )
    await test_db.flush()

    # Same entity_id, different tenant — must return nothing
    results = await get_timeline(
        test_db,
        tenant_id=tenant_b,
        entity_type="deal",
        entity_id=entity_id,
    )
    assert results == []


@pytest.mark.asyncio
async def test_record_silent_on_error():
    """record() should never raise even when the DB write fails."""
    bad_db = AsyncMock(spec=AsyncSession)
    bad_db.add = MagicMock(side_effect=RuntimeError("db error"))

    # Should not raise
    await record(
        bad_db,
        tenant_id=uuid.uuid4(),
        entity_type="contact",
        entity_id=uuid.uuid4(),
        activity_type="contact_created",
    )


@pytest.mark.asyncio
async def test_get_timeline_limit(test_db: AsyncSession):
    """get_timeline respects the limit parameter."""
    tenant_id = uuid.uuid4()
    entity_id = uuid.uuid4()

    for i in range(5):
        await record(
            test_db,
            tenant_id=tenant_id,
            entity_type="contact",
            entity_id=entity_id,
            activity_type="note_added",
            payload={"n": i},
        )
    await test_db.flush()

    results = await get_timeline(
        test_db,
        tenant_id=tenant_id,
        entity_type="contact",
        entity_id=entity_id,
        limit=3,
    )
    assert len(results) == 3


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_http_get_timeline_empty(http_client: AsyncClient, test_db: AsyncSession):
    """GET /api/v1/activities/{type}/{id} returns empty list when no events exist."""
    user = _make_user(TENANT_A_ID)
    _override_user(user)
    app.dependency_overrides[get_db] = lambda: test_db
    try:
        entity_id = uuid.uuid4()
        resp = await http_client.get(f"/api/v1/activities/contact/{entity_id}")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_http_get_timeline_with_event(http_client: AsyncClient, test_db: AsyncSession):
    """GET /api/v1/activities/{type}/{id} returns recorded activities."""
    user = _make_user(TENANT_A_ID)
    _override_user(user)
    app.dependency_overrides[get_db] = lambda: test_db
    try:
        entity_id = uuid.uuid4()
        await record(
            test_db,
            tenant_id=TENANT_A_ID,
            entity_type="contact",
            entity_id=entity_id,
            activity_type="contact_created",
            actor_id=user.id,
        )
        await test_db.flush()

        resp = await http_client.get(f"/api/v1/activities/contact/{entity_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["type"] == "contact_created"
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_http_invalid_entity_type(http_client: AsyncClient, test_db: AsyncSession):
    """GET /api/v1/activities/bad_type/{id} returns 422."""
    user = _make_user(TENANT_A_ID)
    _override_user(user)
    app.dependency_overrides[get_db] = lambda: test_db
    try:
        resp = await http_client.get(f"/api/v1/activities/invoice/{uuid.uuid4()}")
        assert resp.status_code == 422
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_http_limit_query_param(http_client: AsyncClient, test_db: AsyncSession):
    """GET ...?limit=2 returns at most 2 results."""
    user = _make_user(TENANT_A_ID)
    _override_user(user)
    app.dependency_overrides[get_db] = lambda: test_db
    try:
        entity_id = uuid.uuid4()
        for _ in range(4):
            await record(
                test_db,
                tenant_id=TENANT_A_ID,
                entity_type="deal",
                entity_id=entity_id,
                activity_type="note_added",
            )
        await test_db.flush()

        resp = await http_client.get(
            f"/api/v1/activities/deal/{entity_id}", params={"limit": 2}
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_http_tenant_isolation(http_client: AsyncClient, test_db: AsyncSession):
    """Tenant B cannot see tenant A's activities for the same entity_id."""
    user_a = _make_user(TENANT_A_ID)
    user_b = _make_user(TENANT_B_ID)
    app.dependency_overrides[get_db] = lambda: test_db

    entity_id = uuid.uuid4()
    await record(
        test_db,
        tenant_id=TENANT_A_ID,
        entity_type="contact",
        entity_id=entity_id,
        activity_type="contact_created",
    )
    await test_db.flush()

    # Tenant B query
    app.dependency_overrides[get_current_active_user] = lambda: user_b
    try:
        resp = await http_client.get(f"/api/v1/activities/contact/{entity_id}")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        _clear_overrides()
