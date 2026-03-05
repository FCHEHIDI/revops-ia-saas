from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional
from datetime import datetime

class AuditLogResponse(BaseModel):
    id: UUID
    org_id: UUID
    user_id: Optional[UUID]
    action: str
    resource: str
    payload: Optional[dict]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
