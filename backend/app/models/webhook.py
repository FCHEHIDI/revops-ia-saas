"""SQLAlchemy models for webhook_endpoints and webhook_delivery_logs."""

import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.common.db import Base


class WebhookEndpoint(Base):
    """A tenant-scoped webhook subscription for a specific event type.

    The ``secret`` is stored in plaintext because we must compute HMAC-SHA256
    on delivery. It is 32 random bytes (64 hex chars) generated on creation and
    returned to the client once. Tenants should rotate via delete + re-create.
    """

    __tablename__ = "webhook_endpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(64), nullable=False)
    url = Column(Text, nullable=False)
    secret = Column(String(64), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    logs = relationship(
        "WebhookDeliveryLog",
        back_populates="endpoint",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class WebhookDeliveryLog(Base):
    """Delivery attempt record for a webhook event.

    Keeps a rolling history (purge via cron if needed). ``response_status``
    is None when delivery failed before reaching the target server.
    """

    __tablename__ = "webhook_delivery_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    response_status = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    delivered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    endpoint = relationship("WebhookEndpoint", back_populates="logs")
