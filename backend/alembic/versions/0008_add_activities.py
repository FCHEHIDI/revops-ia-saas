"""Alembic migration 0008 — activities table (entity activity timeline)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "entity_type",
            sa.String(64),
            nullable=False,
            comment="contact | account | deal",
        ),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=True, comment="user who triggered the activity"),
        sa.Column(
            "type",
            sa.String(64),
            nullable=False,
            comment=(
                "email_sent | email_opened | deal_created | deal_stage_changed | "
                "note_added | sequence_enrolled | ai_chat_message | "
                "invoice_paid | invoice_overdue | contact_created"
            ),
        ),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_activities_tenant_id", "activities", ["tenant_id"])
    op.create_index(
        "ix_activities_entity",
        "activities",
        ["tenant_id", "entity_type", "entity_id"],
    )
    op.create_index(
        "ix_activities_created_at",
        "activities",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_activities_created_at", table_name="activities")
    op.drop_index("ix_activities_entity", table_name="activities")
    op.drop_index("ix_activities_tenant_id", table_name="activities")
    op.drop_table("activities")
