"""Canonical User model.

Unifies the two legacy variants that previously lived in
`app/models/user.py` (auth-flavored: tenant_id + is_active + full_name) and
`app/users/models.py` (rbac-flavored: org_id + roles + permissions).

Single source of truth shared by:
- auth/service.py (JWT signing, password verification, refresh tokens)
- users/service.py (profile read/update)
- crm/permissions.py (RBAC enforcement on /internal/v1/crm/*)
- conftest.py (test fixtures)
"""

from __future__ import annotations

import uuid

from sqlalchemy import ARRAY, Boolean, Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.common.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    roles = Column(ARRAY(String), nullable=False, server_default="{}", default=list)
    permissions = Column(
        ARRAY(String), nullable=False, server_default="{}", default=list
    )
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @property
    def tenant_id(self) -> uuid.UUID:
        """Backward-compat alias used by JWT payload and middleware.

        The JWT contract exposes `tenant_id` to clients but internally we
        store the value as `org_id` (ADR-008 naming).
        """
        return self.org_id  # type: ignore[return-value]
