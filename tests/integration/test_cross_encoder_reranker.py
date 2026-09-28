"""Integration tests for CrossEncoderReranker with a real cross-encoder model.

These tests download and run the actual cross-encoder model on CPU.
They verify end-to-end behavior: model loading, scoring, ordering.

Mark with @pytest.mark.integration to allow selective skipping.
"""

import time

import pytest

from src.adapters.cross_encoder_reranker import CrossEncoderReranker
from src.core.retrieval import RetrievedChunk
from src.ports.models import Chunk


def _make_chunk(doc_id: str, chunk_index: int, content: str) -> Chunk:
    return Chunk(
        document_id=doc_id,
        document_title="Test Doc",
        source_path="/test.md",
        section_path="",
        chunk_index=chunk_index,
        content=content,
        token_count=len(content) // 4,
        content_hash=f"hash_{doc_id}_{chunk_index}",
    )


def _make_retrieved_chunk(
    doc_id: str, chunk_index: int, content: str, score: float = 0.5
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=_make_chunk(doc_id, chunk_index, content),
        score=score,
        bm25_rank=chunk_index + 1,
        vector_rank=chunk_index + 1,
    )


@pytest.fixture
def reranker():
    """Create a CrossEncoderReranker with the default model."""
    return CrossEncoderReranker()


@pytest.mark.integration
class TestCrossEncoderIntegration:
    """Integration tests with real cross-encoder model."""

    @pytest.mark.asyncio
    async def test_model_loads_successfully(self, reranker):
        """Model loads from cache or downloads on first call."""
        assert reranker._model is None
        reranker._ensure_model()
        assert reranker._model is not None

    @pytest.mark.asyncio
    async def test_reranking_produces_ordered_scores(self, reranker):
        """Reranking produces scores in descending order."""
        candidates = [
            _make_retrieved_chunk("doc1", 0, "The capital of France is Paris."),
            _make_retrieved_chunk("doc1", 1, "Cats are furry animals."),
            _make_retrieved_chunk("doc1", 2, "Paris is a city in Europe."),
        ]

        results = await reranker.rerank("What is the capital of France?", candidates, top_k=3)

        assert len(results) == 3
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), "Scores should be descending"

    @pytest.mark.asyncio
    async def test_reranking_relevant_chunk_ranks_higher(self, reranker):
        """A highly relevant chunk ranks above irrelevant ones."""
        candidates = [
            _make_retrieved_chunk("doc1", 0, "The weather today is sunny and warm."),
            _make_retrieved_chunk("doc1", 1, "Python was created by Guido van Rossum."),
            _make_retrieved_chunk("doc1", 2, "Machine learning models require training data."),
        ]

        results = await reranker.rerank(
            "Who created the Python programming language?", candidates, top_k=3
        )

        # The Python chunk should be ranked first
        assert "Python" in results[0].chunk.content or "Guido" in results[0].chunk.content

    @pytest.mark.asyncio
    async def test_empty_candidates_with_real_model(self, reranker):
        """Empty candidates returns empty list even with real model."""
        results = await reranker.rerank("any query", [], top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_top_k_limits_output(self, reranker):
        """top_k limits the number of returned results."""
        candidates = [
            _make_retrieved_chunk("doc1", i, f"Content number {i}") for i in range(10)
        ]

        results = await reranker.rerank("test query", candidates, top_k=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_model_reuse_across_calls(self, reranker):
        """Model is loaded once and reused across multiple rerank() calls."""
        reranker._ensure_model()
        model_ref = reranker._model

        candidates = [_make_retrieved_chunk("doc1", 0, "test content")]
        await reranker.rerank("query 1", candidates, top_k=5)
        await reranker.rerank("query 2", candidates, top_k=5)

        assert reranker._model is model_ref
