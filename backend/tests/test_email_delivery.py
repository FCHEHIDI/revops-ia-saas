"""Tests for the email delivery module — Feature #1.

Note: Redis is not needed for these tests — when settings.redis_url is None
the service skips the queue push silently.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.email_delivery.service import enqueue_send, mark_clicked, mark_opened
from app.main import app
from app.models.email_send import EmailSend

from .conftest import TENANT_A_ID, TENANT_B_ID, make_user

INTER_SERVICE_SECRET = "dev-internal-key-change-me"


def _override_db(db: AsyncSession) -> None:
    app.dependency_overrides[get_db] = lambda: db


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    """Prevent any real Redis connection during tests by nulling settings.redis_url."""
    import app.email_delivery.service as svc_mod
    monkeypatch.setattr(svc_mod.settings, "redis_url", None)


@pytest.mark.asyncio
async def test_enqueue_send_creates_row(test_db: AsyncSession):
    """enqueue_send() inserts an EmailSend with status='pending'."""
    send = await enqueue_send(
        test_db,
        tenant_id=TENANT_A_ID,
        contact_id=uuid.uuid4(),
        to_email="contact@example.com",
        subject="Hello from RevOps",
        body_html="<p>Hi</p>",
    )
    assert send.status == "pending"
    assert send.to_email == "contact@example.com"
    assert send.subject == "Hello from RevOps"
    assert send.tenant_id == TENANT_A_ID
    assert send.open_token is not None
    assert send.click_token is not None


@pytest.mark.asyncio
async def test_mark_opened_sets_opened_at(test_db: AsyncSession):
    """mark_opened() sets opened_at on first call, is idempotent on second."""
    send = await enqueue_send(
        test_db,
        tenant_id=TENANT_A_ID,
        contact_id=uuid.uuid4(),
        to_email="a@b.com",
        subject="S",
        body_html="<p>B</p>",
    )
    await test_db.commit()

    result1 = await mark_opened(test_db, send.open_token)
    assert result1 is True

    row = (await test_db.execute(select(EmailSend).where(EmailSend.id == send.id))).scalar_one()
    assert row.opened_at is not None
    first_opened_at = row.opened_at

    result2 = await mark_opened(test_db, send.open_token)
    assert result2 is False

    row2 = (await test_db.execute(select(EmailSend).where(EmailSend.id == send.id))).scalar_one_or_none()
    assert row2.opened_at == first_opened_at


@pytest.mark.asyncio
async def test_mark_opened_unknown_token(test_db: AsyncSession):
    assert await mark_opened(test_db, uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_mark_clicked_returns_email(test_db: AsyncSession):
    send = await enqueue_send(
        test_db,
        tenant_id=TENANT_A_ID,
        contact_id=uuid.uuid4(),
        to_email="clicker@example.com",
        subject="S",
        body_html="<p>B</p>",
    )
    await test_db.commit()
    email = await mark_clicked(test_db, send.click_token)
    assert email == "clicker@example.com"


@pytest.mark.asyncio
async def test_mark_clicked_unknown_token(test_db: AsyncSession):
    assert await mark_clicked(test_db, uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_enqueue_endpoint_creates_record(test_db: AsyncSession):
    _override_db(test_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/internal/v1/email/enqueue",
                headers={"x-inter-service-secret": INTER_SERVICE_SECRET},
                json={
                    "tenant_id": str(TENANT_A_ID),
                    "contact_id": str(uuid.uuid4()),
                    "to_email": "person@company.com",
                    "subject": "Test subject",
                    "body_html": "<p>Hello</p>",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["to_email"] == "person@company.com"
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_enqueue_endpoint_rejects_wrong_secret(test_db: AsyncSession):
    _override_db(test_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/internal/v1/email/enqueue",
                headers={"x-inter-service-secret": "wrong-secret"},
                json={
                    "tenant_id": str(TENANT_A_ID),
                    "contact_id": str(uuid.uuid4()),
                    "to_email": "x@y.com",
                    "subject": "S",
                    "body_html": "<p>B</p>",
                },
            )
        assert resp.status_code == 401
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_track_open_returns_gif(test_db: AsyncSession):
    _override_db(test_db)
    try:
        send = await enqueue_send(
            test_db,
            tenant_id=TENANT_A_ID,
            contact_id=uuid.uuid4(),
            to_email="track@test.com",
            subject="S",
            body_html="<p>B</p>",
        )
        await test_db.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/track/{send.open_token}")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/gif"
        assert len(resp.content) > 0

        row = (await test_db.execute(select(EmailSend).where(EmailSend.id == send.id))).scalar_one()
        assert row.opened_at is not None
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_click_redirect_valid_url(test_db: AsyncSession):
    _override_db(test_db)
    try:
        send = await enqueue_send(
            test_db,
            tenant_id=TENANT_A_ID,
            contact_id=uuid.uuid4(),
            to_email="click@test.com",
            subject="S",
            body_html="<p>B</p>",
        )
        await test_db.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
        ) as client:
            resp = await client.get(f"/click/{send.click_token}", params={"url": "https://example.com/landing"})

        assert resp.status_code == 302
        assert resp.headers["location"] == "https://example.com/landing"

        row = (await test_db.execute(select(EmailSend).where(EmailSend.id == send.id))).scalar_one()
        assert row.clicked_at is not None
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_click_redirect_blocks_javascript_url(test_db: AsyncSession):
    _override_db(test_db)
    try:
        send = await enqueue_send(
            test_db,
            tenant_id=TENANT_A_ID,
            contact_id=uuid.uuid4(),
            to_email="xss@test.com",
            subject="S",
            body_html="<p>B</p>",
        )
        await test_db.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
        ) as client:
            resp = await client.get(f"/click/{send.click_token}", params={"url": "javascript:alert(1)"})

        assert resp.status_code == 422
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_track_unknown_token_returns_gif(test_db: AsyncSession):
    _override_db(test_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/track/{uuid.uuid4()}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/gif"
    finally:
        _clear_overrides()
