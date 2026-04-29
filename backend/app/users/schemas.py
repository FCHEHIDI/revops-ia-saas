from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime


class UserResponse(BaseModel):
    id: UUID
    org_id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    avatar: Optional[str] = None
    roles: list[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UpdateProfileRequest(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    avatar: Optional[str] = None
