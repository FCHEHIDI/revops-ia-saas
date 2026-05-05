from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.auth.validation import validate_password_format, validate_mfa_code


class LoginRequest(BaseModel):
    # Accept any string — valid-email enforcement happens at registration time.
    # Allows CLI / test logins with non-RFC-5321 identifiers during development.
    email: str
    password: str
    mfa_code: Optional[str] = None

    @field_validator("mfa_code")
    def validate_mfa_code_format(cls, value: Optional[str]) -> Optional[str]:
        return validate_mfa_code(value)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: Optional[str] = None
    tenant_id: Optional[UUID] = None

    @field_validator("password")
    def validate_password_format(cls, value: str) -> str:
        validate_password_format(value)
        return value


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
    roles: list[str]
    permissions: list[str]
    mfa_enabled: bool


class MFASetupResponse(BaseModel):
    otpauth_uri: str
    secret: str


class EnableMFARequest(BaseModel):
    code: str

    @field_validator("code")
    def validate_code(cls, value: str) -> str:
        if not validate_mfa_code(value):
            raise ValueError("MFA code must be exactly 6 digits")
        return value


class DisableMFARequest(BaseModel):
    password: str
    code: str

    @field_validator("code")
    def validate_code(cls, value: str) -> str:
        if not validate_mfa_code(value):
            raise ValueError("MFA code must be exactly 6 digits")
        return value


class MessageResponse(BaseModel):
    message: str
