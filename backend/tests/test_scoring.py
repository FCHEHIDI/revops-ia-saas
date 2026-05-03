"""Tests for AI lead scoring — Feature #3.

Covers:
- Heuristic scoring (no LLM, no Redis)
- score_lead() persists a LeadScore row
- Contact not found raises ValueError → 404
- Cache hit returns cached=True
- HTTP endpoint: POST /internal/v1/scoring/score-lead
- HTTP endpoint: 404 for unknown contact
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db import get_db
from app.crm.models import Contact, Deal
from app.main import app
from app.models.lead_score import LeadScore
from app.scoring.service import _score_heuristic, score_lead

from .conftest import TENANT_A_ID, make_user

INTERNAL_API_KEY = ""  # default in tests is empty string (settings.internal_api_key)


def _override_db(db: AsyncSession) -> None:
    app.dependency_overrides[get_db] = lambda: db


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    """Disable Redis in scoring service for tests."""
    import app.scoring.service as svc_mod

    monkeypatch.setattr(svc_mod, "_get_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(svc_mod, "_set_cache", AsyncMock())


# ---------------------------------------------------------------------------
# Unit: heuristic scoring
# ---------------------------------------------------------------------------


def _make_deal(stage: str) -> MagicMock:
    d = MagicMock(spec=Deal)
    d.stage = stage
    d.title = "Test deal"
    d.amount = 10000
    d.currency = "EUR"
    d.probability = 50
    return d


def _make_contact() -> MagicMock:
    c = MagicMock(spec=Contact)
    c.first_name = "Alice"
    c.last_name = "Smith"
    c.job_title = "VP Sales"
    c.status = "active"
    return c


def test_heuristic_no_deals():
    """No deals → score=20, action suggests discovery email."""
    contact = _make_contact()
    score, reasoning, action, model = _score_heuristic(contact=contact, deals=[])
    assert score == 20
    assert model == "heuristic"
    assert "discovery" in action.lower() or action  # just a non-empty action


def test_heuristic_negotiation_stage():
    """Best stage = negotiation → score=85."""
    contact = _make_contact()
    deals = [_make_deal("negotiation"), _make_deal("prospecting")]
    score, reasoning, action, model = _score_heuristic(contact=contact, deals=deals)
    # Two deals: 85 + 5 = 90 (capped at 100)
    assert score == 90
    assert model == "heuristic"
    assert "negotiation" in reasoning


def test_heuristic_closed_won():
    """Closed won → score=100 (100 + 5 for 2 deals, capped at 100)."""
    contact = _make_contact()
    deals = [_make_deal("closed_won"), _make_deal("negotiation")]
    score, _, _, _ = _score_heuristic(contact=contact, deals=deals)
    assert score == 100


def test_heuristic_single_deal_prospecting():
    """Single prospecting deal → score=25 (no boost)."""
    contact = _make_contact()
    score, _, _, _ = _score_heuristic(contact=contact, deals=[_make_deal("prospecting")])
    assert score == 25


# ---------------------------------------------------------------------------
# Integration: score_lead() persists to DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_lead_persists_row(test_db: AsyncSession):
    """score_lead() inserts a LeadScore row and returns a valid response."""
    # Insert a contact
    contact_id = uuid.uuid4()
    contact = Contact(
        id=contact_id,
        org_id=TENANT_A_ID,
        first_name="Bob",
        last_name="Jones",
        email=f"bob.{contact_id}@example.com",
        status="prospect",
    )
    test_db.add(contact)
    await test_db.commit()

    from app.config import settings

    resp = await score_lead(
        test_db,
        tenant_id=TENANT_A_ID,
        contact_id=contact_id,
        force_refresh=False,
        settings=settings,
    )

    assert resp.score == 20  # no deals → heuristic default
    assert resp.model_used == "heuristic"
    assert resp.cached is False
    assert resp.contact_id == contact_id

    # Row persisted
    row = (
        await test_db.execute(
            select(LeadScore).where(
                LeadScore.contact_id == contact_id,
                LeadScore.tenant_id == TENANT_A_ID,
            )
        )
    ).scalar_one_or_none()
    assert row is not None
    assert row.score == 20


@pytest.mark.asyncio
async def test_score_lead_contact_not_found(test_db: AsyncSession):
    """score_lead() raises ValueError when contact does not exist."""
    from app.config import settings

    with pytest.raises(ValueError, match="not found"):
        await score_lead(
            test_db,
            tenant_id=TENANT_A_ID,
            contact_id=uuid.uuid4(),
            force_refresh=False,
            settings=settings,
        )


@pytest.mark.asyncio
async def test_score_lead_with_deals(test_db: AsyncSession):
    """Contact with a deal in 'proposal' stage scores 65."""
    contact_id = uuid.uuid4()
    contact = Contact(
        id=contact_id,
        org_id=TENANT_A_ID,
        first_name="Carol",
        last_name="White",
        email=f"carol.{contact_id}@example.com",
        status="active",
    )
    test_db.add(contact)
    await test_db.flush()

    # Need an account for the deal
    from app.crm.models import Account

    account = Account(
        id=uuid.uuid4(),
        org_id=TENANT_A_ID,
        name="Acme Corp",
        status="active",
    )
    test_db.add(account)
    await test_db.flush()

    deal = Deal(
        id=uuid.uuid4(),
        org_id=TENANT_A_ID,
        account_id=account.id,
        contact_id=contact_id,
        title="Big Deal",
        stage="proposal",
        currency="EUR",
    )
    test_db.add(deal)
    await test_db.commit()

    from app.config import settings

    resp = await score_lead(
        test_db,
        tenant_id=TENANT_A_ID,
        contact_id=contact_id,
        force_refresh=False,
        settings=settings,
    )
    assert resp.score == 65
    assert resp.model_used == "heuristic"


# ---------------------------------------------------------------------------
# Integration: cache hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_lead_cache_hit(test_db: AsyncSession, monkeypatch):
    """When cache returns a value, score_lead returns cached=True without hitting DB."""
    import app.scoring.service as svc_mod

    contact_id = uuid.uuid4()
    cached_payload = {
        "contact_id": str(contact_id),
        "score": 77,
        "reasoning": "From cache",
        "recommended_action": "Call now",
        "model_used": "gpt-4o-mini",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Override _get_cache so it always returns the cached payload
    monkeypatch.setattr(svc_mod, "_get_cache", AsyncMock(return_value=cached_payload))

    # Build a mock settings with redis_url set so the cache branch is entered
    mock_settings = MagicMock()
    mock_settings.redis_url = "redis://localhost:6379"
    mock_settings.openai_api_key = ""
    mock_settings.lead_score_ttl_seconds = 86400

    resp = await score_lead(
        test_db,
        tenant_id=TENANT_A_ID,
        contact_id=contact_id,
        force_refresh=False,
        settings=mock_settings,
    )
    assert resp.cached is True
    assert resp.score == 77
    assert resp.recommended_action == "Call now"


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_score_lead_returns_200(test_db: AsyncSession):
    """POST /internal/v1/scoring/score-lead returns 200 with a valid payload."""
    _override_db(test_db)
    try:
        contact_id = uuid.uuid4()
        contact = Contact(
            id=contact_id,
            org_id=TENANT_A_ID,
            first_name="Dave",
            last_name="Brown",
            email=f"dave.{contact_id}@example.com",
            status="active",
        )
        test_db.add(contact)
        await test_db.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/internal/v1/scoring/score-lead",
                headers={
                    "x-internal-api-key": "",  # empty = matches default
                    "x-tenant-id": str(TENANT_A_ID),
                },
                json={
                    "tenant_id": str(TENANT_A_ID),
                    "contact_id": str(contact_id),
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert 0 <= data["score"] <= 100
        assert "reasoning" in data
        assert "recommended_action" in data
        assert data["cached"] is False
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_http_score_lead_contact_not_found(test_db: AsyncSession):
    """POST /internal/v1/scoring/score-lead returns 404 for unknown contact."""
    _override_db(test_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/internal/v1/scoring/score-lead",
                headers={
                    "x-internal-api-key": "",
                    "x-tenant-id": str(TENANT_A_ID),
                },
                json={
                    "tenant_id": str(TENANT_A_ID),
                    "contact_id": str(uuid.uuid4()),
                },
            )
        assert resp.status_code == 404
    finally:
        _clear_overrides()
