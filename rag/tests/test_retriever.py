"""Tests for the RAG layer.

Covers:
- TextChunker: splitting behaviour and overlap
- DocumentRetriever: tenant isolation guarantee (namespace scoping)
- EmbeddingService: output shape
- QdrantVectorStore: search delegation
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.embeddings.embedder import EmbeddingService
from app.indexing.chunker import Chunk, TextChunker
from app.models.schemas import ChunkResult
from app.retrieval.retriever import DocumentRetriever
from app.vector_store.qdrant_store import QdrantVectorStore, _collection_name


# ===========================================================================
# TextChunker
# ===========================================================================


class TestTextChunker:
    def test_short_text_returns_single_chunk(self) -> None:
        chunker = TextChunker(chunk_size=512, overlap=50)
        text = "Hello world."
        chunks = chunker.split(text)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0

    def test_empty_text_returns_empty_list(self) -> None:
        chunker = TextChunker(chunk_size=512, overlap=50)
        assert chunker.split("") == []
        assert chunker.split("   ") == []

    def test_long_text_produces_multiple_chunks(self) -> None:
        chunker = TextChunker(chunk_size=10, overlap=2)
        # 10 tokens * 4 chars = 40 chars per chunk, 2 tokens * 4 = 8 chars overlap
        text = "A" * 200
        chunks = chunker.split(text)
        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunks_are_non_empty(self) -> None:
        chunker = TextChunker(chunk_size=20, overlap=5)
        text = " ".join(f"word{i}" for i in range(100))
        chunks = chunker.split(text)
        assert all(c.text.strip() for c in chunks)

    def test_overlap_less_than_size_required(self) -> None:
        with pytest.raises(ValueError, match="overlap must be less than chunk_size"):
            TextChunker(chunk_size=10, overlap=10)

    def test_paragraph_mode_for_playbook(self) -> None:
        chunker = TextChunker(chunk_size=10, overlap=2)
        text = "Para one.\n\nPara two.\n\nPara three.\n\nPara four."
        chunks = chunker.split(text, document_type="playbook")
        assert len(chunks) >= 1

    def test_chunk_result_type(self) -> None:
        chunker = TextChunker(chunk_size=512, overlap=50)
        chunks = chunker.split("Some sample text for testing.")
        assert isinstance(chunks[0], Chunk)
        assert chunks[0].start_char == 0


# ===========================================================================
# Namespace helper
# ===========================================================================


class TestCollectionName:
    def test_already_formatted_namespace(self) -> None:
        uid = "550e8400-e29b-41d4-a716-446655440000"
        assert _collection_name(f"tenant_{uid}") == f"tenant_{uid}"

    def test_raw_uuid_gets_prefix(self) -> None:
        uid = "550e8400-e29b-41d4-a716-446655440000"
        assert _collection_name(uid) == f"tenant_{uid}"

    def test_strips_whitespace(self) -> None:
        uid = "550e8400-e29b-41d4-a716-446655440000"
        assert _collection_name(f"  tenant_{uid}  ") == f"tenant_{uid}"


# ===========================================================================
# EmbeddingService (mocked)
# ===========================================================================


class TestEmbeddingService:
    def test_embed_returns_correct_shape(self) -> None:
        svc = EmbeddingService(model_name="all-MiniLM-L6-v2", batch_size=32)

        mock_model = MagicMock()
        mock_model.encode.return_value = [
            MagicMock(tolist=lambda: [0.1] * 384),
            MagicMock(tolist=lambda: [0.2] * 384),
        ]
        mock_model.get_sentence_embedding_dimension.return_value = 384
        svc._model = mock_model

        result = asyncio.get_event_loop().run_until_complete(
            svc.embed(["text one", "text two"])
        )
        assert len(result) == 2
        assert len(result[0]) == 384

    def test_embed_one_returns_single_vector(self) -> None:
        svc = EmbeddingService(model_name="all-MiniLM-L6-v2", batch_size=32)

        mock_model = MagicMock()
        mock_model.encode.return_value = [MagicMock(tolist=lambda: [0.5] * 384)]
        mock_model.get_sentence_embedding_dimension.return_value = 384
        svc._model = mock_model

        result = asyncio.get_event_loop().run_until_complete(svc.embed_one("hello"))
        assert len(result) == 384


# ===========================================================================
# DocumentRetriever — tenant isolation
# ===========================================================================


class TestDocumentRetriever:
    def _make_retriever(
        self, store_hits: list[dict]
    ) -> tuple[DocumentRetriever, QdrantVectorStore]:
        mock_store = MagicMock(spec=QdrantVectorStore)
        mock_store.search = AsyncMock(return_value=store_hits)

        mock_embedder = MagicMock(spec=EmbeddingService)
        mock_embedder.embed_one = AsyncMock(return_value=[0.1] * 384)

        retriever = DocumentRetriever(vector_store=mock_store, embedder=mock_embedder)
        return retriever, mock_store

    def test_retrieve_scopes_to_tenant_namespace(self) -> None:
        tenant_id = uuid4()
        retriever, mock_store = self._make_retriever([])

        asyncio.get_event_loop().run_until_complete(
            retriever.retrieve(tenant_id=tenant_id, query="test query")
        )

        mock_store.search.assert_called_once()
        call_kwargs = mock_store.search.call_args.kwargs
        assert call_kwargs["namespace"] == f"tenant_{tenant_id}"

    def test_different_tenants_use_different_namespaces(self) -> None:
        tenant_a = uuid4()
        tenant_b = uuid4()
        retriever, mock_store = self._make_retriever([])

        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            retriever.retrieve(tenant_id=tenant_a, query="query a")
        )
        loop.run_until_complete(
            retriever.retrieve(tenant_id=tenant_b, query="query b")
        )

        calls = mock_store.search.call_args_list
        ns_a = calls[0].kwargs["namespace"]
        ns_b = calls[1].kwargs["namespace"]
        assert ns_a != ns_b
        assert ns_a == f"tenant_{tenant_a}"
        assert ns_b == f"tenant_{tenant_b}"

    def test_retrieve_maps_hits_to_chunk_results(self) -> None:
        doc_id = uuid4()
        hits = [
            {
                "document_id": str(doc_id),
                "filename": "playbook.md",
                "chunk_index": 0,
                "content": "Handle objections by …",
                "similarity_score": 0.92,
                "document_type": "playbook",
                "page_number": None,
            }
        ]
        retriever, _ = self._make_retriever(hits)

        results = asyncio.get_event_loop().run_until_complete(
            retriever.retrieve(tenant_id=uuid4(), query="objections")
        )

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, ChunkResult)
        assert r.document_id == doc_id
        assert r.similarity_score == pytest.approx(0.92)
        assert "objections" in r.content

    def test_retrieve_skips_malformed_hits_gracefully(self) -> None:
        bad_hits = [{"document_id": "not-a-uuid", "content": "broken"}]
        retriever, _ = self._make_retriever(bad_hits)

        results = asyncio.get_event_loop().run_until_complete(
            retriever.retrieve(tenant_id=uuid4(), query="test")
        )
        assert results == []

    def test_retrieve_respects_top_k(self) -> None:
        retriever, mock_store = self._make_retriever([])

        asyncio.get_event_loop().run_until_complete(
            retriever.retrieve(tenant_id=uuid4(), query="q", top_k=3)
        )

        assert mock_store.search.call_args.kwargs["top_k"] == 3

    def test_retrieve_respects_min_score(self) -> None:
        retriever, mock_store = self._make_retriever([])

        asyncio.get_event_loop().run_until_complete(
            retriever.retrieve(tenant_id=uuid4(), query="q", min_score=0.7)
        )

        assert mock_store.search.call_args.kwargs["min_score"] == pytest.approx(0.7)
