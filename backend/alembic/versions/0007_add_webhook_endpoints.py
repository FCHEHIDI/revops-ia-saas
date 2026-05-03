"""Alembic migration 0007 — webhook_endpoints + webhook_delivery_logs tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        # HMAC secret stored in plaintext — tenants receive it once on creation.
        # Hashing is not useful here: we need the secret to compute HMAC on delivery.
        sa.Column("secret", sa.String(64), nullable=False),
        sa.Column(
            "active",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_webhook_endpoints_tenant_id", "webhook_endpoints", ["tenant_id"])
    op.create_index(
        "ix_webhook_endpoints_tenant_event",
        "webhook_endpoints",
        ["tenant_id", "event_type"],
    )

    op.create_table(
        "webhook_delivery_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "endpoint_id",
            UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_webhook_delivery_logs_endpoint_id",
        "webhook_delivery_logs",
        ["endpoint_id"],
    )
    op.create_index(
        "ix_webhook_delivery_logs_tenant_id",
        "webhook_delivery_logs",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_delivery_logs_tenant_id", table_name="webhook_delivery_logs")
    op.drop_index("ix_webhook_delivery_logs_endpoint_id", table_name="webhook_delivery_logs")
    op.drop_table("webhook_delivery_logs")
    op.drop_index("ix_webhook_endpoints_tenant_event", table_name="webhook_endpoints")
    op.drop_index("ix_webhook_endpoints_tenant_id", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
