"""Activity timeline API endpoint.

Routes
------
GET /api/v1/activities/{entity_type}/{entity_id}
    Returns the last N activity events for a CRM entity.
    Query params:
      limit (int, 1-200, default 50)
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.models.user import User

from .schemas import ENTITY_TYPES, ActivityPublic
from .service import get_timeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["activities"])


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=list[ActivityPublic],
    summary="Get activity timeline for a CRM entity",
)
async def get_entity_timeline(
    entity_type: str,
    entity_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityPublic]:
    """Return the activity timeline for a contact, account, or deal.

    Events are returned newest-first. The maximum page size is 200; use
    ``limit`` to control how many entries are returned.

    Args:
        entity_type: One of ``contact``, ``account``, ``deal``.
        entity_id: UUID of the entity.
        limit: Number of events to return (1–200, default 50).
        current_user: Authenticated user (injected by FastAPI).
        db: Database session (injected by FastAPI).

    Returns:
        List of activity events, newest first.

    Raises:
        HTTPException: 422 if entity_type is not recognised.
    """
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid entity_type '{entity_type}'. Valid values: {sorted(ENTITY_TYPES)}",
        )

    activities = await get_timeline(
        db=db,
        tenant_id=current_user.tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )
    return [ActivityPublic.model_validate(a) for a in activities]
