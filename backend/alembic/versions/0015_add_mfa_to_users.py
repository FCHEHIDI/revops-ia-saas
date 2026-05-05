"""Alembic migration 0015 — add MFA support to users.

Adds a boolean MFA enabled flag and an optional TOTP secret to the
users table. These columns are used by the auth service to support
optional two-factor authentication.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("mfa_secret", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_secret")
    op.drop_column("users", "mfa_enabled")
