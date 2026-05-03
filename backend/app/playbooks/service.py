"""Playbook CRUD, event publishing, and background worker.

Event bus
---------
A module-level ``asyncio.Queue`` acts as the in-process event bus.
Producers call ``publish_playbook_event(event_dict)`` (fire-and-forget).
The background worker (``run_worker``) consumes events and runs matching
active playbooks.

Event dict structure
--------------------
::

    {
        "event": "deal.stage_changed",
        "tenant_id": "<uuid-str>",
        "entity_type": "deal",
        "entity_id": "<uuid-str>",
        "payload": {
            "deal_id": "<uuid-str>",
            "stage": "negotiation",
            "old_stage": "proposal",
            "contact_id": "<uuid-str>|null",
        },
    }
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncContextManager, Callable
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook import Playbook, PlaybookRun
from app.playbooks.executor import evaluate_conditions, execute_action
from app.playbooks.schemas import PlaybookCreate, PlaybookUpdate

logger = logging.getLogger(__name__)

# In-process event queue — no Redis required.
# maxsize=1000 acts as a back-pressure valve; if the queue fills up we drop
# rather than blocking the caller (CRM service).
_event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)


# ---------------------------------------------------------------------------
# Event publishing
# ---------------------------------------------------------------------------


def publish_playbook_event(event: dict[str, Any]) -> None:
    """Enqueue a CRM event for playbook evaluation (fire-and-forget).

    Safe to call from non-async code (uses put_nowait).

    Args:
        event: Event dict with keys ``event``, ``tenant_id``, ``entity_type``,
            ``entity_id``, and ``payload``.
    """
    try:
        _event_queue.put_nowait(event)
        logger.debug("Playbook event enqueued: %s", event.get("event"))
    except asyncio.QueueFull:
        logger.warning(
            "Playbook event queue full — dropping event: %s tenant=%s",
            event.get("event"),
            event.get("tenant_id"),
        )


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


async def create_playbook(
    db: AsyncSession,
    tenant_id: UUID,
    data: PlaybookCreate,
) -> Playbook:
    """Persist a new playbook for *tenant_id*.

    Args:
        db: Async database session.
        tenant_id: Owning tenant.
        data: Validated creation payload.

    Returns:
        The newly created Playbook ORM instance.
    """
    playbook = Playbook(
        id=uuid4(),
        tenant_id=tenant_id,
        name=data.name,
        description=data.description,
        trigger_event=data.trigger_event,
        trigger_conditions=data.trigger_conditions,
        actions=data.actions,
        is_active=data.is_active,
    )
    db.add(playbook)
    await db.commit()
    await db.refresh(playbook)
    return playbook


async def list_playbooks(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    page: int = 1,
    limit: int = 20,
    active_only: bool = False,
) -> tuple[list[Playbook], int]:
    """Return a paginated list of playbooks for *tenant_id*.

    Args:
        db: Async database session.
        tenant_id: Owning tenant.
        page: 1-based page number.
        limit: Page size (max 100).
        active_only: If True, only return is_active=True playbooks.

    Returns:
        Tuple of (items, total_count).
    """
    q = select(Playbook).where(Playbook.tenant_id == tenant_id)
    if active_only:
        q = q.where(Playbook.is_active.is_(True))
    total = (
        await db.execute(
            select(func.count()).select_from(
                q.subquery()
            )
        )
    ).scalar_one()
    items = (
        await db.execute(
            q.order_by(Playbook.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).scalars().all()
    return list(items), total


async def get_playbook(
    db: AsyncSession,
    playbook_id: UUID,
    tenant_id: UUID,
) -> Playbook | None:
    """Fetch a single playbook by id + tenant (tenant isolation).

    Args:
        db: Async database session.
        playbook_id: Playbook primary key.
        tenant_id: Must match the playbook's tenant_id.

    Returns:
        Playbook instance or None if not found.
    """
    return (
        await db.execute(
            select(Playbook).where(
                Playbook.id == playbook_id,
                Playbook.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()


async def update_playbook(
    db: AsyncSession,
    playbook_id: UUID,
    tenant_id: UUID,
    data: PlaybookUpdate,
) -> Playbook | None:
    """Apply a partial update to a playbook.

    Args:
        db: Async database session.
        playbook_id: Target playbook id.
        tenant_id: Must match the playbook's tenant_id.
        data: Fields to update (None fields are skipped).

    Returns:
        Updated Playbook or None if not found.
    """
    playbook = await get_playbook(db, playbook_id, tenant_id)
    if playbook is None:
        return None

    updates = data.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(playbook, field, value)

    await db.commit()
    await db.refresh(playbook)
    return playbook


async def delete_playbook(
    db: AsyncSession,
    playbook_id: UUID,
    tenant_id: UUID,
) -> bool:
    """Delete a playbook (and cascade-delete its runs).

    Args:
        db: Async database session.
        playbook_id: Target playbook id.
        tenant_id: Must match the playbook's tenant_id.

    Returns:
        True if deleted, False if not found.
    """
    playbook = await get_playbook(db, playbook_id, tenant_id)
    if playbook is None:
        return False
    await db.delete(playbook)
    await db.commit()
    return True


async def list_runs(
    db: AsyncSession,
    playbook_id: UUID,
    tenant_id: UUID,
    *,
    limit: int = 20,
) -> list[PlaybookRun]:
    """Return the most recent runs for a playbook.

    Args:
        db: Async database session.
        playbook_id: Target playbook id.
        tenant_id: Owning tenant (tenant isolation check).
        limit: Maximum number of runs to return.

    Returns:
        List of PlaybookRun ordered newest-first.
    """
    rows = await db.execute(
        select(PlaybookRun)
        .where(
            PlaybookRun.playbook_id == playbook_id,
            PlaybookRun.tenant_id == tenant_id,
        )
        .order_by(PlaybookRun.started_at.desc())
        .limit(limit)
    )
    return list(rows.scalars().all())


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


async def _fetch_active_playbooks_for_event(
    db: AsyncSession,
    tenant_id: UUID,
    trigger_event: str,
) -> list[Playbook]:
    """Return active playbooks that match *trigger_event* for *tenant_id*.

    Args:
        db: Async database session.
        tenant_id: Owning tenant.
        trigger_event: Event name to filter by.

    Returns:
        List of matching Playbook instances.
    """
    rows = await db.execute(
        select(Playbook).where(
            Playbook.tenant_id == tenant_id,
            Playbook.trigger_event == trigger_event,
            Playbook.is_active.is_(True),
        )
    )
    return list(rows.scalars().all())


async def run_playbook(
    db: AsyncSession,
    playbook: Playbook,
    event: dict[str, Any],
) -> PlaybookRun:
    """Execute all actions of *playbook* and persist a run record.

    The run is created with status ``running``, actions are executed
    sequentially, then status transitions to ``completed`` or ``failed``.

    Args:
        db: Async database session.
        playbook: The playbook to execute.
        event: Full event dict (fields: event, tenant_id, entity_type,
            entity_id, payload).

    Returns:
        The persisted PlaybookRun.
    """
    entity_id_str = event.get("entity_id")
    run = PlaybookRun(
        id=uuid4(),
        tenant_id=playbook.tenant_id,
        playbook_id=playbook.id,
        trigger_event=event.get("event", "manual"),
        entity_type=event.get("entity_type"),
        entity_id=UUID(entity_id_str) if entity_id_str else None,
        status="running",
    )
    db.add(run)
    await db.flush()

    payload: dict[str, Any] = event.get("payload", {})
    action_results: list[dict[str, Any]] = []
    error_msg: str | None = None

    try:
        for action in (playbook.actions or []):
            result = await execute_action(db, playbook.tenant_id, action, payload)
            action_results.append({"action": action.get("type"), "result": result})
        run.status = "completed"
        run.result = {"actions_executed": action_results}
        logger.info(
            "Playbook completed | id=%s name=%s tenant=%s",
            playbook.id,
            playbook.name,
            playbook.tenant_id,
        )
    except Exception as exc:
        error_msg = str(exc)
        run.status = "failed"
        run.error = error_msg
        logger.error(
            "Playbook failed | id=%s name=%s error=%s",
            playbook.id,
            playbook.name,
            error_msg,
        )
    finally:
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(run)

    asyncio.ensure_future(_notify_playbook_run(run, playbook))
    return run


async def _notify_playbook_run(run: Any, playbook: Any) -> None:
    """Fire-and-forget helper: create a notification after a playbook run.

    Uses a separate DB session so the caller's session is already committed.

    Args:
        run: The PlaybookRun ORM object (already committed).
        playbook: The Playbook ORM object (already committed).
    """
    from app.common.db import AsyncSessionLocal
    from app.notifications.schemas import NotificationCreate
    from app.notifications.service import create_notification

    status_label = "exécuté" if run.status == "completed" else "échoué"
    async with AsyncSessionLocal() as notif_db:
        try:
            await create_notification(
                notif_db,
                NotificationCreate(
                    tenant_id=playbook.tenant_id,
                    type="playbook_triggered",
                    title=f"Playbook '{playbook.name}' {status_label}",
                    data={
                        "playbook_id": str(playbook.id),
                        "run_id": str(run.id),
                        "status": run.status,
                    },
                ),
            )
            await notif_db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Playbook notification failed: %s", exc)





# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


async def run_worker(
    db_factory: Callable[[], AsyncContextManager[AsyncSession]],
) -> None:
    """Process playbook events from the in-process queue indefinitely.

    Intended to run as an asyncio background task (started in main.py lifespan).
    Cancellation is handled gracefully.

    Args:
        db_factory: Async context-manager factory yielding an AsyncSession.
    """
    logger.info("Playbook worker started")
    while True:
        try:
            event: dict[str, Any] = await asyncio.wait_for(
                _event_queue.get(), timeout=5.0
            )
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            logger.info("Playbook worker cancelled")
            raise

        tenant_id_str: str = event.get("tenant_id", "")
        trigger_event: str = event.get("event", "")
        payload: dict[str, Any] = event.get("payload", {})

        if not tenant_id_str or not trigger_event:
            logger.warning("Playbook worker: malformed event dropped: %r", event)
            continue

        try:
            tenant_id = UUID(tenant_id_str)
        except ValueError:
            logger.warning("Playbook worker: invalid tenant_id %r", tenant_id_str)
            continue

        try:
            async with db_factory() as db:
                playbooks = await _fetch_active_playbooks_for_event(
                    db, tenant_id, trigger_event
                )
                for playbook in playbooks:
                    if evaluate_conditions(playbook.trigger_conditions or [], payload):
                        with contextlib.suppress(Exception):
                            await run_playbook(db, playbook, event)
                    else:
                        logger.debug(
                            "Playbook %s conditions not met for event %s",
                            playbook.id,
                            trigger_event,
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Playbook worker error processing event %s: %s", trigger_event, exc)
