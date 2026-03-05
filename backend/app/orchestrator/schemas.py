from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

class OrchestratorProcessRequest(BaseModel):
    message: str
    session_id: UUID
    tenant_id: UUID
    user_id: UUID

class AddSessionMessageRequest(BaseModel):
    role: str
    content: str
    timestamp: datetime

class LLMCallbackRequest(BaseModel):
    session_id: UUID
    content: str
    finish_reason: Optional[str] = None
