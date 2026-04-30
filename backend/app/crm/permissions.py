from fastapi import Header, HTTPException, Depends
from typing import Optional
from uuid import UUID
import secrets
from app.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.db import get_db
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN

def verify_internal_api_key(x_internal_api_key: str = Header(alias="X-Internal-API-Key")):
    expected = settings.internal_api_key
    if not expected or not secrets.compare_digest(x_internal_api_key, expected):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")

def extract_tenant(x_tenant_id: str = Header(alias="X-Tenant-ID")) -> UUID:
    try:
        return UUID(x_tenant_id)
    except Exception:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid or missing tenant UUID")

def extract_user_id(x_user_id: Optional[str] = Header(alias="X-User-ID", default=None)) -> Optional[UUID]:
    if x_user_id is None:
        return None
    try:
        return UUID(x_user_id)
    except Exception:
        return None

def require_permission(perm: str):
    """Return a FastAPI-compatible dependency callable enforcing `perm`.

    Usage in router:
        dependencies=[Depends(require_permission("crm:accounts:write"))]
    """
    async def checker(
        user_id: Optional[UUID] = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db),
    ):
        if user_id is None:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="User permissions required",
            )
        from app.models import User as UserModel
        result = await db.execute(
            UserModel.__table__.select().where(UserModel.id == user_id)
        )
        user = result.fetchone()
        if not user or not user.permissions or perm not in user.permissions:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=f"Permission {perm} required",
            )
    return checker
