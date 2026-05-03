"""Pydantic schemas for the activity timeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

# All valid activity type values
ACTIVITY_TYPES: frozenset[str] = frozenset(
    {
        "contact_created",
        "deal_created",
        "deal_stage_changed",
        "note_added",
        "sequence_enrolled",
        "email_sent",
        "email_opened",
        "ai_chat_message",
        "invoice_paid",
        "invoice_overdue",
    }
)

ENTITY_TYPES: frozenset[str] = frozenset({"contact", "account", "deal"})


class ActivityPublic(BaseModel):
    """Single activity entry in the timeline.

    Args:
        id: Activity UUID.
        entity_type: The type of CRM entity (contact, account, deal).
        entity_id: UUID of the entity.
        actor_id: UUID of the user who triggered the activity, or None.
        type: Activity type (e.g. ``deal_stage_changed``).
        payload: Arbitrary metadata about the event.
        created_at: Timestamp of the activity.
    """

    model_config = {"from_attributes": True}

    id: UUID
    entity_type: str
    entity_id: UUID
    actor_id: Optional[UUID]
    type: str
    payload: dict[str, Any]
    created_at: datetime
