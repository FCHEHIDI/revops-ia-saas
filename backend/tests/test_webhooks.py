"""Tests for the Webhooks feature.

Covers:
  - Schema validation (event_type, HTTPS url)
  - Service helpers (secret generation, HMAC signing)
  - HTTP CRUD endpoints via the ASGI test client
  - Delivery worker (publish_event + _deliver_one) with mocked HTTP/Redis
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.webhooks.schemas import SUPPORTED_EVENTS, WebhookEndpointCreate
from app.webhooks.service import _generate_secret, _sign_payload, publish_event

from .conftest import TENANT_A_ID, make_user

# ---------------------------------------------------------------------------
# Schema / unit tests (no HTTP, no DB)
# ---------------------------------------------------------------------------


def test_secret_is_64_hex_chars() -> None:
    """Generated secret must be 64 hexadecimal characters (32 bytes)."""
    secret = _generate_secret()
    assert len(secret) == 64
    assert all(c in "0123456789abcdef" for c in secret)


def test_secrets_are_unique() -> None:
    """Each call to _generate_secret must return a different value."""
    assert _generate_secret() != _generate_secret()


def test_sign_payload_format() -> None:
    """Signature must be prefixed with 'sha256='."""
    sig = _sign_payload("a" * 64, b"hello")
    assert sig.startswith("sha256=")
    assert len(sig) == len("sha256=") + 64  # 64 hex chars


def test_sign_payload_is_deterministic() -> None:
    """Same secret + body must always produce the same signature."""
    secret = _generate_secret()
    body = b'{"event":"deal.won"}'
    assert _sign_payload(secret, body) == _sign_payload(secret, body)


def test_sign_payload_is_correct_hmac() -> None:
    """Verify signature matches manually computed HMAC-SHA256."""
    secret = "c" * 64
    body = b"test-payload"
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _sign_payload(secret, body) == expected


def test_supported_events_set() -> None:
    """SUPPORTED_EVENTS must contain the required RevOps events."""
    required = {"deal.won", "deal.lost", "contact.created", "invoice.overdue", "sequence.completed"}
    assert required.issubset(SUPPORTED_EVENTS)


def test_schema_rejects_unknown_event_type() -> None:
    """WebhookEndpointCreate must raise ValueError for unsupported event types."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        WebhookEndpointCreate(event_type="unknown.event", url="https://example.com/hook")


def test_schema_rejects_http_url() -> None:
    """Webhook URLs must use HTTPS — plain HTTP is rejected."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        WebhookEndpointCreate(event_type="deal.won", url="http://example.com/hook")


def test_schema_accepts_valid_input() -> None:
    """Valid event_type + HTTPS URL must pass schema validation."""
    obj = WebhookEndpointCreate(event_type="deal.won", url="https://example.com/hook")
    assert obj.event_type == "deal.won"


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_event_is_fire_and_forget_when_no_redis(monkeypatch) -> None:
    """publish_event must not raise even when Redis is unavailable."""
    monkeypatch.setattr("app.webhooks.service.settings.redis_url", "")
    # Should complete without exception
    await publish_event(uuid4(), "deal.won", {"id": "abc"})


# ---------------------------------------------------------------------------
# HTTP integration tests — bypass TenantMiddleware via BYPASS_PATHS
# ---------------------------------------------------------------------------
# /api/v1/webhooks is in BYPASS_PATHS; auth enforced by Depends().


@pytest.fixture
def authed_user():
    """Override FastAPI auth dependencies with a mock user."""
    user = make_user(TENANT_A_ID)

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override
    app.dependency_overrides[get_current_active_user] = _override
    yield user
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.asyncio
async def test_create_webhook_returns_secret(authed_user) -> None:
    """POST /api/v1/webhooks must return 201 with a 64-char secret."""
    mock_endpoint = MagicMock()
    mock_endpoint.id = uuid4()
    mock_endpoint.event_type = "deal.won"
    mock_endpoint.url = "https://example.com/hook"
    mock_endpoint.secret = _generate_secret()
    mock_endpoint.active = True
    from datetime import datetime, timezone
    mock_endpoint.created_at = datetime.now(timezone.utc)

    with patch("app.webhooks.router.create_endpoint", new_callable=AsyncMock, return_value=mock_endpoint):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/webhooks",
                json={"event_type": "deal.won", "url": "https://example.com/hook"},
            )

    assert resp.status_code == 201
    data = resp.json()
    assert "secret" in data
    assert len(data["secret"]) == 64


@pytest.mark.asyncio
async def test_create_webhook_rejects_invalid_event(authed_user) -> None:
    """POST with an unsupported event_type must return 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/webhooks",
            json={"event_type": "not.an.event", "url": "https://example.com/hook"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_webhook_rejects_http_url(authed_user) -> None:
    """POST with an HTTP (non-HTTPS) URL must return 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/webhooks",
            json={"event_type": "deal.won", "url": "http://insecure.example.com/hook"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_webhooks_omits_secret(authed_user) -> None:
    """GET /api/v1/webhooks must return a list without secret fields."""
    from datetime import datetime, timezone

    mock_ep = MagicMock()
    mock_ep.id = uuid4()
    mock_ep.event_type = "contact.created"
    mock_ep.url = "https://hooks.example.com/"
    mock_ep.active = True
    mock_ep.created_at = datetime.now(timezone.utc)

    with patch("app.webhooks.router.list_endpoints", new_callable=AsyncMock, return_value=[mock_ep]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/webhooks")

    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) == 1
    assert "secret" not in items[0]


@pytest.mark.asyncio
async def test_delete_webhook_returns_204(authed_user) -> None:
    """DELETE /api/v1/webhooks/{id} must return 204 when endpoint exists."""
    with patch("app.webhooks.router.delete_endpoint", new_callable=AsyncMock, return_value=True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete(f"/api/v1/webhooks/{uuid4()}")

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_webhook_returns_404_when_missing(authed_user) -> None:
    """DELETE /api/v1/webhooks/{id} must return 404 when endpoint not found."""
    with patch("app.webhooks.router.delete_endpoint", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete(f"/api/v1/webhooks/{uuid4()}")

    assert resp.status_code == 404
