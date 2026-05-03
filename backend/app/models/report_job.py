"""SQLAlchemy model for report_jobs (Feature #7 PDF Reports)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.common.db import Base


class ReportJob(Base):
    """Represents an async PDF report generation job.

    Attributes:
        id: Primary key UUID.
        tenant_id: FK to organizations (cascade delete).
        report_type: One of pipeline | mrr | team_performance | churn.
        status: pending | generating_data | rendering | done | failed.
        parameters: Optional JSON parameters for the report.
        file_path: Marker path once PDF is stored (prefixed "memory:<job_id>").
        error: Error message if status is "failed".
        created_at: Creation timestamp.
        completed_at: Completion timestamp (done or failed).
    """

    __tablename__ = "report_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    parameters = Column(JSONB, nullable=True)
    file_path = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_report_jobs_tenant_status_model", "tenant_id", "status"),
    )
