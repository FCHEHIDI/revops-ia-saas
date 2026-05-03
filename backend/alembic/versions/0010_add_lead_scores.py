"""Alembic migration 0010 — lead_scores table (AI lead scoring Feature #3)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "score",
            sa.SmallInteger,
            nullable=False,
            comment="0-100 lead quality score",
        ),
        sa.Column("reasoning", sa.Text, nullable=False),
        sa.Column(
            "recommended_action",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "model_used",
            sa.String(100),
            nullable=False,
            server_default="heuristic",
        ),
        sa.Column(
            "cache_key",
            sa.String(255),
            nullable=True,
            comment="Redis cache key used for this score",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_lead_scores_tenant_id", "lead_scores", ["tenant_id"])
    op.create_index(
        "ix_lead_scores_contact",
        "lead_scores",
        ["tenant_id", "contact_id"],
    )
    # Latest score per contact (most queries use this)
    op.create_index(
        "ix_lead_scores_contact_created",
        "lead_scores",
        ["tenant_id", "contact_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_scores_contact_created", "lead_scores")
    op.drop_index("ix_lead_scores_contact", "lead_scores")
    op.drop_index("ix_lead_scores_tenant_id", "lead_scores")
    op.drop_table("lead_scores")
