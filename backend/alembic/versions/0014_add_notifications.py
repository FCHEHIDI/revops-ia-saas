"""Alembic migration 0014 — notifications table (Feature #9 Notification Center).

Stores persistent, per-tenant (optionally per-user) notifications with a
read_at timestamp.  A NULL read_at means the notification is unread.

Query patterns:
  - WHERE tenant_id = ? ORDER BY created_at DESC   → ix_notifications_tenant_created
  - WHERE user_id = ? AND read_at IS NULL           → partial index ix_notifications_user_unread
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        # Notification category (see NOTIFICATION_TYPES in schemas.py)
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        # Arbitrary JSON context (deal_id, playbook_id, run_id, etc.)
        sa.Column("data", JSONB, nullable=True),
        # NULL = unread; set to now() on first read
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Main query: per-tenant listing newest-first
    op.create_index(
        "ix_notifications_tenant_created",
        "notifications",
        ["tenant_id", "created_at"],
    )
    # Unread badge: count unread per user
    op.create_index(
        "ix_notifications_user_id",
        "notifications",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_tenant_created", table_name="notifications")
    op.drop_table("notifications")
