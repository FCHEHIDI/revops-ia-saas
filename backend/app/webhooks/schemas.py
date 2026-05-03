"""Pydantic schemas for webhook endpoints and delivery logs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl, field_validator

# Supported event types
SUPPORTED_EVENTS: frozenset[str] = frozenset(
    {
        "deal.won",
        "deal.lost",
        "contact.created",
        "invoice.overdue",
        "sequence.completed",
    }
)


class WebhookEndpointCreate(BaseModel):
    """Request body for creating a new webhook subscription.

    Args:
        event_type: One of the supported RevOps events.
        url: HTTPS URL that will receive POST requests.

    Raises:
        ValueError: If event_type is not in SUPPORTED_EVENTS or url is not HTTPS.
    """

    event_type: str
    url: HttpUrl

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Validate that event_type is one of the supported events."""
        if v not in SUPPORTED_EVENTS:
            raise ValueError(
                f"Unsupported event_type '{v}'. "
                f"Valid values: {sorted(SUPPORTED_EVENTS)}"
            )
        return v

    @field_validator("url")
    @classmethod
    def validate_https(cls, v: HttpUrl) -> HttpUrl:
        """Enforce HTTPS for webhook targets to prevent credential leakage."""
        if v.scheme != "https":
            raise ValueError("Webhook URL must use HTTPS.")
        return v


class WebhookEndpointResponse(BaseModel):
    """Full representation of a webhook endpoint (returned on create).

    The ``secret`` field is returned ONLY on creation. Subsequent reads
    via the list endpoint use ``WebhookEndpointPublic`` which omits it.

    Args:
        id: UUID of the endpoint.
        event_type: Event type subscribed to.
        url: Target URL.
        secret: HMAC-SHA256 signing secret (hex, 64 chars). Shown once.
        active: Whether the endpoint is active.
        created_at: Creation timestamp.
    """

    model_config = {"from_attributes": True}

    id: UUID
    event_type: str
    url: str
    secret: str  # shown once on creation
    active: bool
    created_at: datetime


class WebhookEndpointPublic(BaseModel):
    """Webhook endpoint without the secret, for listing.

    Args:
        id: UUID of the endpoint.
        event_type: Event type subscribed to.
        url: Target URL.
        active: Whether the endpoint is active.
        created_at: Creation timestamp.
    """

    model_config = {"from_attributes": True}

    id: UUID
    event_type: str
    url: str
    active: bool
    created_at: datetime


class WebhookDeliveryLogPublic(BaseModel):
    """One delivery attempt for a webhook.

    Args:
        id: Log entry UUID.
        event_type: Event type delivered.
        response_status: HTTP status returned by the target, or None on network error.
        error: Error message if delivery failed, else None.
        delivered_at: Timestamp of the attempt.
    """

    model_config = {"from_attributes": True}

    id: UUID
    event_type: str
    response_status: Optional[int]
    error: Optional[str]
    delivered_at: datetime
