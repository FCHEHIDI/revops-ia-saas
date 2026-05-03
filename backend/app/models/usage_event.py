"""SQLAlchemy model for usage_events (Feature #8 Usage Metering)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.common.db import Base


class UsageEvent(Base):
    """Represents a single metered usage unit for a tenant.

    Attributes:
        id: Primary key UUID.
        tenant_id: FK to organizations (cascade delete).
        event_type: Category of usage. One of:
            - ``llm_tokens_input``   — prompt tokens consumed
            - ``llm_tokens_output``  — completion tokens generated
            - ``mcp_calls``          — MCP tool invocations
            - ``emails_sent``        — outbound emails via sequences
            - ``documents_indexed``  — RAG document chunks indexed
        quantity: Unsigned integer count for the event.
        metadata: Optional JSONB bag for contextual data
            (e.g. ``{"model": "gpt-4o", "session_id": "...", "tool": "..."``).
        ts: Timestamp of the event (defaults to ``now()`` at DB level).
    """

    __tablename__ = "usage_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(64), nullable=False)
    quantity = Column(BigInteger, nullable=False)
    # "metadata" is reserved by SQLAlchemy Base — mapped to DB column "metadata"
    event_metadata = Column("metadata", JSONB, nullable=True)
    ts = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_usage_events_tenant_ts", "tenant_id", "ts"),
        Index("ix_usage_events_tenant_type", "tenant_id", "event_type"),
    )
