"""Add job_title column to users table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("job_title", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "job_title")
