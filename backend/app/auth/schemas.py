from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    tenant_id: Optional[UUID] = None


class TokenPayload(BaseModel):
    sub: UUID
    tenant_id: UUID
    exp: int
    type: Literal["access", "refresh"]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    tenant_id: UUID
    is_active: bool
    created_at: datetime


class MessageResponse(BaseModel):
    message: str
