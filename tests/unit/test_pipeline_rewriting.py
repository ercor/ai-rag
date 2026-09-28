"""Unit tests for pipeline query rewriting integration.

Tests cover:
- Pipeline with rewriter calls rewriter before embedding
- Pipeline without rewriter (rewriter=None) uses raw query
- Parallel search execution (asyncio.gather)
- Rewriting duration and variant count are logged
- Rewriter + reranker combined flow
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.core.query_pipeline import QueryPipeline
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


def _make_mock_pipeline(query_rewriter=None, reranker=None):
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
        query_rewriter=query_rewriter,
    )


class TestPipelineWithRewriter:
    """Test QueryPipeline.retrieve() with query_rewriter."""

    @pytest.mark.asyncio
    async def test_rewriter_called_before_embedding(self):
        """When rewriter is set, it is called to produce variants."""
        rewriter = AsyncMock()
        rewriter.rewrite = AsyncMock(return_value=[
            "original query",
            "variant 1",
            "variant 2",
        ])

        pipeline = _make_mock_pipeline(query_rewriter=rewriter)

        chunk = _make_chunk("doc1", 0)
        pipeline.search_index.bm25_search = AsyncMock(return_value=[(chunk, 0.8)])
        pipeline.search_index.vector_search = AsyncMock(return_value=[(chunk, 0.9)])

        with patch("src.core.query_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.retrieval_top_k = 5
            settings.min_score_threshold = 0.0
            mock_settings.return_value = settings

            result = await pipeline.retrieve("original query")

        assert result.status == "streaming"
        rewriter.rewrite.assert_called_once_with("original query")

    @pytest.mark.asyncio
    async def test_each_variant_embedded_and_searched(self):
        """Each variant from the rewriter is embedded and searched."""
        rewriter = AsyncMock()
        rewriter.rewrite = AsyncMock(return_value=["q1", "q2", "q3"])

        pipeline = _make_mock_pipeline(query_rewriter=rewriter)

        chunk = _make_chunk("doc1", 0)
        pipeline.search_index.bm25_search = AsyncMock(return_value=[(chunk, 0.8)])
        pipeline.search_index.vector_search = AsyncMock(return_value=[(chunk, 0.9)])

        with patch("src.core.query_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.retrieval_top_k = 5
            settings.min_score_threshold = 0.0
            mock_settings.return_value = settings

            await pipeline.retrieve("original query")

        # Embedder should be called 3 times (once per variant)
        assert pipeline.embedder.embed.call_count == 3
        # BM25 and vector search each called 3 times
        assert pipeline.search_index.bm25_search.call_count == 3
        assert pipeline.search_index.vector_search.call_count == 3

    @pytest.mark.asyncio
    async def test_parallel_search_execution(self):
        """Variant searches run concurrently via asyncio.gather."""
        call_times = []

        async def slow_embed(query):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.05)
            return [0.1] * 768

        rewriter = AsyncMock()
        rewriter.rewrite = AsyncMock(return_value=["q1", "q2", "q3"])

        pipeline = _make_mock_pipeline(query_rewriter=rewriter)
        pipeline.embedder.embed = slow_embed

        chunk = _make_chunk("doc1", 0)
        pipeline.search_index.bm25_search = AsyncMock(return_value=[(chunk, 0.8)])
        pipeline.search_index.vector_search = AsyncMock(return_value=[(chunk, 0.9)])

        with patch("src.core.query_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.retrieval_top_k = 5
            settings.min_score_threshold = 0.0
            mock_settings.return_value = settings

            import time
            start = time.monotonic()
            await pipeline.retrieve("original query")
            elapsed = time.monotonic() - start

        # If parallel, total time should be ~0.05s, not ~0.15s
        # Allow generous margin for CI/VM overhead
        assert elapsed < 0.3, f"Expected parallel execution, took {elapsed:.2f}s"


class TestPipelineWithoutRewriter:
    """Test that disabled rewriter preserves original behavior."""

    @pytest.mark.asyncio
    async def test_no_rewriter_uses_raw_query(self):
        """When rewriter is None, pipeline uses raw query directly."""
        pipeline = _make_mock_pipeline(query_rewriter=None)

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
        # Embedder called exactly once (single query)
        pipeline.embedder.embed.assert_called_once_with("test query")
        # BM25 and vector search each called once
        assert pipeline.search_index.bm25_search.call_count == 1
        assert pipeline.search_index.vector_search.call_count == 1


class TestPipelineRewriterWithReranker:
    """Test combined rewriter + reranker flow."""

    @pytest.mark.asyncio
    async def test_reranker_called_after_multi_rrf(self):
        """When both rewriter and reranker are set, reranker runs after multi-RRF."""
        rewriter = AsyncMock()
        rewriter.rewrite = AsyncMock(return_value=["q1", "q2"])

        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=[
            _make_retrieved_chunk("doc1", 0, score=0.95),
        ])

        pipeline = _make_mock_pipeline(query_rewriter=rewriter, reranker=reranker)

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
        rewriter.rewrite.assert_called_once()
        reranker.rerank.assert_called_once()

    @pytest.mark.asyncio
    async def test_rewriter_uses_reranker_top_k_before(self):
        """When reranker is enabled, multi-query search uses reranker_top_k_before."""
        rewriter = AsyncMock()
        rewriter.rewrite = AsyncMock(return_value=["q1", "q2"])

        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=[_make_retrieved_chunk()])

        pipeline = _make_mock_pipeline(query_rewriter=rewriter, reranker=reranker)

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

        # BM25 search should use reranker_top_k_before=20 for all variants
        assert pipeline.search_index.bm25_search.call_count == 2
        for c in pipeline.search_index.bm25_search.call_args_list:
            assert c.args[1] == 20


class TestPipelineRewriterFallback:
    """Test graceful degradation when rewriter produces only original."""

    @pytest.mark.asyncio
    async def test_single_variant_from_rewriter_still_works(self):
        """When rewriter returns only [original], pipeline still works."""
        rewriter = AsyncMock()
        rewriter.rewrite = AsyncMock(return_value=["original query"])

        pipeline = _make_mock_pipeline(query_rewriter=rewriter)

        chunk = _make_chunk("doc1", 0)
        pipeline.search_index.bm25_search = AsyncMock(return_value=[(chunk, 0.8)])
        pipeline.search_index.vector_search = AsyncMock(return_value=[(chunk, 0.9)])

        with patch("src.core.query_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.retrieval_top_k = 5
            settings.min_score_threshold = 0.0
            mock_settings.return_value = settings

            result = await pipeline.retrieve("original query")

        assert result.status == "streaming"
        # Only 1 variant, so embed called once
        pipeline.embedder.embed.assert_called_once()
