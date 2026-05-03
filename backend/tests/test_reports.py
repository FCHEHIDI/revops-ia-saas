"""Tests for Feature #7 — PDF Reports.

Coverage:
- Unit: ReportGenerateRequest validation (valid types, invalid type)
- Unit: render_pdf() for all 4 report types
- DB:   create_report_job / get_report_job / list_report_jobs via service (real DB)
- HTTP: POST /api/v1/reports/generate → 202 (mocked DB)
- HTTP: POST /api/v1/reports/generate → 422 for invalid type
- HTTP: GET  /api/v1/reports/{id}/status → 200 and 404 (mocked DB)
- HTTP: GET  /api/v1/reports/{id}/download → 200 with PDF bytes (mocked DB)
- HTTP: GET  /api/v1/reports/{id}/download → 409 when not done (mocked DB)

DB tests use a separately-committed Organization row (separate engine, function-scoped)
so the report_jobs FK constraint is satisfied without touching the rollback-based
test_db session state.

HTTP tests use AsyncMock DB sessions (like test_sessions.py) to avoid asyncpg
event-loop conflicts when running inside ASGITransport.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.dependencies import get_current_active_user
from app.auth.service import create_access_token
from app.common.db import get_db
from app.main import app
from app.models.organization import Organization
from app.models.report_job import ReportJob
from app.models.user import User
from app.reports import service as svc
from app.reports.schemas import ReportGenerateRequest, REPORT_TYPES
from app.reports.service import render_pdf, _pdf_cache

logger = logging.getLogger(__name__)

_TEST_DB_URL = "postgresql+asyncpg://revops:revops@localhost:5433/revops_test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tenant_id() -> AsyncGenerator[UUID, None]:
    """Create a committed Organization row in its own engine and yield its id.

    Uses a separate engine (not test_db) so the committed org satisfies the
    report_jobs FK constraint without polluting the rollback-based test session.
    """
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    org_id = uuid4()
    async with factory() as session:
        org = Organization(
            id=org_id,
            name="ReportsTestTenant",
            slug=f"reports-test-{org_id.hex[:8]}",
        )
        session.add(org)
        await session.commit()
    yield org_id
    try:
        from sqlalchemy import delete
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
# Helpers for HTTP tests (AsyncMock-based DB)
# ---------------------------------------------------------------------------


def _make_mock_user(tenant_id: UUID) -> MagicMock:
    """Return a MagicMock User for auth dependency override."""
    u = MagicMock(spec=User)
    u.id = uuid4()
    u.tenant_id = tenant_id
    u.is_active = True
    u.full_name = "Test User"
    u.email = "test@example.com"
    return u


def _jwt_cookies(user: MagicMock) -> dict[str, str]:
    """Create a valid JWT cookie to satisfy TenantMiddleware."""
    return {"access_token": create_access_token(user)}


def _make_job(
    tenant_id: UUID, report_type: str = "pipeline", status: str = "pending"
) -> ReportJob:
    """Instantiate a ReportJob Python object with all fields set."""
    return ReportJob(
        id=uuid4(),
        tenant_id=tenant_id,
        report_type=report_type,
        status=status,
        created_at=datetime.now(timezone.utc),
    )


def _mock_db(job: ReportJob | None = None) -> AsyncMock:
    """Return an AsyncMock session where execute().scalar_one_or_none() → job."""
    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    result.scalars.return_value = MagicMock(
        all=MagicMock(return_value=[job] if job is not None else [])
    )
    mock_db.execute = AsyncMock(return_value=result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    return mock_db


# ---------------------------------------------------------------------------
# Unit tests — schema validation
# ---------------------------------------------------------------------------


def test_report_generate_request_valid_types() -> None:
    """All REPORT_TYPES should be accepted by ReportGenerateRequest."""
    for rtype in REPORT_TYPES:
        req = ReportGenerateRequest(report_type=rtype)
        assert req.report_type == rtype


def test_report_generate_request_invalid_type() -> None:
    """Unknown report_type should raise a validation error."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="Unknown report_type"):
        ReportGenerateRequest(report_type="unknown_type")


# ---------------------------------------------------------------------------
# Unit tests — PDF rendering
# ---------------------------------------------------------------------------


def test_render_pdf_pipeline() -> None:
    """render_pdf('pipeline', ...) returns a valid PDF."""
    data = {
        "stages": [
            {"stage": "closed_won", "count": 2, "total": 10000.0},
            {"stage": "proposal", "count": 4, "total": 40000.0},
        ],
        "total_deals": 6,
        "total_value": 50000.0,
        "win_rate": 33.3,
    }
    pdf = render_pdf("pipeline", data, uuid4())
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 500


def test_render_pdf_mrr() -> None:
    """render_pdf('mrr', ...) returns a valid PDF."""
    data = {
        "accounts": [
            {"name": "Acme Corp", "arr": 90000.0, "status": "active", "industry": "SaaS"}
        ],
        "total_arr": 90000.0,
    }
    pdf = render_pdf("mrr", data, uuid4())
    assert pdf[:4] == b"%PDF"


def test_render_pdf_team_performance() -> None:
    """render_pdf('team_performance', ...) returns a valid PDF."""
    data = {
        "reps": [
            {"owner_id": str(uuid4()), "deal_count": 3, "won_count": 1, "total_value": 30000.0}
        ],
        "total_reps": 1,
    }
    pdf = render_pdf("team_performance", data, uuid4())
    assert pdf[:4] == b"%PDF"


def test_render_pdf_churn() -> None:
    """render_pdf('churn', ...) returns a valid PDF."""
    data = {
        "by_status": [{"status": "active", "count": 8}, {"status": "churned", "count": 2}],
        "total_accounts": 10,
        "churned": 2,
        "churn_rate": 20.0,
        "total_contacts": 30,
    }
    pdf = render_pdf("churn", data, uuid4())
    assert pdf[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# DB tests — service layer (own committed engine, no test_db to avoid rollback clash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_report_job(tenant_id: UUID) -> None:
    """create_report_job stores the job; get_report_job retrieves it."""
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            req = ReportGenerateRequest(report_type="pipeline")
            job = await svc.create_report_job(db, tenant_id, req)
            await db.commit()

            assert job.id is not None
            assert job.tenant_id == tenant_id
            assert job.report_type == "pipeline"
            assert job.status == "pending"
            assert job.created_at is not None

            fetched = await svc.get_report_job(db, tenant_id, job.id)
            assert fetched is not None
            assert fetched.id == job.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_report_job_wrong_tenant(tenant_id: UUID) -> None:
    """get_report_job returns None for a different tenant."""
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            req = ReportGenerateRequest(report_type="mrr")
            job = await svc.create_report_job(db, tenant_id, req)
            await db.commit()

            result = await svc.get_report_job(db, uuid4(), job.id)
            assert result is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_report_jobs(tenant_id: UUID) -> None:
    """list_report_jobs returns all jobs for the tenant, newest first."""
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            for rtype in ("pipeline", "mrr", "churn"):
                await svc.create_report_job(db, tenant_id, ReportGenerateRequest(report_type=rtype))
            await db.commit()

            jobs = await svc.list_report_jobs(db, tenant_id)
            assert len(jobs) >= 3
            report_types = {j.report_type for j in jobs}
            assert {"pipeline", "mrr", "churn"}.issubset(report_types)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_to_status_read_done_has_download_url(tenant_id: UUID) -> None:
    """to_status_read sets download_url only when status is 'done'."""
    engine = create_async_engine(_TEST_DB_URL, future=True, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            req = ReportGenerateRequest(report_type="churn")
            job = await svc.create_report_job(db, tenant_id, req)
            await db.commit()
    finally:
        await engine.dispose()

    pending_read = svc.to_status_read(job)
    assert pending_read.download_url is None

    job.status = "done"
    done_read = svc.to_status_read(job)
    assert done_read.download_url == f"/api/v1/reports/{job.id}/download"


# ---------------------------------------------------------------------------
# HTTP tests — AsyncMock DB avoids asyncpg event-loop conflicts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_generate_report() -> None:
    """POST /api/v1/reports/generate returns 202 with pending job."""
    tid = uuid4()
    user = _make_mock_user(tid)
    cookies = _jwt_cookies(user)
    db = _mock_db()

    async def db_override() -> AsyncGenerator[AsyncMock, None]:
        yield db

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    with patch("app.reports.router.asyncio.create_task"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/api/v1/reports/generate",
                json={"report_type": "pipeline"},
                cookies=cookies,
            )

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["report_type"] == "pipeline"
    assert body["download_url"] is None


@pytest.mark.asyncio
async def test_http_generate_invalid_type() -> None:
    """POST /generate with unknown report_type returns 422."""
    tid = uuid4()
    user = _make_mock_user(tid)
    cookies = _jwt_cookies(user)

    async def db_override() -> AsyncGenerator[AsyncMock, None]:
        yield _mock_db()

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/v1/reports/generate",
            json={"report_type": "nonexistent"},
            cookies=cookies,
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_http_status_200() -> None:
    """GET /{job_id}/status returns 200 with job info."""
    tid = uuid4()
    user = _make_mock_user(tid)
    job = _make_job(tid, "mrr", "pending")
    cookies = _jwt_cookies(user)

    async def db_override() -> AsyncGenerator[AsyncMock, None]:
        yield _mock_db(job=job)

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            f"/api/v1/reports/{job.id}/status",
            cookies=cookies,
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_http_status_404() -> None:
    """GET /{job_id}/status returns 404 for unknown job."""
    tid = uuid4()
    user = _make_mock_user(tid)
    cookies = _jwt_cookies(user)

    async def db_override() -> AsyncGenerator[AsyncMock, None]:
        yield _mock_db(job=None)

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            f"/api/v1/reports/{uuid4()}/status",
            cookies=cookies,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_http_download_done() -> None:
    """GET /{job_id}/download returns PDF bytes when status is 'done'."""
    tid = uuid4()
    user = _make_mock_user(tid)
    job = _make_job(tid, "churn", "done")
    fake_pdf = b"%PDF-1.4 fake content for test"
    _pdf_cache[str(job.id)] = fake_pdf
    cookies = _jwt_cookies(user)

    async def db_override() -> AsyncGenerator[AsyncMock, None]:
        yield _mock_db(job=job)

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                f"/api/v1/reports/{job.id}/download",
                cookies=cookies,
            )
    finally:
        _pdf_cache.pop(str(job.id), None)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == fake_pdf


@pytest.mark.asyncio
async def test_http_download_not_done_returns_409() -> None:
    """GET /download returns 409 when job is still pending."""
    tid = uuid4()
    user = _make_mock_user(tid)
    job = _make_job(tid, "team_performance", "pending")
    cookies = _jwt_cookies(user)

    async def db_override() -> AsyncGenerator[AsyncMock, None]:
        yield _mock_db(job=job)

    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = db_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            f"/api/v1/reports/{job.id}/download",
            cookies=cookies,
        )

    assert resp.status_code == 409
