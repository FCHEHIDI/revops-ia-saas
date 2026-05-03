from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.models.user import User
from app.api_keys import service
from app.api_keys.schemas import (
    ApiKeyCreate,
    ApiKeyPublic,
    ApiKeyResponse,
    VALID_SCOPES,
)

router = APIRouter()


@router.post(
    "",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key",
    description=(
        "Returns the plaintext key **once** — store it immediately, "
        "it cannot be retrieved again."
    ),
)
async def create_api_key(
    payload: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiKeyResponse:
    invalid_scopes = set(payload.scopes) - VALID_SCOPES
    if invalid_scopes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid scopes: {sorted(invalid_scopes)}. "
                   f"Valid scopes: {sorted(VALID_SCOPES)}",
        )
    key_obj, raw_key = await service.create_api_key(
        db=db,
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=payload.name,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
    )
    return ApiKeyResponse(
        id=key_obj.id,
        name=key_obj.name,
        scopes=key_obj.scopes,
        expires_at=key_obj.expires_at,
        created_at=key_obj.created_at,
        key=raw_key,
    )


@router.get(
    "",
    response_model=list[ApiKeyPublic],
    summary="List API keys for the current tenant",
)
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ApiKeyPublic]:
    keys = await service.list_api_keys(db, current_user.tenant_id)
    return [ApiKeyPublic.model_validate(k) for k in keys]


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    ok = await service.revoke_api_key(db, key_id, current_user.tenant_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
