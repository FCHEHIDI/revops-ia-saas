"""Pydantic schemas for usage metering (Feature #8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Supported event types
# ---------------------------------------------------------------------------

USAGE_EVENT_TYPES = frozenset(
    {
        "llm_tokens_input",
        "llm_tokens_output",
        "mcp_calls",
        "emails_sent",
        "documents_indexed",
    }
)

UsageEventType = Literal[
    "llm_tokens_input",
    "llm_tokens_output",
    "mcp_calls",
    "emails_sent",
    "documents_indexed",
]

# ---------------------------------------------------------------------------
# Supported period values
# ---------------------------------------------------------------------------

UsagePeriod = Literal[
    "current_month",
    "last_month",
    "last_7_days",
    "last_30_days",
]

# ---------------------------------------------------------------------------
# Write schema (internal — not exposed via HTTP)
# ---------------------------------------------------------------------------


class UsageEventCreate(BaseModel):
    """Internal DTO used by services to record a usage event.

    Args:
        tenant_id: UUID of the tenant.
        event_type: Category of the usage metric.
        quantity: Number of units consumed (tokens, calls, etc.).
        metadata: Optional contextual data (model name, tool name, etc.).
    """

    tenant_id: UUID
    event_type: UsageEventType
    quantity: int = Field(..., ge=1)
    metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Read schemas
# ---------------------------------------------------------------------------


class UsageEventRead(BaseModel):
    """Serialized usage event row returned by the API.

    Args:
        id: Row UUID.
        tenant_id: Owning tenant.
        event_type: Category of the metric.
        quantity: Units consumed.
        metadata: Optional context bag (mapped from ORM field ``event_metadata``).
        ts: Timestamp of the event.
    """

    id: UUID
    tenant_id: UUID
    event_type: str
    quantity: int
    metadata: Optional[Dict[str, Any]] = Field(None, alias=None)
    ts: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):  # type: ignore[override]
        """Map ORM ``event_metadata`` attribute to Pydantic ``metadata`` field."""
        if hasattr(obj, "event_metadata"):
            data = {
                "id": obj.id,
                "tenant_id": obj.tenant_id,
                "event_type": obj.event_type,
                "quantity": obj.quantity,
                "metadata": obj.event_metadata,
                "ts": obj.ts,
            }
            return cls(**data)
        return super().model_validate(obj, **kwargs)


class UsageSummaryItem(BaseModel):
    """Aggregate total for a single event_type within a period.

    Args:
        event_type: The metric category.
        total: Sum of all quantity values for the period.
    """

    event_type: str
    total: int


class UsageSummaryResponse(BaseModel):
    """Response body for GET /billing/usage.

    Args:
        period: The requested period label.
        start: Period start (inclusive, UTC).
        end: Period end (exclusive, UTC).
        items: Per-event-type aggregated totals.
    """

    period: str
    start: datetime
    end: datetime
    items: list[UsageSummaryItem]
