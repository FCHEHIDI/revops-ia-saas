from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.common.db import get_db
from app.sessions.service import get_session_history
from app.sessions.schemas import SessionHistoryResponse
from app.orchestrator.schemas import AddSessionMessageRequest, LLMCallbackRequest
from app.orchestrator.service import handle_llm_callback
from uuid import UUID

router = APIRouter()

def verify_internal_secret(x_internal_secret: str = Header(...)):
    if x_internal_secret != settings.internal_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse, dependencies=[Depends(verify_internal_secret)])
async def get_history(session_id: UUID, db: AsyncSession = Depends(get_db)):
    messages = await get_session_history(db, session_id)
    return SessionHistoryResponse(session_id=session_id, messages=messages)

@router.post("/sessions/{session_id}/messages", status_code=201, dependencies=[Depends(verify_internal_secret)])
async def add_message_to_session(session_id: UUID, data: AddSessionMessageRequest, db: AsyncSession = Depends(get_db)):
    from app.sessions.service import add_message
    await add_message(db, session_id, data.role, data.content)
    return {"detail": "Message added"}

@router.post("/llm/callback", status_code=204, dependencies=[Depends(verify_internal_secret)])
async def llm_callback(data: LLMCallbackRequest, db: AsyncSession = Depends(get_db)):
    await handle_llm_callback(db, data.session_id, data.content)
