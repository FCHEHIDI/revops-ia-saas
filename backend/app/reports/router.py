"""FastAPI router for Feature #7 — PDF Reports.

Endpoints
---------
POST /api/v1/reports/generate          — kick off async report generation
GET  /api/v1/reports/                  — list recent jobs for tenant
GET  /api/v1/reports/{job_id}/status   — poll job status
GET  /api/v1/reports/{job_id}/stream   — SSE progress stream
GET  /api/v1/reports/{job_id}/download — download the generated PDF

All endpoints require a valid JWT (TenantMiddleware enforces auth).
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.common.db import AsyncSessionLocal, get_db
from app.models.user import User
from app.reports import service as svc
from app.reports.schemas import ReportGenerateRequest, ReportJobStatusRead

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    response_model=ReportJobStatusRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate a PDF report (async)",
)
async def generate_report(
    body: ReportGenerateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ReportJobStatusRead:
    """Create an async report generation job and return its initial status.

    The report is generated in the background.  Poll
    ``GET /{job_id}/status`` or subscribe to ``GET /{job_id}/stream``
    (SSE) to track progress.

    Args:
        body: Report type and optional parameters.
        current_user: Authenticated user (provides tenant_id).
        db: Database session.

    Returns:
        Initial ReportJobStatusRead with status='pending'.
    """
    job = await svc.create_report_job(db, current_user.tenant_id, body)
    await db.commit()
    await db.refresh(job)

    asyncio.create_task(
        svc.run_report_job(
            _make_db_factory(),
            job.id,
            current_user.tenant_id,
        )
    )
    return svc.to_status_read(job)


def _make_db_factory():
    """Return an async context manager factory backed by AsyncSessionLocal.

    Returns:
        Callable that yields AsyncSession.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _factory():
        async with AsyncSessionLocal() as session:
            yield session

    return _factory


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=list[ReportJobStatusRead],
    summary="List recent report jobs",
)
async def list_report_jobs(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReportJobStatusRead]:
    """Return the 20 most recent report jobs for the current tenant.

    Args:
        current_user: Authenticated user.
        db: Database session.

    Returns:
        List of ReportJobStatusRead, newest first.
    """
    jobs = await svc.list_report_jobs(db, current_user.tenant_id)
    return [svc.to_status_read(j) for j in jobs]


# ---------------------------------------------------------------------------
# GET /{job_id}/status
# ---------------------------------------------------------------------------


@router.get(
    "/{job_id}/status",
    response_model=ReportJobStatusRead,
    summary="Poll report job status",
)
async def get_report_status(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ReportJobStatusRead:
    """Fetch current status of a report job.

    Args:
        job_id: Target job UUID.
        current_user: Authenticated user.
        db: Database session.

    Returns:
        ReportJobStatusRead with download_url if status is 'done'.

    Raises:
        HTTPException 404: If job not found or not owned by tenant.
    """
    job = await svc.get_report_job(db, current_user.tenant_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report job not found",
        )
    return svc.to_status_read(job)


# ---------------------------------------------------------------------------
# GET /{job_id}/stream  — SSE
# ---------------------------------------------------------------------------


@router.get(
    "/{job_id}/stream",
    summary="SSE stream of report generation progress",
)
async def stream_report_progress(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """Subscribe to Server-Sent Events for report job progress.

    Emits one event per status transition until the job reaches
    ``done`` or ``failed`` (or a 60-second timeout elapses).

    Args:
        job_id: Target job UUID.
        current_user: Authenticated user.

    Returns:
        StreamingResponse with media_type='text/event-stream'.
    """
    tenant_id = current_user.tenant_id

    async def _event_gen():
        seen_status: str | None = None
        for _ in range(120):  # max 60s at 0.5s intervals
            await asyncio.sleep(0.5)
            async with AsyncSessionLocal() as db:
                job = await svc.get_report_job(db, tenant_id, job_id)
            if job is None:
                yield f"data: {json.dumps({'event': 'error', 'message': 'not found'})}\n\n"
                return
            if job.status != seen_status:
                seen_status = job.status
                payload = json.dumps(
                    {"event": job.status, "job_id": str(job_id)}
                )
                yield f"data: {payload}\n\n"
            if job.status in ("done", "failed"):
                return

    return StreamingResponse(_event_gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /{job_id}/download
# ---------------------------------------------------------------------------


@router.get(
    "/{job_id}/download",
    summary="Download the generated PDF report",
)
async def download_report(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the PDF for a completed report job.

    Args:
        job_id: Target job UUID.
        current_user: Authenticated user.
        db: Database session.

    Returns:
        PDF response with appropriate Content-Disposition header.

    Raises:
        HTTPException 404: If job not found or PDF not yet available.
        HTTPException 409: If job is not yet completed.
    """
    job = await svc.get_report_job(db, current_user.tenant_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report job not found",
        )
    if job.status != "done":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Report is not ready yet (status: {job.status})",
        )
    pdf_bytes = svc.get_pdf_bytes(job_id)
    if pdf_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF data not found in cache",
        )
    filename = f"report_{job.report_type}_{job_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
