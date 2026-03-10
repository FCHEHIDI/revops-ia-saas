from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.documents.models import Document
from fastapi import UploadFile
from uuid import uuid4
from app.common.utils import utcnow
from typing import List

async def upload_document(db: AsyncSession, org_id, user_id, file: UploadFile) -> Document:
    filename = file.filename
    content_type = file.content_type
    storage_path = f"uploads/{uuid4()}_{filename}"
    with open(storage_path, "wb") as f:
        f.write(await file.read())
    doc = Document(
        id=uuid4(),
        org_id=org_id,
        user_id=user_id,
        filename=filename,
        content_type=content_type,
        storage_path=storage_path,
        status="pending",
        created_at=utcnow()
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc

async def list_documents(db: AsyncSession, org_id) -> List[Document]:
    q = await db.execute(select(Document).where(Document.org_id == org_id))
    return q.scalars().all()

async def get_document(db: AsyncSession, doc_id) -> Document | None:
    q = await db.execute(select(Document).where(Document.id == doc_id))
    return q.scalar_one_or_none()
