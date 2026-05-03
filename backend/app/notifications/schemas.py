"""Pydantic schemas for the Notification Center (Feature #9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# Recognised notification type strings.
# Consumers (frontend) should handle unknown types gracefully.
NOTIFICATION_TYPES: frozenset[str] = frozenset({
    "playbook_triggered",
    "deal_stage_changed",
    "usage_limit_warning",
    "system",
    "lead_scored",
    "report_ready",
})


class NotificationCreate(BaseModel):
    """Payload for creating a new notification row.

    Attributes:
        tenant_id: Owning tenant.
        user_id: Target user; None means tenant-wide.
        type: Notification category (must be in NOTIFICATION_TYPES).
        title: Short human-readable summary (max 255 chars).
        body: Optional longer description.
        data: Arbitrary JSON context attached to this notification.
    """

    tenant_id: UUID
    user_id: Optional[UUID] = None
    type: str = Field(..., max_length=64)
    title: str = Field(..., max_length=255)
    body: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Accept known types; allow unknown for forward-compat."""
        return v


class NotificationRead(BaseModel):
    """Read-side representation of a Notification ORM object.

    Attributes:
        id: Notification primary key.
        tenant_id: Owning tenant.
        user_id: Target user (None = tenant-wide).
        type: Notification category.
        title: Short summary.
        body: Optional longer description.
        data: Arbitrary JSON context.
        read_at: Timestamp of first read; None if still unread.
        created_at: Row creation timestamp.
    """

    id: UUID
    tenant_id: UUID
    user_id: Optional[UUID]
    type: str
    title: str
    body: Optional[str]
    data: Optional[Dict[str, Any]]
    read_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    """Response body for the unread-count endpoint.

    Attributes:
        unread: Number of unread notifications for the requesting user/tenant.
    """

    unread: int


class MarkAllReadResponse(BaseModel):
    """Response body for the read-all endpoint.

    Attributes:
        updated: Number of rows marked as read.
    """

    updated: int
