from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.db import get_db
from app.dependencies import get_current_user
from app.sessions.service import create_session, list_user_sessions, get_session, add_message
from app.sessions.schemas import SessionCreate, SessionResponse, AddMessageRequest
from app.sse import stream_llm_response
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.post("/", response_model=SessionResponse, status_code=201)
async def create_new_session(data: SessionCreate, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await create_session(db, user["user_id"], user["tenant_id"], data.title)
    return session

@router.get("/", response_model=list[SessionResponse])
async def get_sessions(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await list_user_sessions(db, user["user_id"])

@router.get("/{session_id}", response_model=SessionResponse)
async def get_single_session(session_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await get_session(db, session_id)
    if not session or session.org_id != user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return session

@router.post("/{session_id}/chat")
async def chat_with_agent(session_id: str, data: AddMessageRequest, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await add_message(db, session_id, data.role, data.content)
    return {"message": "Message added successfully"}
    # Simuler l'appel à l'orchestrateur ici, mais retourner l'écho à titre d'exemple
    async def event_stream():
        async for token in stream_llm_response(data.content, session_id):
            yield f"data: {token}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
