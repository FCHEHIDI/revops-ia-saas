from pydantic import BaseModel, ConfigDict
from enum import Enum
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime


class SessionCreate(BaseModel):
    title: Optional[str] = None


class SessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    org_id: UUID
    title: Optional[str]
    messages: List[Message]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SessionHistoryResponse(BaseModel):
    session_id: UUID
    messages: List[Message]


class AddMessageRequest(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime
