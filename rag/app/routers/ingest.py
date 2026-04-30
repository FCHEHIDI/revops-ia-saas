"""Ingestion endpoints.

POST  /ingest                  — enqueue document ingestion (called by mcp-filesystem)
DELETE /documents/{document_id} — delete all chunks for a document
"""

import asyncio
import logging
import os
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.dependencies import (
    get_chunker,
    get_embedder,
    get_vector_store,
    require_internal_api_key,
)
from app.config import settings
from app.embeddings.embedder import EmbeddingService
from app.indexing.chunker import TextChunker
from app.indexing.document_parser import detect_document_type, extract_text
from app.models.schemas import DeleteResponse, IngestRequest, IngestResponse
from app.vector_store.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="",
    tags=["ingest"],
    dependencies=[Depends(require_internal_api_key)],
)


# ---------------------------------------------------------------------------
# POST /ingest
# ---------------------------------------------------------------------------


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue document ingestion",
    description=(
        "Accepts a document reference from mcp-filesystem and immediately returns "
        "a job_id.  The actual chunking, embedding, and Qdrant upsert run "
        "asynchronously as a background task."
    ),
)
async def ingest_document(
    body: IngestRequest,
    background_tasks: BackgroundTasks,
    store: QdrantVectorStore = Depends(get_vector_store),
    embedder: EmbeddingService = Depends(get_embedder),
    chunker: TextChunker = Depends(get_chunker),
) -> IngestResponse:
    job_id = uuid4()

    background_tasks.add_task(
        _run_ingestion,
        store=store,
        embedder=embedder,
        chunker=chunker,
        namespace=body.namespace,
        document_id=body.document_id,
        storage_path=body.storage_path,
        filename=body.filename or os.path.basename(body.storage_path),
        document_type=body.document_type or detect_document_type(
            body.filename or os.path.basename(body.storage_path)
        ),
        content=body.content,
    )

    logger.info(
        "Ingestion job %s queued for namespace='%s' document_id=%s",
        job_id,
        body.namespace,
        body.document_id,
    )
    return IngestResponse(job_id=job_id, status="queued")


# ---------------------------------------------------------------------------
# DELETE /documents/{document_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/documents/{document_id}",
    response_model=DeleteResponse,
    summary="Delete all chunks for a document",
)
async def delete_document(
    document_id: UUID,
    namespace: str,
    store: QdrantVectorStore = Depends(get_vector_store),
) -> DeleteResponse:
    """Remove all Qdrant points belonging to *document_id* within *namespace*."""
    deleted = await store.delete_document(namespace, document_id)
    return DeleteResponse(
        document_id=document_id,
        namespace=namespace,
        deleted_count=deleted,
    )


# ---------------------------------------------------------------------------
# Background ingestion pipeline
# ---------------------------------------------------------------------------


async def _run_ingestion(
    *,
    store: QdrantVectorStore,
    embedder: EmbeddingService,
    chunker: TextChunker,
    namespace: str,
    document_id: UUID,
    storage_path: str,
    filename: str,
    document_type: str,
    content: str | None,
) -> None:
    """Full ingestion pipeline executed in a background task."""
    try:
        if content is None:
            content = await _read_from_storage(storage_path)

        if not content.strip():
            logger.warning(
                "Empty content for document %s (path=%s) — skipping",
                document_id,
                storage_path,
            )
            return

        chunks = chunker.split(content, document_type=document_type)
        if not chunks:
            logger.warning("No chunks produced for document %s", document_id)
            return

        texts = [c.text for c in chunks]
        embeddings = await embedder.embed(texts)

        # Idempotent: delete stale chunks before upserting new ones
        await store.delete_document(namespace, document_id)

        count = await store.upsert_chunks(
            namespace=namespace,
            document_id=document_id,
            filename=filename,
            document_type=document_type,
            chunks=texts,
            embeddings=embeddings,
        )
        logger.info(
            "Ingested %d chunks for document %s in namespace '%s'",
            count,
            document_id,
            namespace,
        )
    except Exception as exc:
        logger.error(
            "Ingestion failed for document %s namespace='%s': %s",
            document_id,
            namespace,
            exc,
            exc_info=True,
        )


async def _read_from_storage(storage_path: str) -> str:
    """Extract text from the shared storage volume, dispatching by file type.

    Supports .txt, .md, .csv (plain UTF-8), .pdf (pypdf), .docx (python-docx),
    and .xlsx/.xls (openpyxl).  Falls back to UTF-8 for unknown extensions.

    Args:
        storage_path: Relative path under ``settings.storage_base_path``.

    Returns:
        Extracted plain text ready for chunking.

    Raises:
        HTTPException 404: If the file does not exist in storage.
    """
    full_path = os.path.join(settings.storage_base_path, storage_path)
    loop = asyncio.get_event_loop()
    try:
        text = await loop.run_in_executor(None, extract_text, full_path)
        return text
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Storage file not found: {storage_path}",
        )
