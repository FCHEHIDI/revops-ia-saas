"""PDF Reports service — data fetching, PDF rendering, and job lifecycle.

Job lifecycle
-------------
pending → generating_data → rendering → done
                                       ↘ failed

PDF storage
-----------
Generated PDFs are held in the module-level ``_pdf_cache`` dict (keyed by
``str(job_id)``) for the lifetime of the process.  In production this would
be replaced by an object-store (mcp-filesystem / S3), but the in-process dict
is sufficient for development and unit tests.

Report types
------------
- ``pipeline``       — deals by stage: count, value, win rate
- ``mrr``            — accounts with ARR: top accounts, total ARR
- ``team_performance`` — deals by sales rep (owner_id): count, won, value
- ``churn``          — accounts by status: churn rate, total contacts
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from app.common.utils import utcnow
from typing import Any, AsyncContextManager, Callable
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crm.models import Account, Contact, Deal
from app.models.report_job import ReportJob
from app.reports.pdf_renderer import render_pdf
from app.reports.schemas import ReportGenerateRequest, ReportJobStatusRead

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process PDF cache: job_id → PDF bytes
# ---------------------------------------------------------------------------
_pdf_cache: dict[str, bytes] = {}


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


async def create_report_job(
    db: AsyncSession,
    tenant_id: UUID,
    req: ReportGenerateRequest,
) -> ReportJob:
    """Create a new ReportJob record with status 'pending'.

    Args:
        db: Database session.
        tenant_id: Owning tenant UUID.
        req: Validated generate request.

    Returns:
        Persisted ReportJob (not committed — caller must flush/commit or rely
        on session teardown).
    """
    job = ReportJob(
        id=uuid4(),
        tenant_id=tenant_id,
        report_type=req.report_type,
        status="pending",
        parameters=req.parameters or None,
        created_at=utcnow(),
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


async def get_report_job(
    db: AsyncSession,
    tenant_id: UUID,
    job_id: UUID,
) -> ReportJob | None:
    """Fetch a single ReportJob by id, scoped to tenant.

    Args:
        db: Database session.
        tenant_id: Owning tenant UUID.
        job_id: Target job UUID.

    Returns:
        ReportJob if found and owned by tenant, else None.
    """
    result = await db.execute(
        select(ReportJob).where(
            ReportJob.id == job_id,
            ReportJob.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def list_report_jobs(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    limit: int = 20,
) -> list[ReportJob]:
    """List recent report jobs for a tenant, newest first.

    Args:
        db: Database session.
        tenant_id: Owning tenant UUID.
        limit: Maximum number of jobs to return.

    Returns:
        List of ReportJob, ordered by created_at descending.
    """
    result = await db.execute(
        select(ReportJob)
        .where(ReportJob.tenant_id == tenant_id)
        .order_by(ReportJob.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def to_status_read(job: ReportJob) -> ReportJobStatusRead:
    """Convert a ReportJob ORM object to ReportJobStatusRead schema.

    Args:
        job: ReportJob ORM instance.

    Returns:
        ReportJobStatusRead with download_url populated when status is 'done'.
    """
    return ReportJobStatusRead(
        id=job.id,
        tenant_id=job.tenant_id,
        report_type=job.report_type,
        status=job.status,
        download_url=(
            f"/api/v1/reports/{job.id}/download"
            if job.status == "done"
            else None
        ),
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


def get_pdf_bytes(job_id: UUID) -> bytes | None:
    """Retrieve cached PDF bytes for a completed job.

    Args:
        job_id: Target job UUID.

    Returns:
        PDF bytes if available in cache, else None.
    """
    return _pdf_cache.get(str(job_id))


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------


async def _fetch_pipeline_data(
    db: AsyncSession, tenant_id: UUID
) -> dict[str, Any]:
    """Fetch pipeline data: deals grouped by stage.

    Args:
        db: Database session.
        tenant_id: Owning tenant UUID.

    Returns:
        Dict with keys: stages, total_deals, total_value, win_rate.
    """
    result = await db.execute(
        select(
            Deal.stage,
            func.count(Deal.id).label("count"),
            func.coalesce(func.sum(Deal.amount), 0).label("total"),
        )
        .where(Deal.org_id == tenant_id)
        .group_by(Deal.stage)
        .order_by(Deal.stage)
    )
    rows = result.all()
    stages = [
        {"stage": r.stage, "count": r.count, "total": float(r.total)}
        for r in rows
    ]
    total_deals = sum(s["count"] for s in stages)
    total_value = sum(s["total"] for s in stages)
    won = next((s for s in stages if s["stage"] == "closed_won"), None)
    win_rate = round((won["count"] / total_deals * 100) if total_deals and won else 0.0, 1)
    return {
        "stages": stages,
        "total_deals": total_deals,
        "total_value": total_value,
        "win_rate": win_rate,
    }


async def _fetch_mrr_data(
    db: AsyncSession, tenant_id: UUID
) -> dict[str, Any]:
    """Fetch MRR data: accounts with ARR, sorted by ARR descending.

    Args:
        db: Database session.
        tenant_id: Owning tenant UUID.

    Returns:
        Dict with keys: accounts (top 20), total_arr.
    """
    result = await db.execute(
        select(Account.name, Account.arr, Account.status, Account.industry)
        .where(Account.org_id == tenant_id, Account.arr.isnot(None))
        .order_by(Account.arr.desc())
        .limit(20)
    )
    rows = result.all()
    accounts = [
        {
            "name": r.name,
            "arr": float(r.arr),
            "status": r.status,
            "industry": r.industry or "N/A",
        }
        for r in rows
    ]
    total_arr = sum(a["arr"] for a in accounts)
    return {"accounts": accounts, "total_arr": total_arr}


async def _fetch_team_performance_data(
    db: AsyncSession, tenant_id: UUID
) -> dict[str, Any]:
    """Fetch team performance data: deals grouped by owner.

    Args:
        db: Database session.
        tenant_id: Owning tenant UUID.

    Returns:
        Dict with keys: reps (list), total_reps.
    """
    result = await db.execute(
        select(
            Deal.owner_id,
            func.count(Deal.id).label("deal_count"),
            func.coalesce(func.sum(Deal.amount), 0).label("total_value"),
            func.count(Deal.id)
            .filter(Deal.stage == "closed_won")
            .label("won_count"),
        )
        .where(Deal.org_id == tenant_id, Deal.owner_id.isnot(None))
        .group_by(Deal.owner_id)
        .order_by(func.sum(Deal.amount).desc().nullslast())
    )
    rows = result.all()
    reps = [
        {
            "owner_id": str(r.owner_id),
            "deal_count": r.deal_count,
            "total_value": float(r.total_value),
            "won_count": r.won_count,
        }
        for r in rows
    ]
    return {"reps": reps, "total_reps": len(reps)}


async def _fetch_churn_data(
    db: AsyncSession, tenant_id: UUID
) -> dict[str, Any]:
    """Fetch churn data: accounts by status, total contacts.

    Args:
        db: Database session.
        tenant_id: Owning tenant UUID.

    Returns:
        Dict with keys: by_status, total_accounts, churned, churn_rate, total_contacts.
    """
    status_result = await db.execute(
        select(Account.status, func.count(Account.id).label("count"))
        .where(Account.org_id == tenant_id)
        .group_by(Account.status)
    )
    by_status = {r.status: r.count for r in status_result.all()}

    contact_result = await db.execute(
        select(func.count(Contact.id)).where(Contact.org_id == tenant_id)
    )
    total_contacts: int = contact_result.scalar_one_or_none() or 0

    total = sum(by_status.values())
    churned = by_status.get("churned", 0)
    churn_rate = round((churned / total * 100) if total else 0.0, 1)

    return {
        "by_status": [{"status": k, "count": v} for k, v in by_status.items()],
        "total_accounts": total,
        "churned": churned,
        "churn_rate": churn_rate,
        "total_contacts": total_contacts,
    }


_FETCHERS: dict[str, Any] = {
    "pipeline": _fetch_pipeline_data,
    "mrr": _fetch_mrr_data,
    "team_performance": _fetch_team_performance_data,
    "churn": _fetch_churn_data,
}


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------


async def run_report_job(
    db_factory: Callable[[], AsyncContextManager[AsyncSession]],
    job_id: UUID,
    tenant_id: UUID,
) -> None:
    """Execute a report job asynchronously: fetch data → render PDF → cache.

    Updates job status through the lifecycle:
    ``pending → generating_data → rendering → done`` (or ``failed``).

    Args:
        db_factory: Async context manager factory that yields an AsyncSession.
        job_id: Job to execute.
        tenant_id: Owning tenant UUID.
    """
    async def _update_status(
        status: str, *, error: str | None = None, file_path: str | None = None
    ) -> None:
        async with db_factory() as db:
            result = await db.execute(
                select(ReportJob).where(ReportJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job is None:
                return
            job.status = status
            if error is not None:
                job.error = error
            if file_path is not None:
                job.file_path = file_path
            if status in ("done", "failed"):
                job.completed_at = utcnow()
            await db.commit()

    try:
        # Step 1 — generating_data
        await _update_status("generating_data")

        async with db_factory() as db:
            result = await db.execute(
                select(ReportJob).where(ReportJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job is None:
                logger.error("run_report_job: job %s not found", job_id)
                return

            fetcher = _FETCHERS.get(job.report_type)
            if fetcher is None:
                await _update_status(
                    "failed",
                    error=f"Unknown report_type: {job.report_type}",
                )
                return

            data = await fetcher(db, tenant_id)

        # Step 2 — rendering
        await _update_status("rendering")
        pdf_bytes = await asyncio.get_event_loop().run_in_executor(
            None, render_pdf, job.report_type, data, tenant_id
        )

        # Step 3 — cache + done
        marker = f"memory:{job_id}"
        _pdf_cache[str(job_id)] = pdf_bytes
        await _update_status("done", file_path=marker)
        logger.info(
            "report job %s completed (%d bytes)",
            job_id,
            len(pdf_bytes),
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("report job %s failed: %s", job_id, exc)
        await _update_status("failed", error=str(exc))
