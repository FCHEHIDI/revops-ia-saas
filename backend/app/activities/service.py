"""Activity timeline service — write and read entity events.

All callers should use ``record`` to append events. The function is
fire-and-forget friendly: it never raises; errors are logged only.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity

logger = logging.getLogger(__name__)


async def record(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    entity_type: str,
    entity_id: UUID,
    activity_type: str,
    actor_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one activity event to the timeline.

    Silently drops the event (with a warning log) if the DB write fails so
    that a timeline failure never breaks the primary operation that called it.

    Args:
        db: Async SQLAlchemy session (already open, caller manages transaction).
        tenant_id: Tenant that owns the entity.
        entity_type: ``"contact"``, ``"account"``, or ``"deal"``.
        entity_id: UUID of the entity the event belongs to.
        activity_type: One of the values in ``ACTIVITY_TYPES``.
        actor_id: UUID of the user who triggered the event, or None for
            system-generated events.
        payload: Arbitrary metadata dict (stored as JSONB). Defaults to ``{}``.
    """
    try:
        activity = Activity(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            type=activity_type,
            payload=payload or {},
        )
        db.add(activity)
        await db.flush()  # write within the caller's transaction; commit is theirs
    except Exception as exc:
        logger.warning(
            "activities: failed to record %s for %s/%s: %s",
            activity_type,
            entity_type,
            entity_id,
            exc,
        )


async def get_timeline(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    entity_type: str,
    entity_id: UUID,
    limit: int = 50,
) -> list[Activity]:
    """Fetch the most recent activities for one entity.

    Args:
        db: Async SQLAlchemy session.
        tenant_id: Tenant UUID (enforces ownership).
        entity_type: Entity type to filter on.
        entity_id: Entity UUID to filter on.
        limit: Maximum number of entries (default 50, max 200).

    Returns:
        List of ``Activity`` instances ordered newest-first.
    """
    limit = min(limit, 200)
    result = await db.execute(
        select(Activity)
        .where(
            Activity.tenant_id == tenant_id,
            Activity.entity_type == entity_type,
            Activity.entity_id == entity_id,
        )
        .order_by(Activity.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
