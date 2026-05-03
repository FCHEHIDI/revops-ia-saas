"""SQLAlchemy model for the lead_scores table."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.common.db import Base


class LeadScore(Base):
    """Persists the result of an AI lead-scoring call for a contact."""

    __tablename__ = "lead_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), nullable=False)
    score = Column(SmallInteger, nullable=False)
    reasoning = Column(Text, nullable=False)
    recommended_action = Column(String(255), nullable=False)
    model_used = Column(String(100), nullable=False, default="heuristic")
    cache_key = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
