from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.db import get_db
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.users.service import get_user_by_id, update_user_profile
from app.users.schemas import UserResponse, UpdateProfileRequest

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    db_user = await get_user_by_id(db, user.id)
    return db_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UpdateProfileRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await update_user_profile(db, user.id, data)
    return updated
