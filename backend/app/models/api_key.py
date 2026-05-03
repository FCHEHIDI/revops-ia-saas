"""ApiKey model — programmatic access tokens for tenants.

Format : ``rk_live_<32 random url-safe chars>``
Storage : only the SHA-256 hex-digest is persisted, never the raw key.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.common.db import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The user who created this key (for audit, not for auth).
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(String(128), nullable=False)
    # SHA-256 hex-digest of the raw key — never the plaintext.
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    # Subset of available scopes this key is granted.
    scopes = Column(ARRAY(String), nullable=False, default=list, server_default="{}")
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
