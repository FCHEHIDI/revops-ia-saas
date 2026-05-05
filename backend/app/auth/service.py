import asyncio
import hashlib
import secrets
from datetime import timedelta
from typing import Optional, Tuple
from uuid import UUID, uuid4

import pyotp
from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth.validation import validate_password_format
from app.config import settings
from app.common.utils import utcnow
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.auth.schemas import TokenPayload

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Precomputed dummy hash used for constant-time response when the user does not
# exist — prevents email enumeration via timing attacks.
_DUMMY_HASH: str = pwd_context.hash("__dummy__")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


async def get_password_hash_async(password: str) -> str:
    """Non-blocking bcrypt hash — runs in a thread pool."""
    return await asyncio.to_thread(pwd_context.hash, password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Non-blocking bcrypt verify — runs in a thread pool."""
    return await asyncio.to_thread(pwd_context.verify, plain_password, hashed_password)


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def get_totp(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret, digits=6, interval=30)


def verify_mfa_code(secret: str, code: str) -> bool:
    try:
        return bool(get_totp(secret).verify(code, valid_window=1))
    except Exception:
        return False


def validate_password(password: str) -> None:
    validate_password_format(password)


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(user: User) -> str:
    expire = utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def create_refresh_token(db: AsyncSession, user: User) -> str:
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_refresh_token(raw_token)
    expire = utcnow() + timedelta(days=settings.refresh_token_expire_days)
    token_obj = RefreshToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expire,
        is_revoked=False,
    )
    db.add(token_obj)
    await db.commit()
    return raw_token


def verify_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenPayload(
            sub=UUID(payload["sub"]),
            tenant_id=UUID(payload["tenant_id"]),
            exp=payload["exp"],
            type=payload["type"],
        )
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )


async def refresh_tokens(db: AsyncSession, raw_refresh_token: str) -> Tuple[str, str]:
    token_hash = _hash_refresh_token(raw_refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.expires_at > utcnow(),
            RefreshToken.is_revoked.is_(False),
        )
    )
    token_obj = result.scalar_one_or_none()
    if not token_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    token_obj.is_revoked = True
    db.add(token_obj)

    user_result = await db.execute(select(User).where(User.id == token_obj.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    access_token = create_access_token(user)
    new_refresh_token = await create_refresh_token(db, user)
    await db.commit()
    return access_token, new_refresh_token


async def revoke_refresh_token(db: AsyncSession, raw_refresh_token: str) -> None:
    token_hash = _hash_refresh_token(raw_refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked.is_(False),
        )
    )
    token_obj = result.scalar_one_or_none()
    if token_obj:
        token_obj.is_revoked = True
        db.add(token_obj)
        await db.commit()


async def authenticate_user(
    db: AsyncSession, email: str, password: str, mfa_code: Optional[str] = None
) -> Optional[User]:
    # Exact email match first.
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Username-style fallback: if input has no "@" and no exact match, look up
    # the unique user whose email starts with "username@" (dev convenience).
    if user is None and "@" not in email:
        result = await db.execute(
            select(User).where(User.email.like(f"{email}@%"))
        )
        users = result.scalars().all()
        user = users[0] if len(users) == 1 else None

    # Always run bcrypt — even when the user does not exist — so response time
    # is constant and cannot be used to enumerate valid email addresses.
    hash_to_check = user.password_hash if (user and user.is_active) else _DUMMY_HASH
    password_ok = await verify_password_async(password, hash_to_check)

    if not user or not user.is_active or not password_ok:
        return None
    if user.mfa_enabled:
        if not user.mfa_secret or not mfa_code or not verify_mfa_code(user.mfa_secret, mfa_code):
            return None
    return user
