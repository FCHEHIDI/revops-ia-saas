from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from uuid import uuid4
from app.common.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
