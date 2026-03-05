from app.users.models import User, RefreshToken
from app.common.security import verify_password, hash_password, create_access_token, create_refresh_token
from app.common.utils import utcnow
from app.config import settings
from app.auth.schemas import TokenResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import timedelta
from fastapi import HTTPException, status
from uuid import uuid4

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    q = await db.execute(select(User).where(User.email == email))
    user = q.scalar_one_or_none()
    if user and verify_password(password, user.password_hash):
        return user
    return None

async def create_tokens(db: AsyncSession, user: User) -> TokenResponse:
    access_token = create_access_token(
        data={"sub": str(user.id), "org_id": str(user.org_id), "permissions": user.permissions},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    refresh_token = create_refresh_token()
    expires_at = utcnow() + timedelta(days=settings.refresh_token_expire_days)
    refresh_token_obj = RefreshToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=hash_password(refresh_token),
        expires_at=expires_at
    )
    db.add(refresh_token_obj)
    await db.commit()
    await db.refresh(refresh_token_obj)
    return TokenResponse(access_token=access_token, expires_in=settings.access_token_expire_minutes * 60, refresh_token=refresh_token)

async def refresh_access_token(db: AsyncSession, refresh_token: str) -> TokenResponse:
    q = await db.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
    tokens = q.scalars().all()
    valid = None
    for tok in tokens:
        if verify_password(refresh_token, tok.token_hash):
            valid = tok
            break
    if not valid or valid.expires_at < utcnow():
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    await revoke_refresh_token(db, refresh_token)
    q_user = await db.execute(select(User).where(User.id == valid.user_id))
    user = q_user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return await create_tokens(db, user)

async def revoke_refresh_token(db: AsyncSession, refresh_token: str):
    q = await db.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
    tokens = q.scalars().all()
    for tok in tokens:
        if verify_password(refresh_token, tok.token_hash):
            tok.revoked_at = utcnow()
            db.add(tok)
    await db.commit()
