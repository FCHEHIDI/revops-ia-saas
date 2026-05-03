"""Playbook action executor and condition evaluator.

Condition evaluation
--------------------
Each condition is a dict ``{"field": str, "op": str, "value": Any}``.
Fields are looked up in the flat event payload dict.  All conditions must
pass for the playbook to run (AND semantics).  An empty condition list
always passes.

Supported ops:
- ``eq``  — exact equality
- ``ne``  — not equal
- ``gte`` — numeric greater-or-equal
- ``lte`` — numeric less-or-equal
- ``in``  — value is member of a list
- ``contains`` — string contains substring

Action execution
----------------
Each action dict must have a ``type`` key.  The executor dispatches to the
appropriate private handler which may perform DB writes.  Every handler
returns a plain dict result that is recorded in ``PlaybookRun.result``.

Supported action types
~~~~~~~~~~~~~~~~~~~~~~
- ``add_note``          — append an Activity row to the timeline.
- ``update_deal_stage`` — transition a Deal to a new stage.
- ``score_lead``        — invoke the AI lead scoring service.
- ``send_notification`` — log a notification message (Slack/webhook stub).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities.service import record as _record_activity
from app.config import settings as _settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Condition evaluator
# ---------------------------------------------------------------------------


def evaluate_conditions(conditions: list[dict[str, Any]], payload: dict[str, Any]) -> bool:
    """Return True when all conditions evaluate to True against *payload*.

    Args:
        conditions: List of condition dicts (may be empty → always True).
        payload: Flat event payload dict used as the data source.

    Returns:
        True if every condition passes, False if any fails.
    """
    for cond in conditions:
        field: str = cond.get("field", "")
        op: str = cond.get("op", "eq")
        expected: Any = cond.get("value")
        actual: Any = payload.get(field)

        try:
            if op == "eq":
                if actual != expected:
                    return False
            elif op == "ne":
                if actual == expected:
                    return False
            elif op == "gte":
                if float(actual) < float(expected):
                    return False
            elif op == "lte":
                if float(actual) > float(expected):
                    return False
            elif op == "in":
                if not isinstance(expected, list) or actual not in expected:
                    return False
            elif op == "contains":
                if not isinstance(actual, str) or str(expected) not in actual:
                    return False
        except (TypeError, ValueError):
            logger.debug("Condition evaluation error: field=%s op=%s actual=%r expected=%r", field, op, actual, expected)
            return False

    return True


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------


async def _action_add_note(
    db: AsyncSession,
    tenant_id: UUID,
    action: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Append an activity note to the CRM timeline.

    Args:
        db: Database session.
        tenant_id: Owning tenant.
        action: Action config dict — expects optional ``entity_type`` and
            ``entity_id``, required ``content``.  Falls back to payload fields.
        payload: Event payload for context (deal_id, contact_id, entity_id…).

    Returns:
        Dict with entity_id and content written.
    """
    entity_type: str = action.get("entity_type") or payload.get("entity_type", "deal")
    # Resolve entity_id: action → payload.entity_id → payload.deal_id → payload.contact_id
    raw_id = (
        action.get("entity_id")
        or payload.get("entity_id")
        or payload.get("deal_id")
        or payload.get("contact_id")
    )
    if not raw_id:
        raise ValueError("add_note action: could not resolve entity_id from event payload")

    entity_id = UUID(str(raw_id))
    content: str = action.get("content") or "Automated note from playbook"

    await _record_activity(
        db,
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type="note_added",
        actor_id=None,
        payload={"content": content, "source": "playbook"},
    )
    return {"entity_type": entity_type, "entity_id": str(entity_id), "content": content}


async def _action_update_deal_stage(
    db: AsyncSession,
    tenant_id: UUID,
    action: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Transition a deal to a new stage.

    Args:
        db: Database session.
        tenant_id: Owning tenant (used for RLS-style safety check).
        action: Action config dict — requires ``new_stage``.
        payload: Event payload — must supply ``deal_id``.

    Returns:
        Dict with deal_id and new_stage applied.

    Raises:
        ValueError: If deal_id or new_stage is missing, or deal not found.
    """
    raw_deal_id = action.get("deal_id") or payload.get("deal_id")
    if not raw_deal_id:
        raise ValueError("update_deal_stage action: deal_id missing from action and payload")
    new_stage: str = action.get("new_stage", "")
    if not new_stage:
        raise ValueError("update_deal_stage action: new_stage is required")

    deal_id = UUID(str(raw_deal_id))
    from app.crm.models import Deal  # local import avoids circular dependency
    result = await db.execute(
        update(Deal)
        .where(Deal.id == deal_id, Deal.org_id == tenant_id)
        .values(stage=new_stage)
        .returning(Deal.id)
    )
    if result.scalar_one_or_none() is None:
        raise ValueError(f"update_deal_stage action: deal {deal_id} not found for tenant")

    await db.flush()
    return {"deal_id": str(deal_id), "new_stage": new_stage}


async def _action_score_lead(
    db: AsyncSession,
    tenant_id: UUID,
    action: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Trigger AI lead scoring for a contact.

    Args:
        db: Database session.
        tenant_id: Owning tenant.
        action: Action config dict — optional ``contact_id`` override.
        payload: Event payload — must supply ``contact_id`` if not in action.

    Returns:
        Dict with contact_id, score, and model_used.

    Raises:
        ValueError: If contact_id is missing or contact not found.
    """
    # Local import to avoid circular dependency at module level
    from app.scoring.service import score_lead

    raw_contact_id = action.get("contact_id") or payload.get("contact_id")
    if not raw_contact_id:
        raise ValueError("score_lead action: contact_id missing from action and payload")

    contact_id = UUID(str(raw_contact_id))
    resp = await score_lead(
        db,
        tenant_id=tenant_id,
        contact_id=contact_id,
        force_refresh=False,
        settings=_settings,
    )
    return {"contact_id": str(contact_id), "score": resp.score, "model_used": resp.model_used}


async def _action_send_notification(
    db: AsyncSession,
    tenant_id: UUID,
    action: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Log a notification message (Slack/webhook stub for future extension).

    Args:
        db: Database session (unused — kept for uniform signature).
        tenant_id: Owning tenant.
        action: Action config dict — expects ``message``.
        payload: Event payload for context.

    Returns:
        Dict with the message that was logged.
    """
    message: str = action.get("message") or "Playbook notification"
    logger.info(
        "Playbook notification | tenant=%s | message=%s | payload=%r",
        tenant_id,
        message,
        payload,
    )
    return {"message": message, "status": "logged"}


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_ACTION_HANDLERS = {
    "add_note": _action_add_note,
    "update_deal_stage": _action_update_deal_stage,
    "score_lead": _action_score_lead,
    "send_notification": _action_send_notification,
}


async def execute_action(
    db: AsyncSession,
    tenant_id: UUID,
    action: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch a single action and return its result dict.

    Args:
        db: Database session.
        tenant_id: Owning tenant.
        action: Action config dict with ``type`` key.
        payload: Event payload for context.

    Returns:
        Action result dict (structure depends on action type).

    Raises:
        ValueError: If action type is unknown or handler raises.
    """
    action_type: str = action.get("type", "")
    handler = _ACTION_HANDLERS.get(action_type)
    if handler is None:
        raise ValueError(f"Unknown action type: {action_type!r}")
    return await handler(db, tenant_id, action, payload)
