"""Alembic migration 0012 — report_jobs table (Feature #7 PDF Reports).

Stores async report generation jobs with status tracking and optional file path.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("parameters", JSONB, nullable=True),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_report_jobs_tenant", "report_jobs", ["tenant_id"])
    op.create_index(
        "ix_report_jobs_tenant_status", "report_jobs", ["tenant_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_report_jobs_tenant_status", table_name="report_jobs")
    op.drop_index("ix_report_jobs_tenant", table_name="report_jobs")
    op.drop_table("report_jobs")
