"""Tests for Feature #6 — Playbooks IA.

Coverage:
- Unit: evaluate_conditions logic (all pass, one fail, in-op)
- DB: CRUD via service layer (create, get, list, update, delete, runs)
- DB: run_playbook() — add_note action, condition filtering, completed status
- HTTP: GET  /internal/v1/playbooks?tenant_id=...  → 200
- HTTP: POST /internal/v1/playbooks/trigger        → 202
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.models.organization import Organization
from app.playbooks.executor import evaluate_conditions
from app.playbooks.schemas import PlaybookCreate, PlaybookUpdate
from app.playbooks import service as svc

logger = logging.getLogger(__name__)

_TEST_DB_URL = "postgresql+asyncpg://revops:revops@localhost:5433/revops_test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tenant_id() -> AsyncGenerator[UUID, None]:
    """Create a real Organization row in its own committed session and return its id."""
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    org_id = uuid4()
    async with factory() as session:
        org = Organization(
            id=org_id,
            name="PlaybookTestTenant",
            slug=f"playbook-test-{org_id.hex[:8]}",
        )
        session.add(org)
        await session.commit()
    yield org_id
    # Cleanup
    try:
        async with factory() as session:
            from sqlalchemy import delete
            await session.execute(delete(Organization).where(Organization.id == org_id))
            await session.commit()
        await engine.dispose()
    except Exception:  # noqa: BLE001
        pass


@pytest_asyncio.fixture(scope="module")
async def tenant_with_playbook() -> AsyncGenerator[tuple[UUID, UUID], None]:
    """Create an Organization + Playbook in committed state; yield (tenant_id, playbook_id)."""
    from app.models.playbook import Playbook as PlaybookModel

    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    org_id = uuid4()
    pb_id = uuid4()
    async with factory() as session:
        org = Organization(
            id=org_id,
            name="PlaybookHTTPTenant",
            slug=f"playbook-http-{org_id.hex[:8]}",
        )
        session.add(org)
        await session.flush()
        pb = PlaybookModel(
            id=pb_id,
            tenant_id=org_id,
            name="HTTP trigger test",
            trigger_event="manual",
            actions=[{"type": "send_notification", "message": "triggered"}],
            is_active=True,
        )
        session.add(pb)
        await session.commit()
    yield org_id, pb_id
    # Cleanup — org CASCADE deletes playbook
    try:
        async with factory() as session:
            from sqlalchemy import delete
            await session.execute(delete(Organization).where(Organization.id == org_id))
            await session.commit()
        await engine.dispose()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture(autouse=True)
def no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out Redis cache calls to avoid connection errors in scoring action."""
    import app.scoring.service as svc_mod

    monkeypatch.setattr(svc_mod, "_get_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(svc_mod, "_set_cache", AsyncMock())


@pytest_asyncio.fixture(scope="module")
async def http_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Unit — evaluate_conditions
# ---------------------------------------------------------------------------


def test_evaluate_conditions_empty_passes() -> None:
    """Empty condition list → True (unconditional trigger)."""
    assert evaluate_conditions([], {"score": 90}) is True


def test_evaluate_conditions_eq_pass() -> None:
    """Single eq condition that matches."""
    conditions = [{"field": "stage", "op": "eq", "value": "qualified"}]
    assert evaluate_conditions(conditions, {"stage": "qualified"}) is True


def test_evaluate_conditions_one_fails() -> None:
    """All conditions must pass (AND logic); one ne mismatch fails the set."""
    conditions = [
        {"field": "stage", "op": "eq", "value": "qualified"},
        {"field": "stage", "op": "ne", "value": "qualified"},
    ]
    assert evaluate_conditions(conditions, {"stage": "qualified"}) is False


def test_evaluate_conditions_in_op() -> None:
    """in operator — field value must be in the list."""
    conditions = [{"field": "stage", "op": "in", "value": ["qualified", "proposal"]}]
    assert evaluate_conditions(conditions, {"stage": "qualified"}) is True
    assert evaluate_conditions(conditions, {"stage": "lost"}) is False


def test_evaluate_conditions_gte_lte() -> None:
    """gte / lte numeric comparisons."""
    assert evaluate_conditions(
        [{"field": "score", "op": "gte", "value": 80}], {"score": 90}
    ) is True
    assert evaluate_conditions(
        [{"field": "score", "op": "lte", "value": 50}], {"score": 90}
    ) is False


def test_evaluate_conditions_missing_field_fails() -> None:
    """A field not present in the payload should NOT raise; the condition fails."""
    conditions = [{"field": "nonexistent", "op": "eq", "value": "x"}]
    assert evaluate_conditions(conditions, {}) is False


# ---------------------------------------------------------------------------
# HTTP — internal endpoints (run before DB tests to avoid loop teardown issues)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_internal_list_and_trigger_playbook(test_db: AsyncSession, tenant_id: UUID) -> None:
    """Tests both GET /internal/v1/playbooks and POST /internal/v1/playbooks/trigger."""
    from app.common.db import get_db
    from app.main import app as _app

    # Create playbook in test_db (same session the HTTP endpoint will use)
    pb = await svc.create_playbook(
        test_db,
        tenant_id,
        PlaybookCreate(
            name="HTTP test playbook",
            trigger_event="manual",
            actions=[{"type": "send_notification", "message": "ok"}],
        ),
    )

    # Override get_db so HTTP requests use the same test_db session
    _app.dependency_overrides[get_db] = lambda: test_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as ac:
            # GET list
            resp = await ac.get(
                "/internal/v1/playbooks/",
                params={"tenant_id": str(tenant_id)},
            )
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

            # POST trigger
            resp2 = await ac.post(
                "/internal/v1/playbooks/trigger",
                json={"playbook_id": str(pb.id)},
            )
            assert resp2.status_code == 202
            body = resp2.json()
            assert body["status"] in ("completed", "running", "failed", "pending")
    finally:
        _app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# DB — CRUD via service layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_playbook(test_db: AsyncSession, tenant_id: UUID) -> None:
    """Create a playbook, then retrieve it by id."""
    data = PlaybookCreate(
        name="Test PB",
        trigger_event="deal.stage_changed",
        trigger_conditions=[],
        actions=[{"type": "send_notification", "message": "Hello"}],
    )
    pb = await svc.create_playbook(test_db, tenant_id, data)
    assert pb.id is not None
    assert pb.name == "Test PB"

    fetched = await svc.get_playbook(test_db, pb.id, tenant_id)
    assert fetched is not None
    assert fetched.id == pb.id


@pytest.mark.asyncio
async def test_list_playbooks_active_only(test_db: AsyncSession, tenant_id: UUID) -> None:
    """active_only=True must exclude inactive playbooks."""
    data_active = PlaybookCreate(
        name="Active PB",
        trigger_event="deal.created",
        actions=[{"type": "send_notification", "message": "Hi"}],
    )
    data_inactive = PlaybookCreate(
        name="Inactive PB",
        trigger_event="deal.created",
        is_active=False,
        actions=[{"type": "send_notification", "message": "Hi"}],
    )
    await svc.create_playbook(test_db, tenant_id, data_active)
    await svc.create_playbook(test_db, tenant_id, data_inactive)

    items, total = await svc.list_playbooks(test_db, tenant_id, active_only=True)
    names = [p.name for p in items]
    assert "Active PB" in names
    assert "Inactive PB" not in names


@pytest.mark.asyncio
async def test_update_playbook(test_db: AsyncSession, tenant_id: UUID) -> None:
    """Patch is_active to False, verify persistence."""
    pb = await svc.create_playbook(
        test_db,
        tenant_id,
        PlaybookCreate(
            name="PB to update",
            trigger_event="manual",
            actions=[{"type": "send_notification", "message": "x"}],
        ),
    )
    updated = await svc.update_playbook(
        test_db, pb.id, tenant_id, PlaybookUpdate(is_active=False)
    )
    assert updated is not None
    assert updated.is_active is False


@pytest.mark.asyncio
async def test_delete_playbook(test_db: AsyncSession, tenant_id: UUID) -> None:
    """Delete a playbook; subsequent get should return None."""
    pb = await svc.create_playbook(
        test_db,
        tenant_id,
        PlaybookCreate(
            name="PB to delete",
            trigger_event="manual",
            actions=[{"type": "send_notification", "message": "x"}],
        ),
    )
    deleted = await svc.delete_playbook(test_db, pb.id, tenant_id)
    assert deleted is True

    gone = await svc.get_playbook(test_db, pb.id, tenant_id)
    assert gone is None


@pytest.mark.asyncio
async def test_list_runs_empty(test_db: AsyncSession, tenant_id: UUID) -> None:
    """A newly created playbook has no runs."""
    pb = await svc.create_playbook(
        test_db,
        tenant_id,
        PlaybookCreate(
            name="PB no runs",
            trigger_event="manual",
            actions=[{"type": "send_notification", "message": "x"}],
        ),
    )
    runs = await svc.list_runs(test_db, pb.id, tenant_id)
    assert runs == []


# ---------------------------------------------------------------------------
# DB — run_playbook() execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_playbook_completed_status(test_db: AsyncSession, tenant_id: UUID) -> None:
    """run_playbook() should return a PlaybookRun with status='completed'."""
    pb = await svc.create_playbook(
        test_db,
        tenant_id,
        PlaybookCreate(
            name="Run test",
            trigger_event="manual",
            actions=[{"type": "send_notification", "message": "test msg"}],
        ),
    )
    event = {"event": "manual", "tenant_id": str(tenant_id), "payload": {}}
    run = await svc.run_playbook(test_db, pb, event)

    assert run.status == "completed"
    assert run.completed_at is not None
    assert run.result is not None


@pytest.mark.asyncio
async def test_run_playbook_add_note_action(test_db: AsyncSession, tenant_id: UUID) -> None:
    """run_playbook() with add_note action should call activities.record without raising."""
    record_calls: list = []

    async def fake_record(*args, **kwargs) -> None:  # noqa: ANN002
        record_calls.append(kwargs)

    with patch("app.playbooks.executor._record_activity", side_effect=fake_record):
        pb = await svc.create_playbook(
            test_db,
            tenant_id,
            PlaybookCreate(
                name="Note PB",
                trigger_event="deal.stage_changed",
                actions=[
                    {
                        "type": "add_note",
                        "content": "Stage changed — follow up!",
                    }
                ],
            ),
        )
        deal_id = uuid4()
        event = {
            "event": "deal.stage_changed",
            "tenant_id": str(tenant_id),
            "payload": {"deal_id": str(deal_id), "stage": "qualified"},
        }
        run = await svc.run_playbook(test_db, pb, event)

    assert run.status == "completed"
    assert len(record_calls) == 1
    assert record_calls[0]["activity_type"] == "note_added"


@pytest.mark.asyncio
async def test_run_playbook_conditions_filter(test_db: AsyncSession, tenant_id: UUID) -> None:
    """Only playbooks whose conditions match the event payload are executed."""
    # Matching playbook: requires stage == "qualified"
    pb_match = await svc.create_playbook(
        test_db,
        tenant_id,
        PlaybookCreate(
            name="Matching",
            trigger_event="deal.stage_changed",
            trigger_conditions=[{"field": "stage", "op": "eq", "value": "qualified"}],
            actions=[{"type": "send_notification", "message": "Qualified!"}],
        ),
    )
    # Non-matching playbook: requires stage == "proposal"
    pb_no_match = await svc.create_playbook(
        test_db,
        tenant_id,
        PlaybookCreate(
            name="NonMatching",
            trigger_event="deal.stage_changed",
            trigger_conditions=[{"field": "stage", "op": "eq", "value": "proposal"}],
            actions=[{"type": "send_notification", "message": "Proposal"}],
        ),
    )

    event = {
        "event": "deal.stage_changed",
        "tenant_id": str(tenant_id),
        "entity_type": "deal",
        "entity_id": str(uuid4()),
        "payload": {"stage": "qualified", "deal_id": str(uuid4())},
    }

    # Run both manually to simulate what the worker does
    run_match = await svc.run_playbook(test_db, pb_match, event)
    assert run_match.status == "completed"

    # Condition check before run_playbook (as worker would do)
    conditions_met = evaluate_conditions(
        pb_no_match.trigger_conditions or [], event.get("payload", {})
    )
    assert conditions_met is False
