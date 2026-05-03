"""Alembic migration 0009 — email_sends table (sequence email delivery tracking)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_sends",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_id", UUID(as_uuid=True), nullable=True),
        sa.Column("contact_id", UUID(as_uuid=True), nullable=False),
        sa.Column("step_index", sa.Integer, nullable=True),
        sa.Column("to_email", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("body_html", sa.Text, nullable=False),
        # Unique tokens for open/click tracking (never exposed to sender)
        sa.Column(
            "open_token",
            UUID(as_uuid=True),
            nullable=False,
            unique=True,
            comment="1x1 pixel tracking token",
        ),
        sa.Column(
            "click_token",
            UUID(as_uuid=True),
            nullable=False,
            unique=True,
            comment="click redirect token",
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
            comment="pending | sent | failed",
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_email_sends_tenant_id", "email_sends", ["tenant_id"])
    op.create_index(
        "ix_email_sends_contact",
        "email_sends",
        ["tenant_id", "contact_id"],
    )
    op.create_index(
        "ix_email_sends_pending",
        "email_sends",
        ["status"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_email_sends_pending", "email_sends")
    op.drop_index("ix_email_sends_contact", "email_sends")
    op.drop_index("ix_email_sends_tenant_id", "email_sends")
    op.drop_table("email_sends")
