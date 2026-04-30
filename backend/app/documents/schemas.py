from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime


class DocumentResponse(BaseModel):
    id: UUID
    org_id: UUID
    filename: str
    content_type: str
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
