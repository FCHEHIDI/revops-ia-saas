from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Literal
from uuid import UUID
from datetime import datetime, date

DealStage = Literal[
    "prospecting", "qualification", "proposal", "negotiation", "closing", "won", "lost"
]

class AccountBase(BaseModel):
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    arr: Optional[float] = None
    status: Optional[str] = "active"

class AccountCreate(AccountBase):
    pass

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    arr: Optional[float] = None
    status: Optional[str] = None

class AccountRead(AccountBase):
    id: UUID
    org_id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class ContactBase(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    job_title: Optional[str] = None
    status: Optional[str] = "active"
    account_id: Optional[UUID] = None

class ContactCreate(ContactBase):
    pass

class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    status: Optional[str] = None
    account_id: Optional[UUID] = None

class ContactRead(ContactBase):
    id: UUID
    org_id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class DealBase(BaseModel):
    account_id: UUID
    contact_id: Optional[UUID] = None
    owner_id: Optional[UUID] = None
    title: str
    stage: DealStage
    amount: Optional[float] = None
    currency: Optional[str] = "EUR"
    close_date: Optional[date] = None
    probability: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = "active"

class DealCreate(DealBase):
    pass

class DealUpdate(BaseModel):
    account_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    owner_id: Optional[UUID] = None
    title: Optional[str] = None
    stage: Optional[DealStage] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    close_date: Optional[date] = None
    probability: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = None

class DealStageUpdate(BaseModel):
    new_stage: DealStage
    notes: Optional[str] = None

class DealRead(DealBase):
    id: UUID
    org_id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class PaginatedAccounts(BaseModel):
    items: List[AccountRead]
    page: int
    limit: int
    total: int

class PaginatedContacts(BaseModel):
    items: List[ContactRead]
    page: int
    limit: int
    total: int

class PaginatedDeals(BaseModel):
    items: List[DealRead]
    page: int
    limit: int
    total: int
