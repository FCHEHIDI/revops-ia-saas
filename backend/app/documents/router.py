from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.db import get_db
from app.dependencies import get_current_user
from app.documents.service import upload_document, list_documents, get_document
from app.documents.schemas import DocumentResponse

router = APIRouter()

@router.post("/", response_model=DocumentResponse)
async def upload(user=Depends(get_current_user), db: AsyncSession = Depends(get_db), file: UploadFile = File(...)):
    doc = await upload_document(db, user["tenant_id"], user["user_id"], file)
    return doc

@router.get("/", response_model=list[DocumentResponse])
async def list_docs(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await list_documents(db, user["tenant_id"])

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_doc(document_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    doc = await get_document(db, document_id)
    if not doc or doc.org_id != user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return doc
