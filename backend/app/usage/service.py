"""Business logic for usage metering (Feature #8).

Design:
- ``record_usage`` writes a single usage_events row. Called fire-and-forget
  from the sessions SSE proxy after each orchestrator stream completes.
- ``get_usage_summary`` aggregates by event_type for a given period.
- ``get_usage_events`` returns the raw rows for a tenant + period (paginated).
- Period helpers convert human-readable labels to [start, end) UTC ranges.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from app.common.utils import utcnow
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_event import UsageEvent
from app.usage.schemas import (
    UsageEventCreate,
    UsageEventRead,
    UsagePeriod,
    UsageSummaryItem,
    UsageSummaryResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------


def _period_bounds(period: UsagePeriod) -> tuple[datetime, datetime]:
    """Compute (start_inclusive, end_exclusive) UTC datetimes for a period label.

    Args:
        period: One of current_month | last_month | last_7_days | last_30_days.

    Returns:
        Tuple of (start, end) as timezone-aware UTC datetimes.

    Raises:
        ValueError: If the period label is not recognised.
    """
    now = utcnow()

    if period == "current_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # End = first day of next month
        if now.month == 12:
            end = start.replace(year=now.year + 1, month=1)
        else:
            end = start.replace(month=now.month + 1)
        return start, end

    if period == "last_month":
        first_of_current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if first_of_current.month == 1:
            start = first_of_current.replace(year=first_of_current.year - 1, month=12)
        else:
            start = first_of_current.replace(month=first_of_current.month - 1)
        return start, first_of_current

    if period == "last_7_days":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        start = end - timedelta(days=7)
        return start, end

    if period == "last_30_days":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        start = end - timedelta(days=30)
        return start, end

    raise ValueError(f"Unknown period: {period!r}")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


async def record_usage(db: AsyncSession, data: UsageEventCreate) -> UsageEvent:
    """Persist a single usage event to the database.

    Args:
        db: Async SQLAlchemy session.
        data: Usage event data to persist.

    Returns:
        The newly created ``UsageEvent`` ORM instance (after flush).

    Raises:
        sqlalchemy.exc.IntegrityError: If ``tenant_id`` does not exist.
    """
    event = UsageEvent(
        id=uuid4(),
        tenant_id=data.tenant_id,
        event_type=data.event_type,
        quantity=data.quantity,
        event_metadata=data.metadata,
        ts=utcnow(),
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


async def get_usage_summary(
    db: AsyncSession,
    tenant_id: UUID,
    period: UsagePeriod,
) -> UsageSummaryResponse:
    """Aggregate usage totals per event_type for a given period.

    Args:
        db: Async SQLAlchemy session.
        tenant_id: Tenant to query.
        period: Human-readable period label.

    Returns:
        ``UsageSummaryResponse`` with start/end bounds and per-type totals.
    """
    start, end = _period_bounds(period)

    stmt = (
        select(UsageEvent.event_type, func.sum(UsageEvent.quantity).label("total"))
        .where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.ts >= start,
            UsageEvent.ts < end,
        )
        .group_by(UsageEvent.event_type)
        .order_by(UsageEvent.event_type)
    )
    result = await db.execute(stmt)
    rows = result.all()

    items = [UsageSummaryItem(event_type=row.event_type, total=int(row.total)) for row in rows]
    return UsageSummaryResponse(period=period, start=start, end=end, items=items)


async def list_usage_events(
    db: AsyncSession,
    tenant_id: UUID,
    period: UsagePeriod,
    limit: int = 200,
    offset: int = 0,
) -> list[UsageEventRead]:
    """Return raw usage event rows for a tenant/period (paginated).

    Args:
        db: Async SQLAlchemy session.
        tenant_id: Tenant to query.
        period: Human-readable period label.
        limit: Maximum rows to return (default 200, max 500).
        offset: Pagination offset.

    Returns:
        List of ``UsageEventRead`` schemas, ordered newest-first.
    """
    start, end = _period_bounds(period)
    limit = min(limit, 500)

    stmt = (
        select(UsageEvent)
        .where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.ts >= start,
            UsageEvent.ts < end,
        )
        .order_by(UsageEvent.ts.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [UsageEventRead.model_validate(row) for row in rows]
