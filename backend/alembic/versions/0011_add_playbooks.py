"""Alembic migration 0011 — playbooks + playbook_runs tables (Feature #6 Playbooks IA).

Playbooks define automation sequences triggered by CRM events.
Each run is recorded for audit / history purposes.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playbooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("trigger_event", sa.String(64), nullable=False),
        # [{"field": "stage", "op": "eq", "value": "negotiation"}]
        sa.Column("trigger_conditions", JSONB, nullable=False, server_default="[]"),
        # [{"type": "add_note", "content": "..."}]
        sa.Column("actions", JSONB, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_playbooks_tenant_id", "playbooks", ["tenant_id"])
    # Partial index: used by the worker to find active playbooks per event quickly
    op.create_index(
        "ix_playbooks_tenant_event_active",
        "playbooks",
        ["tenant_id", "trigger_event"],
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "playbook_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "playbook_id",
            UUID(as_uuid=True),
            sa.ForeignKey("playbooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger_event", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=True),
        # pending | running | completed | failed
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_playbook_runs_tenant_id", "playbook_runs", ["tenant_id"])
    op.create_index("ix_playbook_runs_playbook_id", "playbook_runs", ["playbook_id"])
    op.create_index(
        "ix_playbook_runs_tenant_started",
        "playbook_runs",
        ["tenant_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("playbook_runs")
    op.drop_table("playbooks")
