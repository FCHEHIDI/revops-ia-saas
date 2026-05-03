from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth.service import verify_access_token
from app.common.db import get_db
from app.models.user import User
from app.models.api_key import ApiKey

_API_KEY_PREFIX = "rk_live_"


async def _resolve_api_key(raw_key: str, db: AsyncSession) -> User:
    """Validate a raw API key and return a synthetic User-like object.

    Imports api_keys.service lazily to avoid circular imports.
    """
    from app.api_keys.service import lookup_key, touch_last_used, check_rate_limit

    if not await check_rate_limit(raw_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="API key rate limit exceeded (60 req/min)",
        )
    key_obj = await lookup_key(db, raw_key)
    if key_obj is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )
    # Fire-and-forget last_used update.
    await touch_last_used(db, key_obj.id)

    # Load the owning user so the rest of the app sees a normal User object.
    result = await db.execute(
        select(User).where(
            User.org_id == key_obj.tenant_id,
            User.id == key_obj.created_by,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key owner not found",
        )
    # Attach scopes to the request state so downstream handlers can inspect them.
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    # 1. Try Bearer API key first (programmatic access).
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer = auth_header[len("Bearer "):].strip()
        if bearer.startswith(_API_KEY_PREFIX):
            return await _resolve_api_key(bearer, db)

    # 2. Fall back to cookie-based JWT (browser session).
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
        )
    payload = verify_access_token(token)
    result = await db.execute(
        select(User).where(
            User.id == payload.sub,
            User.org_id == payload.tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or tenant mismatch",
        )
    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return user


async def get_current_tenant(request: Request) -> UUID:
    """Extrait le tenant_id depuis le JWT présent dans le cookie access_token."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
        )
    payload = verify_access_token(token)
    return payload.tenant_id
