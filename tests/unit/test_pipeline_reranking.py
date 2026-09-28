"""Unit tests for pipeline reranking integration.

Tests cover:
- Pipeline with reranker enabled (reranking after RRF, before abstention)
- Pipeline with reranker disabled (no reranking, original behavior)
- Timeout fallback (reranker too slow -> use RRF results)
- Reranker failure fallback (exception -> use RRF results)
- Logging of reranking duration
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.query_pipeline import QueryPipeline, _rerank_with_timeout
from src.core.retrieval import RetrievedChunk
from src.ports.models import Chunk


def _make_chunk(doc_id="doc1", chunk_index=0, content="test"):
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


def _make_retrieved_chunk(doc_id="doc1", chunk_index=0, score=0.5):
    return RetrievedChunk(
        chunk=_make_chunk(doc_id, chunk_index),
        score=score,
        bm25_rank=1,
        vector_rank=1,
    )


def _make_mock_pipeline(reranker=None):
    """Create a pipeline with mocked dependencies."""
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 768)

    search_index = AsyncMock()
    search_index.bm25_search = AsyncMock(return_value=[])
    search_index.vector_search = AsyncMock(return_value=[])

    generator = AsyncMock()
    citation_validator = MagicMock()
    answer_repository = AsyncMock()

    return QueryPipeline(
        embedder=embedder,
        search_index=search_index,
        generator=generator,
        citation_validator=citation_validator,
        answer_repository=answer_repository,
        reranker=reranker,
    )


class TestRerankWithTimeout:
    """Test the _rerank_with_timeout helper."""

    @pytest.mark.asyncio
    async def test_successful_reranking(self):
        """Normal reranking returns reranked results."""
        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=[
            _make_retrieved_chunk("doc1", 0, score=0.9),
        ])

        candidates = [_make_retrieved_chunk("doc1", 0, score=0.5)]
        result = await _rerank_with_timeout(reranker, "q", candidates, top_k=5, timeout_seconds=5.0)

        assert len(result) == 1
        assert result[0].score == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_timeout_returns_original(self):
        """Timeout returns original candidates truncated to top_k."""
        async def slow_rerank(query, candidates, top_k):
            await asyncio.sleep(10)
            return candidates[:top_k]

        reranker = AsyncMock()
        reranker.rerank = slow_rerank

        candidates = [_make_retrieved_chunk(f"doc1", i, score=0.5 - i * 0.1) for i in range(5)]
        result = await _rerank_with_timeout(reranker, "q", candidates, top_k=3, timeout_seconds=0.05)

        assert len(result) == 3
        # Should be original (non-reranked) candidates
        assert result[0].score == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_exception_returns_original(self):
        """Reranker exception returns original candidates truncated to top_k."""
        reranker = AsyncMock()
        reranker.rerank = AsyncMock(side_effect=RuntimeError("model crashed"))

        candidates = [_make_retrieved_chunk("doc1", i, score=0.5 - i * 0.1) for i in range(5)]
        result = await _rerank_with_timeout(reranker, "q", candidates, top_k=3, timeout_seconds=5.0)

        assert len(result) == 3
        assert result[0].score == pytest.approx(0.5)


class TestPipelineWithReranker:
    """Test QueryPipeline.retrieve() with reranker."""

    @pytest.mark.asyncio
    async def test_reranker_called_after_rrf(self):
        """When reranker is set, it is called with RRF results."""
        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=[
            _make_retrieved_chunk("doc1", 0, score=0.95),
        ])

        pipeline = _make_mock_pipeline(reranker=reranker)

        # Set up search index to return some results
        chunk = _make_chunk("doc1", 0)
        pipeline.search_index.bm25_search = AsyncMock(return_value=[(chunk, 0.8)])
        pipeline.search_index.vector_search = AsyncMock(return_value=[(chunk, 0.9)])

        with patch("src.core.query_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.reranker_top_k_before = 20
            settings.reranker_top_k_after = 5
            settings.reranker_timeout_seconds = 5.0
            settings.min_score_threshold = 0.0
            mock_settings.return_value = settings

            result = await pipeline.retrieve("test query")

        assert result.status == "streaming"
        reranker.rerank.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_reranker_skips_reranking(self):
        """When reranker is None, no reranking occurs."""
        pipeline = _make_mock_pipeline(reranker=None)

        chunk = _make_chunk("doc1", 0)
        pipeline.search_index.bm25_search = AsyncMock(return_value=[(chunk, 0.8)])
        pipeline.search_index.vector_search = AsyncMock(return_value=[(chunk, 0.9)])

        with patch("src.core.query_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.retrieval_top_k = 5
            settings.min_score_threshold = 0.0
            mock_settings.return_value = settings

            result = await pipeline.retrieve("test query")

        assert result.status == "streaming"
        # RRF top_k should be retrieval_top_k (5), not reranker_top_k_before (20)
        pipeline.search_index.bm25_search.assert_called_once_with("test query", 5)

    @pytest.mark.asyncio
    async def test_reranker_uses_top_k_before_for_rrf(self):
        """When reranker is enabled, RRF fetches reranker_top_k_before candidates."""
        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=[_make_retrieved_chunk()])

        pipeline = _make_mock_pipeline(reranker=reranker)

        chunk = _make_chunk("doc1", 0)
        pipeline.search_index.bm25_search = AsyncMock(return_value=[(chunk, 0.8)])
        pipeline.search_index.vector_search = AsyncMock(return_value=[(chunk, 0.9)])

        with patch("src.core.query_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.reranker_top_k_before = 20
            settings.reranker_top_k_after = 5
            settings.reranker_timeout_seconds = 5.0
            settings.min_score_threshold = 0.0
            mock_settings.return_value = settings

            await pipeline.retrieve("test query")

        # BM25 and vector search should use reranker_top_k_before=20
        pipeline.search_index.bm25_search.assert_called_once_with("test query", 20)
        pipeline.search_index.vector_search.assert_called_once()


class TestPipelineRerankerDisabled:
    """Test that disabled reranker preserves original behavior."""

    @pytest.mark.asyncio
    async def test_disabled_reranker_uses_retrieval_top_k(self):
        """Without reranker, pipeline uses retrieval_top_k for RRF."""
        pipeline = _make_mock_pipeline(reranker=None)

        chunks = [_make_chunk("doc1", i) for i in range(5)]
        pipeline.search_index.bm25_search = AsyncMock(
            return_value=[(c, 0.9 - i * 0.1) for i, c in enumerate(chunks)]
        )
        pipeline.search_index.vector_search = AsyncMock(
            return_value=[(c, 0.95 - i * 0.1) for i, c in enumerate(chunks)]
        )

        with patch("src.core.query_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.retrieval_top_k = 5
            settings.min_score_threshold = 0.0
            mock_settings.return_value = settings

            result = await pipeline.retrieve("test query")

        assert result.status == "streaming"
        assert len(result.retrieved_chunks) <= 5
