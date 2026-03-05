import httpx
from app.config import settings
from fastapi import HTTPException, status
from app.sessions.models import UserSession
from app.sessions.schemas import MessageRole
from app.common.utils import utcnow
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

async def send_to_orchestrator(message: str, session_id, tenant_id, user_id):
    async with httpx.AsyncClient() as client:
        headers = {"X-Internal-Secret": settings.internal_secret}
        payload = {
            "message": message,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
        }
        resp = await client.post(f"{settings.orchestrator_url}/process", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to send to orchestrator")

async def handle_llm_callback(db: AsyncSession, session_id, content):
    q = await db.execute(select(UserSession).where(UserSession.id == session_id))
    session = q.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    message = {"role": MessageRole.assistant, "content": content, "timestamp": utcnow()}
    session.messages.append(message)
    db.add(session)
    await db.commit()
    await db.refresh(session)
