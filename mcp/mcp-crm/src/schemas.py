from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ContactStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    prospect = "prospect"
    customer = "customer"
    churned = "churned"


class DealStage(str, Enum):
    prospecting = "prospecting"
    qualification = "qualification"
    proposal = "proposal"
    negotiation = "negotiation"
    closed_won = "closed_won"
    closed_lost = "closed_lost"


DEAL_STAGE_VALUES: set[str] = {s.value for s in DealStage}
CONTACT_STATUS_VALUES: set[str] = {s.value for s in ContactStatus}


# ---------------------------------------------------------------------------
# Contact DTOs
# ---------------------------------------------------------------------------


class ContactRead(BaseModel):
    id: UUID
    org_id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None
    job_title: str | None = None
    account_id: UUID | None = None
    status: ContactStatus = ContactStatus.active
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=200)
    account_id: UUID | None = None
    status: ContactStatus = ContactStatus.active
    created_by: UUID


class ContactUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=200)
    account_id: UUID | None = None
    status: ContactStatus | None = None


class ContactListResponse(BaseModel):
    contacts: list[ContactRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Account DTOs
# ---------------------------------------------------------------------------


class AccountRead(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    domain: str | None = None
    industry: str | None = None
    size: str | None = None
    arr: str | None = None
    status: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    domain: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=50)
    created_by: UUID


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    domain: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=50)
    arr: str | None = None
    status: str | None = None


class AccountListResponse(BaseModel):
    accounts: list[AccountRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Deal DTOs
# ---------------------------------------------------------------------------


class DealRead(BaseModel):
    id: UUID
    org_id: UUID
    account_id: UUID
    contact_id: UUID | None = None
    owner_id: UUID
    title: str
    stage: DealStage
    amount: str | None = None
    currency: str = "USD"
    close_date: date | None = None
    probability: float | None = None
    notes: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DealCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    account_id: UUID
    stage: DealStage
    owner_id: UUID
    amount: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    close_date: date | None = None
    contact_id: UUID | None = None
    notes: str | None = None
    created_by: UUID


class DealStageUpdate(BaseModel):
    stage: DealStage
    notes: str | None = None


class DealListResponse(BaseModel):
    deals: list[DealRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Tool schema definitions — used by GET /tools endpoint
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_contact",
        "description": "Retrieve a single CRM contact by ID for the authenticated tenant.",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id", "contact_id"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "contact_id": {"type": "string", "format": "uuid"},
            },
        },
    },
    {
        "name": "search_contacts",
        "description": "Search and list CRM contacts with optional filters (name, email, status, account).",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "query": {"type": "string"},
                "account_id": {"type": "string", "format": "uuid"},
                "status": {"type": "string", "enum": list(CONTACT_STATUS_VALUES)},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "page_size": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "create_contact",
        "description": "Create a new CRM contact for the authenticated tenant.",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id", "first_name", "last_name", "email", "created_by"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "phone": {"type": "string"},
                "job_title": {"type": "string"},
                "account_id": {"type": "string", "format": "uuid"},
                "created_by": {"type": "string", "format": "uuid"},
            },
        },
    },
    {
        "name": "update_contact",
        "description": "Partially update an existing CRM contact (PATCH semantics).",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id", "contact_id"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "contact_id": {"type": "string", "format": "uuid"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "phone": {"type": "string"},
                "job_title": {"type": "string"},
                "account_id": {"type": "string", "format": "uuid"},
                "status": {"type": "string", "enum": list(CONTACT_STATUS_VALUES)},
            },
        },
    },
    {
        "name": "get_account",
        "description": "Retrieve a single CRM account by ID for the authenticated tenant.",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id", "account_id"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "account_id": {"type": "string", "format": "uuid"},
            },
        },
    },
    {
        "name": "search_accounts",
        "description": "Search and list CRM accounts with optional filters (name, domain, industry).",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "query": {"type": "string"},
                "industry": {"type": "string"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "page_size": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "create_account",
        "description": "Create a new CRM account (company) for the authenticated tenant.",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id", "name", "created_by"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "domain": {"type": "string"},
                "industry": {"type": "string"},
                "size": {"type": "string"},
                "created_by": {"type": "string", "format": "uuid"},
            },
        },
    },
    {
        "name": "update_account",
        "description": "Partially update an existing CRM account (PATCH semantics).",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id", "account_id"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "account_id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "domain": {"type": "string"},
                "industry": {"type": "string"},
                "size": {"type": "string"},
                "arr": {"type": "string"},
                "status": {"type": "string"},
            },
        },
    },
    {
        "name": "get_deal",
        "description": "Retrieve a single CRM deal by ID for the authenticated tenant.",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id", "deal_id"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "deal_id": {"type": "string", "format": "uuid"},
            },
        },
    },
    {
        "name": "list_deals",
        "description": "List CRM deals with optional filters (stage, owner, account). Supports pagination.",
        "input_schema": {
            "type": "object",
            "required": ["tenant_id"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "stage": {"type": "string", "enum": list(DEAL_STAGE_VALUES)},
                "owner_id": {"type": "string", "format": "uuid"},
                "account_id": {"type": "string", "format": "uuid"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "page_size": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "create_deal",
        "description": "Create a new deal in the sales pipeline for the authenticated tenant.",
        "input_schema": {
            "type": "object",
            "required": [
                "tenant_id",
                "title",
                "account_id",
                "stage",
                "owner_id",
                "created_by",
            ],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "title": {"type": "string"},
                "account_id": {"type": "string", "format": "uuid"},
                "stage": {"type": "string", "enum": list(DEAL_STAGE_VALUES)},
                "owner_id": {"type": "string", "format": "uuid"},
                "amount": {
                    "type": "string",
                    "description": "Decimal amount as string, e.g. '15000.00'",
                },
                "currency": {
                    "type": "string",
                    "minLength": 3,
                    "maxLength": 3,
                    "default": "USD",
                },
                "close_date": {"type": "string", "format": "date"},
                "contact_id": {"type": "string", "format": "uuid"},
                "notes": {"type": "string"},
                "created_by": {"type": "string", "format": "uuid"},
            },
        },
    },
    {
        "name": "update_deal_stage",
        "description": (
            "Transition a deal to a new pipeline stage. "
            "Stage transitions are validated server-side. "
            "Optionally attaches notes (triggers RAG indexing on backend)."
        ),
        "input_schema": {
            "type": "object",
            "required": ["tenant_id", "deal_id", "new_stage"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "deal_id": {"type": "string", "format": "uuid"},
                "new_stage": {"type": "string", "enum": list(DEAL_STAGE_VALUES)},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "name": "score_lead",
        "description": (
            "Score a CRM contact using AI (LLM or heuristic fallback). "
            "Returns a 0-100 quality score, reasoning, and recommended next action. "
            "Results are cached in Redis for 24 hours."
        ),
        "input_schema": {
            "type": "object",
            "required": ["tenant_id", "contact_id"],
            "properties": {
                "tenant_id": {"type": "string", "format": "uuid"},
                "contact_id": {"type": "string", "format": "uuid"},
                "force_refresh": {
                    "type": "boolean",
                    "default": False,
                    "description": "Bypass cache and re-score even if a cached value exists.",
                },
            },
        },
    },
]
