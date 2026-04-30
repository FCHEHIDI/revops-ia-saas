from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.users.models import User
from app.users.schemas import UpdateProfileRequest
from fastapi import HTTPException


async def get_user_by_id(db: AsyncSession, user_id) -> User | None:
    q = await db.execute(select(User).where(User.id == user_id))
    return q.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    q = await db.execute(select(User).where(User.email == email))
    return q.scalar_one_or_none()


async def update_user_profile(
    db: AsyncSession, user_id, data: UpdateProfileRequest
) -> User:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.email is not None:
        user.email = data.email
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.job_title is not None:
        user.job_title = data.job_title
    if data.avatar is not None:
        user.avatar = data.avatar
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
