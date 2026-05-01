from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified
from app.sessions.models import UserSession
from app.sessions.schemas import Message
from uuid import uuid4, UUID
from app.common.utils import utcnow
from fastapi import HTTPException


async def create_session(db: AsyncSession, user_id, org_id, title=None) -> UserSession:
    session = UserSession(
        id=uuid4(),
        user_id=user_id,
        org_id=org_id,
        title=title,
        messages=[],
        created_at=utcnow(),
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


async def add_message(
    db: AsyncSession, session_id, role: str, content: str,
    owner_user_id=None, owner_org_id=None,
) -> UserSession:
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if owner_user_id is not None and session.user_id != owner_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if owner_org_id is not None and session.org_id != owner_org_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    message = {"role": role, "content": content, "timestamp": utcnow().isoformat()}
    # Reassign to a new list so SQLAlchemy detects the JSONB mutation
    session.messages = list(session.messages) + [message]
    flag_modified(session, "messages")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def add_messages_batch(
    db: AsyncSession, session_id, messages: list[dict],
    owner_user_id=None, owner_org_id=None,
) -> UserSession:
    """Append multiple messages atomically — used for persisting a full chat exchange."""
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if owner_user_id is not None and session.user_id != owner_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if owner_org_id is not None and session.org_id != owner_org_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    session.messages = list(session.messages) + messages
    flag_modified(session, "messages")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def delete_session(
    db: AsyncSession, session_id, owner_user_id, owner_org_id,
) -> None:
    session = await get_session(db, session_id)
    if not session or session.user_id != owner_user_id or session.org_id != owner_org_id:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    await db.commit()


async def list_user_sessions(
    db: AsyncSession, user_id, org_id,
) -> list[UserSession]:
    q = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.org_id == org_id,
        ).order_by(UserSession.created_at.desc())
    )
    return q.scalars().all()
