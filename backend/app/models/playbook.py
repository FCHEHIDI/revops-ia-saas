"""SQLAlchemy models for playbooks and playbook_runs tables (Feature #6)."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.common.db import Base


class Playbook(Base):
    """Tenant-scoped automation playbook.

    A playbook fires when a matching CRM event is published (e.g. deal stage
    changed) and all ``trigger_conditions`` evaluate to True against the event
    payload.  Then every action in ``actions`` is executed in order.
    """

    __tablename__ = "playbooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # One of: deal.stage_changed | contact.created | deal.created | manual
    trigger_event = Column(String(64), nullable=False)
    # JSON array of condition dicts: [{"field": "stage", "op": "eq", "value": "negotiation"}]
    trigger_conditions = Column(JSONB, nullable=False, default=list)
    # JSON array of action dicts: [{"type": "add_note", "content": "..."}]
    actions = Column(JSONB, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PlaybookRun(Base):
    """Audit record for a single playbook execution.

    ``status`` transitions: pending → running → completed | failed.
    ``result`` holds per-action outcomes when status is completed.
    ``error`` holds the exception message when status is failed.
    """

    __tablename__ = "playbook_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    playbook_id = Column(
        UUID(as_uuid=True),
        ForeignKey("playbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_event = Column(String(64), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
