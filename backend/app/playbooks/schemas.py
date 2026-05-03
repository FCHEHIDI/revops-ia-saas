"""Pydantic schemas for playbooks CRUD and run history."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Allowed values
# ---------------------------------------------------------------------------

TRIGGER_EVENTS: frozenset[str] = frozenset(
    {"deal.stage_changed", "contact.created", "deal.created", "manual"}
)

ACTION_TYPES: frozenset[str] = frozenset(
    {"add_note", "update_deal_stage", "score_lead", "send_notification"}
)

CONDITION_OPS: frozenset[str] = frozenset({"eq", "ne", "gte", "lte", "in", "contains"})


# ---------------------------------------------------------------------------
# Condition / Action inline validators
# ---------------------------------------------------------------------------


def _validate_conditions(conditions: list[dict]) -> list[dict]:
    """Validate the structure of trigger_conditions.

    Args:
        conditions: List of condition dicts.

    Returns:
        The validated list unchanged.

    Raises:
        ValueError: If any condition is malformed.
    """
    for i, cond in enumerate(conditions):
        if not isinstance(cond, dict):
            raise ValueError(f"conditions[{i}] must be a dict")
        if "field" not in cond or "op" not in cond or "value" not in cond:
            raise ValueError(f"conditions[{i}] must have 'field', 'op', 'value'")
        if cond["op"] not in CONDITION_OPS:
            raise ValueError(
                f"conditions[{i}].op '{cond['op']}' not in {sorted(CONDITION_OPS)}"
            )
    return conditions


def _validate_actions(actions: list[dict]) -> list[dict]:
    """Validate the structure of playbook actions.

    Args:
        actions: List of action dicts.

    Returns:
        The validated list unchanged.

    Raises:
        ValueError: If any action is malformed.
    """
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"actions[{i}] must be a dict")
        if "type" not in action:
            raise ValueError(f"actions[{i}] missing 'type'")
        if action["type"] not in ACTION_TYPES:
            raise ValueError(
                f"actions[{i}].type '{action['type']}' not in {sorted(ACTION_TYPES)}"
            )
    return actions


# ---------------------------------------------------------------------------
# Playbook CRUD schemas
# ---------------------------------------------------------------------------


class PlaybookCreate(BaseModel):
    """Request body for creating a playbook."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    trigger_event: str
    trigger_conditions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def _validate(self) -> "PlaybookCreate":
        if self.trigger_event not in TRIGGER_EVENTS:
            raise ValueError(
                f"trigger_event '{self.trigger_event}' not in {sorted(TRIGGER_EVENTS)}"
            )
        _validate_conditions(self.trigger_conditions)
        _validate_actions(self.actions)
        return self


class PlaybookUpdate(BaseModel):
    """Request body for partial update of a playbook."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    trigger_event: str | None = None
    trigger_conditions: list[dict[str, Any]] | None = None
    actions: list[dict[str, Any]] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> "PlaybookUpdate":
        if self.trigger_event is not None and self.trigger_event not in TRIGGER_EVENTS:
            raise ValueError(
                f"trigger_event '{self.trigger_event}' not in {sorted(TRIGGER_EVENTS)}"
            )
        if self.trigger_conditions is not None:
            _validate_conditions(self.trigger_conditions)
        if self.actions is not None:
            _validate_actions(self.actions)
        return self


class PlaybookRead(BaseModel):
    """Response schema for a playbook."""

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    trigger_event: str
    trigger_conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Playbook run schemas
# ---------------------------------------------------------------------------


class PlaybookRunRead(BaseModel):
    """Response schema for a playbook run record."""

    id: UUID
    tenant_id: UUID
    playbook_id: UUID
    trigger_event: str
    entity_type: str | None
    entity_id: UUID | None
    status: str
    result: dict[str, Any] | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Trigger request schemas
# ---------------------------------------------------------------------------


class TriggerRequest(BaseModel):
    """Body for manually triggering a playbook (public endpoint)."""

    entity_type: str | None = None
    entity_id: UUID | None = None
    event_payload: dict[str, Any] = Field(default_factory=dict)


class InternalTriggerRequest(BaseModel):
    """Body for the internal mcp-crm trigger endpoint."""

    playbook_id: UUID
    entity_type: str | None = None
    entity_id: UUID | None = None
    event_payload: dict[str, Any] = Field(default_factory=dict)
