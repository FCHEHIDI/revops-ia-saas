"""SQLAlchemy model for the activities (entity timeline) table."""

import uuid
from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.common.db import Base


class Activity(Base):
    """One activity event in the timeline of a CRM entity.

    All writes go through ``app.activities.service.record``. Reads are scoped
    to a tenant + entity so RLS stays effective even without a row-level policy
    on this table (tenant_id is always in the WHERE clause).

    Supported ``type`` values:
        contact_created, deal_created, deal_stage_changed, note_added,
        sequence_enrolled, email_sent, email_opened, ai_chat_message,
        invoice_paid, invoice_overdue
    """

    __tablename__ = "activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    type = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
