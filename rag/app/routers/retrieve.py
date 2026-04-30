"""Retrieval endpoints.

POST /retrieve  — used by the orchestrator LLM (tenant_id in body)
POST /search    — used by mcp-filesystem RagClient (namespace in body)
"""

import logging

from fastapi import APIRouter, Depends

from app.dependencies import get_retriever, require_internal_api_key
from app.models.schemas import (
    RetrieveRequest,
    RetrieveResponse,
    SearchRequest,
    SearchResponse,
)
from app.retrieval.retriever import DocumentRetriever

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="",
    tags=["retrieve"],
    dependencies=[Depends(require_internal_api_key)],
)


# ---------------------------------------------------------------------------
# POST /retrieve  — orchestrator
# ---------------------------------------------------------------------------


@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    summary="Retrieve relevant document chunks (orchestrator)",
    description=(
        "Embeds *query*, performs cosine-similarity search within the tenant's "
        "Qdrant collection, and returns the top-K most relevant chunks.  "
        "The search is strictly scoped to ``tenant_{tenant_id}`` — no cross-tenant "
        "retrieval is possible."
    ),
)
async def retrieve(
    body: RetrieveRequest,
    retriever: DocumentRetriever = Depends(get_retriever),
) -> RetrieveResponse:
    results = await retriever.retrieve(
        tenant_id=body.tenant_id,
        query=body.query,
        top_k=body.top_k,
        min_score=body.min_score,
        document_types=body.document_types,
    )
    return RetrieveResponse(
        tenant_id=body.tenant_id,
        query=body.query,
        results=results,
        total_found=len(results),
    )


# ---------------------------------------------------------------------------
# POST /search  — mcp-filesystem RagClient
# ---------------------------------------------------------------------------


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search by namespace (mcp-filesystem)",
    description=(
        "Compatible with ``mcp-filesystem``'s ``RagClient.search()`` — "
        "accepts a pre-formatted namespace (``tenant_{uuid}``), query, "
        "top_k, min_score and optional document_type filters."
    ),
)
async def search(
    body: SearchRequest,
    retriever: DocumentRetriever = Depends(get_retriever),
) -> SearchResponse:
    document_types = body.filters.document_types if body.filters else None
    results, total = await retriever.search_by_namespace(
        namespace=body.namespace,
        query=body.query,
        top_k=body.top_k,
        min_score=body.min_score,
        document_types=document_types if document_types else None,
    )
    return SearchResponse(results=results, total_found=total)
