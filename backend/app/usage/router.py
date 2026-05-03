"""HTTP router for usage metering (Feature #8).

Endpoints
---------
GET  /api/v1/billing/usage          → aggregated summary for a period
GET  /api/v1/billing/usage/events   → raw event rows (paginated)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.usage.schemas import (
    UsageEventRead,
    UsagePeriod,
    UsageSummaryResponse,
)
from app.usage.service import get_usage_summary, list_usage_events

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/usage",
    response_model=UsageSummaryResponse,
    summary="Usage summary for the current tenant",
)
async def usage_summary(
    period: Annotated[
        UsagePeriod,
        Query(description="Billing period: current_month | last_month | last_7_days | last_30_days"),
    ] = "current_month",
    user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryResponse:
    """Return aggregated usage totals (tokens, MCP calls, etc.) for the authenticated tenant.

    Args:
        period: Which billing period to query. Defaults to ``current_month``.
        user: The authenticated user (injected by dependency).
        db: Async database session (injected by dependency).

    Returns:
        ``UsageSummaryResponse`` with start/end bounds and per-event-type totals.

    Example response:
        ```json
        {
          "period": "current_month",
          "start": "2026-05-01T00:00:00Z",
          "end": "2026-06-01T00:00:00Z",
          "items": [
            {"event_type": "llm_tokens_input", "total": 45320},
            {"event_type": "llm_tokens_output", "total": 12870},
            {"event_type": "mcp_calls", "total": 384}
          ]
        }
        ```
    """
    return await get_usage_summary(db, user.org_id, period)


@router.get(
    "/usage/events",
    response_model=list[UsageEventRead],
    summary="Raw usage events for the current tenant (paginated)",
)
async def usage_events(
    period: Annotated[
        UsagePeriod,
        Query(description="Billing period"),
    ] = "current_month",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[UsageEventRead]:
    """Return raw usage_events rows for the authenticated tenant.

    Args:
        period: Which billing period to query. Defaults to ``current_month``.
        limit: Maximum rows per page (1–500, default 100).
        offset: Pagination offset.
        user: The authenticated user (injected by dependency).
        db: Async database session (injected by dependency).

    Returns:
        List of ``UsageEventRead`` schemas, ordered newest-first.
    """
    return await list_usage_events(db, user.org_id, period, limit=limit, offset=offset)
