from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingest schemas
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    """Payload sent by mcp-filesystem via POST /ingest.

    The namespace follows the convention ``tenant_{tenant_id}`` and maps
    directly to the Qdrant collection name, ensuring tenant isolation.
    """

    namespace: str = Field(
        ...,
        description="Qdrant collection name — format: 'tenant_{tenant_id}'",
        examples=["tenant_550e8400-e29b-41d4-a716-446655440000"],
    )
    document_id: UUID = Field(..., description="Unique identifier of the document")
    storage_path: str = Field(
        ...,
        description="Relative path to the file in the shared storage volume",
    )
    filename: Optional[str] = Field(
        None,
        description="Human-readable filename for metadata storage",
    )
    document_type: Optional[str] = Field(
        "other",
        description="Document type (playbook, report, contract, …)",
    )
    content: Optional[str] = Field(
        None,
        description="Raw text content — used instead of reading from storage_path when provided",
    )


class IngestResponse(BaseModel):
    """Returned immediately by POST /ingest; actual processing is async."""

    job_id: UUID = Field(default_factory=uuid4)
    status: str = "queued"


# ---------------------------------------------------------------------------
# Search schemas — matches rag_client.rs SearchRequest / SearchResponse
# ---------------------------------------------------------------------------


class SearchFilters(BaseModel):
    document_types: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    """POST /search — called by mcp-filesystem RagClient."""

    namespace: str = Field(..., description="Qdrant collection: 'tenant_{tenant_id}'")
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    filters: Optional[SearchFilters] = None


class ChunkResult(BaseModel):
    """Single retrieved chunk — matches DocumentChunk in mcp-filesystem schemas.rs."""

    document_id: UUID
    filename: str
    chunk_index: int
    content: str
    similarity_score: float
    document_type: str
    page_number: Optional[int] = None


class SearchResponse(BaseModel):
    results: list[ChunkResult]
    total_found: int


# ---------------------------------------------------------------------------
# Retrieve schemas — called by the orchestrator
# ---------------------------------------------------------------------------


class RetrieveRequest(BaseModel):
    """POST /retrieve — called by the orchestrator LLM."""

    tenant_id: UUID
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    document_types: Optional[list[str]] = None


class RetrieveResponse(BaseModel):
    tenant_id: UUID
    query: str
    results: list[ChunkResult]
    total_found: int


# ---------------------------------------------------------------------------
# Delete schemas
# ---------------------------------------------------------------------------


class DeleteResponse(BaseModel):
    document_id: UUID
    namespace: str
    deleted_count: int


# ---------------------------------------------------------------------------
# Redis job schemas
# ---------------------------------------------------------------------------


class RedisIngestJob(BaseModel):
    """Format of jobs pushed to the Redis ingestion queue by mcp-filesystem."""

    tenant_id: str
    file_path: str
    file_name: str
    content_type: str = "text/plain"
    document_id: Optional[str] = None
    document_type: Optional[str] = "other"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    qdrant: str = "unknown"
    redis: str = "unknown"
    embedding_model: str = ""
