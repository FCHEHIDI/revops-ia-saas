"""Alembic migration 0013 — usage_events table (Feature #8 Usage Metering).

Records token consumption and MCP tool calls per tenant for billing and abuse
detection. Each row is an atomic usage unit: event_type + quantity + metadata.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Event types: llm_tokens_input | llm_tokens_output | mcp_calls |
        #              emails_sent | documents_indexed
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("quantity", sa.BigInteger, nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Query pattern: WHERE tenant_id = ? AND ts >= ? AND ts < ? → composite index
    op.create_index(
        "ix_usage_events_tenant_ts", "usage_events", ["tenant_id", "ts"]
    )
    op.create_index(
        "ix_usage_events_tenant_type", "usage_events", ["tenant_id", "event_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_usage_events_tenant_type", table_name="usage_events")
    op.drop_index("ix_usage_events_tenant_ts", table_name="usage_events")
    op.drop_table("usage_events")
