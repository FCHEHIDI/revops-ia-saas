from sqlalchemy import (
    Column, String, Numeric, DateTime, ForeignKey, Text, Index, SmallInteger, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, DATE
from sqlalchemy.sql import func
from uuid import uuid4
from app.common.db import Base

class Account(Base):
    __tablename__ = "accounts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=True)
    industry = Column(String(100), nullable=True)
    size = Column(String(50), nullable=True)
    arr = Column(Numeric(14, 2), nullable=True)
    status = Column(String(50), nullable=False, default="active")
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    __table_args__ = (
        Index("ix_accounts_org_name", "org_id", "name"),
    )

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    job_title = Column(String(150), nullable=True)
    status = Column(String(50), nullable=False, default="active")
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_contacts_org_email"),
    )

class Deal(Base):
    __tablename__ = "deals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    title = Column(String(255), nullable=False)
    stage = Column(String(50), nullable=False)
    amount = Column(Numeric(14, 2), nullable=True)
    currency = Column(String(3), nullable=False, default="EUR")
    close_date = Column(DATE, nullable=True)
    probability = Column(SmallInteger, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    __table_args__ = (
        Index("ix_deals_org_stage", "org_id", "stage"),
        Index("ix_deals_org_owner", "org_id", "owner_id"),
    )
