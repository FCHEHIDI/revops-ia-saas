"""SQLAlchemy model for notifications (Feature #9 Notification Center)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Column, DateTime, ForeignKey, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.common.db import Base


class Notification(Base):
    """Persistent notification row, scoped to a tenant (optionally to a user).

    Attributes:
        id: Primary key.
        tenant_id: Owning tenant (cascade-delete on org removal).
        user_id: Optional target user.  NULL means tenant-wide.
        type: Notification category string (e.g. "playbook_triggered").
        title: Short human-readable title (max 255 chars).
        body: Optional longer description.
        data: Arbitrary JSON context (deal_id, run_id, …).
        read_at: Timestamp of first read; NULL means unread.
        created_at: Row creation timestamp (server default).
    """

    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    type = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    # "data" is safe as an ORM attribute name (unlike "metadata" which is
    # reserved by SQLAlchemy Base for the MetaData object).
    data = Column(JSONB, nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
