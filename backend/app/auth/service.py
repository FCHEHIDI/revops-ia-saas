import hashlib
import secrets
from datetime import timedelta
from typing import Optional, Tuple
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.common.utils import utcnow
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.auth.schemas import TokenPayload

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


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
    db: AsyncSession, email: str, password: str
) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user and user.is_active and verify_password(password, user.password_hash):
        return user
    return None
