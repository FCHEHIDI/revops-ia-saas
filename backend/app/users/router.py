from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.db import get_db
from app.dependencies import get_current_user
from app.users.service import get_user_by_id, update_user_profile
from app.users.schemas import UserResponse, UpdateProfileRequest

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_me(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    db_user = await get_user_by_id(db, user["user_id"])
    return db_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UpdateProfileRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await update_user_profile(db, user["user_id"], data)
    return updated
