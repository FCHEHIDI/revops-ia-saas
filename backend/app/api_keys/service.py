"""API Key service — generation, hashing, validation, rate limiting.

Key format : ``rk_live_<32 url-safe chars>``  (total ≥ 40 chars)
Storage    : SHA-256 hex-digest, never the plaintext.
Rate limit : 60 requests / minute per key, tracked in Redis with a sliding
             window counter (INCR + EXPIRE).  Falls back gracefully when
             Redis is unavailable.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.common.utils import utcnow
from app.models.api_key import ApiKey

_KEY_PREFIX = "rk_live_"
_RATE_LIMIT_WINDOW = 60       # seconds
_RATE_LIMIT_MAX_REQUESTS = 60 # requests per window


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_raw_key() -> str:
    """Return a new plaintext key, e.g. ``rk_live_xB3k…``."""
    return _KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(raw_key: str) -> str:
    """SHA-256 hex-digest of the raw key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def create_api_key(
    db: AsyncSession,
    tenant_id: UUID,
    created_by: UUID,
    name: str,
    scopes: list[str],
    expires_at: Optional[datetime],
) -> tuple[ApiKey, str]:
    """Create and persist a new API key.

    Returns:
        Tuple of (ApiKey ORM object, raw plaintext key).
        The caller is responsible for returning the plaintext key to the
        client exactly once — it is not stored.
    """
    raw_key = generate_raw_key()
    key_obj = ApiKey(
        id=uuid4(),
        tenant_id=tenant_id,
        created_by=created_by,
        name=name,
        key_hash=hash_key(raw_key),
        scopes=scopes,
        expires_at=expires_at,
    )
    db.add(key_obj)
    await db.commit()
    await db.refresh(key_obj)
    return key_obj, raw_key


async def list_api_keys(db: AsyncSession, tenant_id: UUID) -> list[ApiKey]:
    """Return all API keys for a tenant (active and inactive)."""
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.tenant_id == tenant_id)
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(
    db: AsyncSession, key_id: UUID, tenant_id: UUID
) -> bool:
    """Deactivate a key. Returns False if not found or wrong tenant."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
    )
    key_obj = result.scalar_one_or_none()
    if key_obj is None:
        return False
    key_obj.active = False
    await db.commit()
    return True


async def lookup_key(db: AsyncSession, raw_key: str) -> Optional[ApiKey]:
    """Resolve a raw key to its ApiKey record if valid (active, not expired)."""
    digest = hash_key(raw_key)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.active.is_(True))
    )
    key_obj = result.scalar_one_or_none()
    if key_obj is None:
        return None
    if key_obj.expires_at and key_obj.expires_at < utcnow():
        return None
    return key_obj


async def touch_last_used(db: AsyncSession, key_id: UUID) -> None:
    """Update last_used_at without loading the full object (fire-and-forget)."""
    await db.execute(
        update(ApiKey)
        .where(ApiKey.id == key_id)
        .values(last_used_at=utcnow())
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

async def check_rate_limit(raw_key: str) -> bool:
    """Return True if the key is within its rate limit, False if exceeded.

    Uses a Redis INCR counter with a sliding TTL of 60 seconds.
    Silently allows the request when Redis is unreachable (fail open).
    """
    if not settings.redis_url:
        return True
    redis_key = f"apikey_rl:{hash_key(raw_key)}"
    try:
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        async with redis.client() as conn:
            count = await conn.incr(redis_key)
            if count == 1:
                await conn.expire(redis_key, _RATE_LIMIT_WINDOW)
            return count <= _RATE_LIMIT_MAX_REQUESTS
    except Exception:  # Redis unavailable — fail open
        return True
