"""HTTP router for the AI lead scoring feature.

Routes
------
POST /score-lead   (mounted at /internal/v1/scoring in main.py)
    Score a CRM contact using LLM or heuristic fallback.
    Protected by the INTERNAL_API_PREFIX middleware (x-internal-api-key + x-tenant-id).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db import get_db
from app.config import settings
from app.scoring.schemas import ScoreLeadRequest, ScoreLeadResponse
from app.scoring.service import score_lead

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/score-lead",
    response_model=ScoreLeadResponse,
    status_code=status.HTTP_200_OK,
    summary="AI lead score for a CRM contact (internal)",
)
async def score_lead_endpoint(
    body: ScoreLeadRequest,
    db: AsyncSession = Depends(get_db),
) -> ScoreLeadResponse:
    """Score a lead using LLM or heuristic fallback.

    Protected by the ``x-internal-api-key`` header validated in TenantMiddleware.
    The ``x-tenant-id`` header is also required and must match ``body.tenant_id``.

    Args:
        body: ScoreLeadRequest with tenant_id, contact_id, and optional force_refresh.
        db: Async database session.

    Returns:
        ScoreLeadResponse with score 0-100, reasoning, recommended_action, cached flag.

    Raises:
        HTTPException: 404 if the contact is not found for this tenant.
    """
    try:
        return await score_lead(
            db,
            tenant_id=body.tenant_id,
            contact_id=body.contact_id,
            force_refresh=body.force_refresh,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
