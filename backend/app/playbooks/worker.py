"""Playbook event bus and background worker.

Extracted from ``playbooks/service.py`` to respect SRP.

The in-process ``asyncio.Queue`` acts as the event bus.  Producers call
``publish_playbook_event`` (fire-and-forget, safe from sync code).
``run_worker`` is the asyncio background task started by the main lifespan.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, AsyncContextManager, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# In-process event queue — no Redis required.
# maxsize=1000 acts as a back-pressure valve; if the queue fills up we drop
# rather than blocking the caller (CRM service).
_event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)


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


async def run_worker(
    db_factory: Callable[[], AsyncContextManager[AsyncSession]],
) -> None:
    """Process playbook events from the in-process queue indefinitely.

    Intended to run as an asyncio background task (started in main.py lifespan).
    Cancellation is handled gracefully.

    Args:
        db_factory: Async context-manager factory yielding an AsyncSession.
    """
    # Deferred import avoids circular dependency (worker → service → worker)
    from app.playbooks.service import _fetch_active_playbooks_for_event, run_playbook
    from app.playbooks.executor import evaluate_conditions

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
            logger.error(
                "Playbook worker error processing event %s: %s", trigger_event, exc
            )
