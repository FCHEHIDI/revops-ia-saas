from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Available scopes — extend as new MCPs/features are added.
# ---------------------------------------------------------------------------
VALID_SCOPES = frozenset(
    {
        "crm:read",
        "crm:write",
        "billing:read",
        "analytics:read",
        "sequences:write",
        "documents:read",
    }
)


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None

    model_config = {"json_schema_extra": {"example": {"name": "CI pipeline", "scopes": ["crm:read", "analytics:read"]}}}


class ApiKeyResponse(BaseModel):
    """Returned after creation — includes the raw key once."""

    id: UUID
    name: str
    scopes: list[str]
    expires_at: Optional[datetime]
    created_at: datetime
    # The plaintext key is ONLY present on the initial create response.
    key: Optional[str] = None

    model_config = {"from_attributes": True}


class ApiKeyPublic(BaseModel):
    """Safe view — no secrets, used for list/get endpoints."""

    id: UUID
    name: str
    scopes: list[str]
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
