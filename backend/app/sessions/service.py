from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.sessions.models import UserSession
from app.sessions.schemas import Message
from uuid import uuid4
from app.common.utils import utcnow
from fastapi import HTTPException, status
from typing import List

async def create_session(db: AsyncSession, user_id, org_id, title=None) -> UserSession:
    session = UserSession(
        id=uuid4(),
        user_id=user_id,
        org_id=org_id,
        title=title,
        messages=[],
        created_at=utcnow()
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

async def get_session(db: AsyncSession, session_id) -> UserSession | None:
    q = await db.execute(select(UserSession).where(UserSession.id == session_id))
    return q.scalar_one_or_none()

async def get_session_history(db: AsyncSession, session_id) -> list[Message]:
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.messages

async def add_message(db: AsyncSession, session_id, role, content) -> UserSession:
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    message = {"role": role, "content": content, "timestamp": utcnow()}
    session.messages.append(message)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

async def list_user_sessions(db: AsyncSession, user_id) -> list[UserSession]:
    q = await db.execute(select(UserSession).where(UserSession.user_id == user_id))
    return q.scalars().all()
