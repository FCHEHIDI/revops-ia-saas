"""SQLAlchemy model for the email_sends table (sequence email delivery)."""

import uuid
from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.common.db import Base


class EmailSend(Base):
    """One outbound email dispatched by the sequence worker.

    Lifecycle: ``pending`` → ``sent`` (or ``failed``).
    Open / click tracking is done by the backend via unique UUID tokens.

    Columns:
        open_token: embedded as 1x1 pixel URL in the HTML body.
        click_token: used for click-redirect URLs (future link wrapping).
    """

    __tablename__ = "email_sends"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    sequence_id = Column(UUID(as_uuid=True), nullable=True)
    contact_id = Column(UUID(as_uuid=True), nullable=False)
    step_index = Column(Integer, nullable=True)
    to_email = Column(Text, nullable=False)
    subject = Column(Text, nullable=False)
    body_html = Column(Text, nullable=False)
    open_token = Column(UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4)
    click_token = Column(UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4)
    status = Column(String(32), nullable=False, server_default="pending")
    sent_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    clicked_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_email_sends_tenant_id", "tenant_id"),
        Index("ix_email_sends_contact", "tenant_id", "contact_id"),
    )
