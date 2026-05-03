from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.db import get_db
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.audit.service import list_audit_logs
from app.audit.schemas import AuditLogResponse

router = APIRouter()


@router.get("/", response_model=list[AuditLogResponse])
async def get_logs(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Vérification du rôle admin : on suppose qu'il existe une permission 'admin'
    if "admin" not in (user.permissions or []):
        raise HTTPException(status_code=403, detail="Admin permission required")
    return await list_audit_logs(db, user.tenant_id)
