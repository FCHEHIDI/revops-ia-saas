"""Pydantic schemas for email delivery."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class EmailEnqueueRequest(BaseModel):
    """Payload sent by mcp-sequences (or any internal caller) to queue an email.

    Args:
        tenant_id: Tenant that owns the send.
        contact_id: CRM contact receiving the email.
        to_email: Recipient email address.
        subject: Email subject line.
        body_html: Fully-rendered HTML body.
        sequence_id: Optional originating sequence UUID.
        step_index: Optional step position within the sequence.
    """

    tenant_id: UUID
    contact_id: UUID
    to_email: EmailStr
    subject: str
    body_html: str
    sequence_id: Optional[UUID] = None
    step_index: Optional[int] = None


class EmailSendPublic(BaseModel):
    """Read-only view of an email send record.

    Args:
        id: Send UUID.
        contact_id: Target contact.
        to_email: Recipient address.
        subject: Subject line.
        status: pending | sent | failed.
        sent_at: When the email was delivered by Resend.
        opened_at: When the open pixel fired.
        clicked_at: When the click redirect fired.
        created_at: Row creation time.
    """

    model_config = {"from_attributes": True}

    id: UUID
    contact_id: UUID
    to_email: str
    subject: str
    status: str
    sent_at: Optional[datetime]
    opened_at: Optional[datetime]
    clicked_at: Optional[datetime]
    created_at: datetime
