"""Schemas for the AI lead scoring endpoint."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ScoreLeadRequest(BaseModel):
    """Request body for POST /internal/v1/scoring/score-lead.

    Args:
        tenant_id: Tenant UUID (also validated via X-Tenant-ID header).
        contact_id: UUID of the contact to score.
        force_refresh: Skip Redis cache and re-score even if a cached value exists.
    """

    tenant_id: UUID
    contact_id: UUID
    force_refresh: bool = False


class ScoreLeadResponse(BaseModel):
    """Response from the scoring endpoint.

    Args:
        contact_id: UUID of the scored contact.
        score: Lead quality score 0-100.
        reasoning: 1-2 sentence explanation of the score.
        recommended_action: Short action string (e.g. "Schedule demo").
        model_used: LLM model name or "heuristic".
        cached: Whether the result was served from Redis cache.
        created_at: Timestamp of when this score was persisted.
    """

    contact_id: UUID
    score: int = Field(..., ge=0, le=100)
    reasoning: str
    recommended_action: str
    model_used: str
    cached: bool
    created_at: datetime

    model_config = {"from_attributes": True}
