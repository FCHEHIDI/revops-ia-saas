"""Align users and refresh_tokens tables with the canonical SQLAlchemy models.

The 0001 initial schema lagged behind the canonical models that the
auth/CRM/permissions layers actually use:

- ``users``:           missing ``full_name`` and ``is_active`` columns
                        (the auth service reads ``user.is_active`` and the
                        login UX displays ``user.full_name``).
- ``refresh_tokens``:  uses ``revoked_at DateTime`` while the model uses
                        ``is_revoked Boolean``.  We add the boolean column
                        and keep ``revoked_at`` for audit purposes.

This migration is additive only (no destructive ops) so it is safe to apply
on top of an existing dev/staging database.
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users -------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("full_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # refresh_tokens ----------------------------------------------------
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "is_revoked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Backfill from revoked_at if present
    op.execute(
        "UPDATE refresh_tokens SET is_revoked = TRUE WHERE revoked_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "is_revoked")
    op.drop_column("users", "is_active")
    op.drop_column("users", "full_name")
