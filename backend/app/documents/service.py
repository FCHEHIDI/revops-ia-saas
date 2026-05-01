import logging
from pathlib import Path
from typing import List
from uuid import uuid4

import httpx
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.common.utils import utcnow
from app.config import settings
from app.documents.models import Document

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def upload_document(
    db: AsyncSession, org_id, user_id, file: UploadFile
) -> Document:
    """Save uploaded file to disk, record in DB, and trigger RAG ingestion."""
    # Sanitise filename — strip any path components the client might inject
    safe_name = Path(file.filename or "upload").name
    file_id = uuid4()
    storage_path = str(UPLOAD_DIR / f"{file_id}_{safe_name}")

    content_bytes = await file.read()
    with open(storage_path, "wb") as fh:
        fh.write(content_bytes)

    doc = Document(
        id=file_id,
        org_id=org_id,
        user_id=user_id,
        filename=safe_name,
        content_type=file.content_type or "application/octet-stream",
        storage_path=storage_path,
        status="processing",
        created_at=utcnow(),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Attempt text extraction for direct content passing (avoids shared-volume
    # requirement between backend and RAG in local dev)
    try:
        text_content: str | None = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text_content = None  # binary file (PDF etc.) — RAG reads from storage_path

    await _trigger_ingest(doc, text_content, db)
    return doc


async def _trigger_ingest(
    doc: Document,
    text_content: str | None,
    db: AsyncSession,
) -> None:
    """Call RAG /ingest and update document status."""
    namespace = f"tenant_{doc.org_id}"
    payload: dict = {
        "namespace": namespace,
        "document_id": str(doc.id),
        "storage_path": doc.storage_path,
        "filename": doc.filename,
        "document_type": "other",
    }
    if text_content is not None:
        payload["content"] = text_content

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.rag_api_url}/ingest",
                json=payload,
                headers={"X-Internal-API-Key": settings.mcp_inter_service_secret},
            )
            resp.raise_for_status()
        # RAG accepted the job (202) — background task will complete shortly
        doc.status = "indexed"
        logger.info("RAG ingestion queued for document %s", doc.id)
    except Exception as exc:
        doc.status = "error"
        logger.error("RAG ingestion failed for document %s: %s", doc.id, exc)

    await db.commit()


async def delete_document(db: AsyncSession, doc: Document) -> None:
    """Remove document chunks from RAG then delete DB record."""
    namespace = f"tenant_{doc.org_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.delete(
                f"{settings.rag_api_url}/documents/{doc.id}",
                headers={
                    "X-Internal-API-Key": settings.mcp_inter_service_secret,
                    "X-Namespace": namespace,
                },
            )
    except Exception as exc:
        logger.warning("RAG delete failed for document %s: %s (continuing)", doc.id, exc)

    await db.delete(doc)
    await db.commit()


async def list_documents(db: AsyncSession, org_id) -> List[Document]:
    """List all documents for a tenant, most recent first."""
    q = await db.execute(
        select(Document)
        .where(Document.org_id == org_id)
        .order_by(Document.created_at.desc())
    )
    return q.scalars().all()


async def get_document(db: AsyncSession, doc_id) -> Document | None:
    q = await db.execute(select(Document).where(Document.id == doc_id))
    return q.scalar_one_or_none()
