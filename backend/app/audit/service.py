from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.audit.models import AuditLog
from app.common.utils import utcnow
from uuid import uuid4

async def log_action(db: AsyncSession, org_id, user_id, action, resource, payload) -> AuditLog:
    log = AuditLog(
        id=uuid4(),
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource=resource,
        payload=payload,
        created_at=utcnow()
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log

async def list_audit_logs(db: AsyncSession, org_id, limit=100) -> list[AuditLog]:
    q = await db.execute(select(AuditLog).where(AuditLog.org_id == org_id).order_by(AuditLog.created_at.desc()).limit(limit))
    return q.scalars().all()
