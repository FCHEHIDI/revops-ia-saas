from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.common.db import get_db
from app.config import settings
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.sessions.service import (
    add_message,
    add_messages_batch,
    create_session,
    delete_session,
    get_session,
    list_user_sessions,
)
from app.sessions.schemas import (
    AddMessageRequest,
    BatchMessagesRequest,
    SessionCreate,
    SessionResponse,
)

router = APIRouter()


@router.post("/", response_model=SessionResponse, status_code=201)
async def create_new_session(
    data: SessionCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    session = await create_session(db, user.id, user.tenant_id, data.title)
    return session


@router.get("/", response_model=list[SessionResponse])
async def get_sessions(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_user_sessions(db, user.id, user.tenant_id)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_single_session(
    session_id: str,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if not session or str(session.org_id) != str(user.tenant_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}", status_code=204)
async def remove_session(
    session_id: str,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_session(db, session_id, user.id, user.tenant_id)


@router.post("/{session_id}/messages", response_model=SessionResponse)
async def persist_messages(
    session_id: str,
    data: BatchMessagesRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist a batch of messages (user + assistant) after a streaming exchange."""
    raw = [
        {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat() if m.timestamp else None}
        for m in data.messages
    ]
    return await add_messages_batch(
        db, session_id, raw,
        owner_user_id=user.id,
        owner_org_id=user.tenant_id,
    )


@router.post("/{session_id}/chat")
async def chat_with_agent(
    session_id: str,
    data: AddMessageRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy a chat message through the orchestrator with SSE streaming.

    Stores the user message in the session, forwards to the orchestrator,
    and streams SSE tokens back to the client. The assistant response is
    saved asynchronously once the stream completes.
    """
    session = await get_session(db, session_id)
    if not session or str(session.org_id) != str(user.tenant_id):
        raise HTTPException(status_code=404, detail="Session not found")

    # Persist the user message immediately
    await add_message(
        db, session_id, data.role, data.content,
        owner_user_id=user.id,
        owner_org_id=user.tenant_id,
    )

    orchestrator_payload = {
        "tenant_id": str(user.tenant_id),
        "conversation_id": session_id,
        "message": data.content,
        "user_id": str(user.id),
    }

    async def event_stream():
        import json as _json
        assistant_tokens: list[str] = []
        # Accumulated usage from the orchestrator Done event
        usage_stats: dict = {}
        # Number of MCP tool_call events received
        mcp_call_count: int = 0

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.orchestrator_url}/process",
                    json=orchestrator_payload,
                    headers={"X-Internal-API-Key": settings.internal_secret},
                ) as resp:
                    if resp.status_code != 200:
                        yield f"data: {{\"type\":\"error\",\"message\":\"Orchestrator returned {resp.status_code}\"}}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            yield "\n"
                            continue
                        yield f"{line}\n"
                        # Collect tokens / usage for persistence
                        if line.startswith("data: "):
                            try:
                                ev = _json.loads(line[6:])
                                ev_type = ev.get("type")
                                if ev_type == "token":
                                    assistant_tokens.append(ev.get("content", ""))
                                elif ev_type == "done":
                                    usage_stats = ev.get("usage", {})
                                elif ev_type == "tool_call":
                                    mcp_call_count += 1
                            except Exception:
                                pass
        finally:
            # Persist assistant response after stream ends (best-effort)
            if assistant_tokens:
                from app.common.db import AsyncSessionLocal
                async with AsyncSessionLocal() as persist_db:
                    try:
                        await add_message(
                            persist_db, session_id, "assistant",
                            "".join(assistant_tokens),
                        )
                    except Exception:
                        pass  # non-fatal

            # Record usage events (fire-and-forget, best-effort)
            if usage_stats or mcp_call_count:
                from app.common.db import AsyncSessionLocal
                from app.usage.service import record_usage
                from app.usage.schemas import UsageEventCreate
                tenant_uuid = user.tenant_id
                session_meta = {"session_id": session_id}
                async with AsyncSessionLocal() as usage_db:
                    try:
                        prompt_tokens = int(usage_stats.get("prompt_tokens", 0))
                        completion_tokens = int(usage_stats.get("completion_tokens", 0))
                        if prompt_tokens > 0:
                            await record_usage(
                                usage_db,
                                UsageEventCreate(
                                    tenant_id=tenant_uuid,
                                    event_type="llm_tokens_input",
                                    quantity=prompt_tokens,
                                    metadata=session_meta,
                                ),
                            )
                        if completion_tokens > 0:
                            await record_usage(
                                usage_db,
                                UsageEventCreate(
                                    tenant_id=tenant_uuid,
                                    event_type="llm_tokens_output",
                                    quantity=completion_tokens,
                                    metadata=session_meta,
                                ),
                            )
                        if mcp_call_count > 0:
                            await record_usage(
                                usage_db,
                                UsageEventCreate(
                                    tenant_id=tenant_uuid,
                                    event_type="mcp_calls",
                                    quantity=mcp_call_count,
                                    metadata=session_meta,
                                ),
                            )
                        await usage_db.commit()
                    except Exception:
                        pass  # non-fatal — metering must never break chat

    return StreamingResponse(event_stream(), media_type="text/event-stream")
