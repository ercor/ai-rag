"""Unit tests for the Reranker port and CrossEncoderReranker adapter.

Tests cover:
- Reranker port contract (empty list, top_k truncation, score ordering)
- CrossEncoderReranker with mocked model (lazy loading, score replacement)
- Model download failure handling
"""

from unittest.mock import MagicMock, patch

import pytest

from src.adapters.cross_encoder_reranker import CrossEncoderReranker
from src.core.retrieval import RetrievedChunk
from src.ports.models import Chunk


def _make_chunk(
    doc_id: str = "doc1",
    chunk_index: int = 0,
    content: str = "test content",
    content_hash: str | None = None,
) -> Chunk:
    """Helper to create a Chunk for testing."""
    return Chunk(
        document_id=doc_id,
        document_title="Test Doc",
        source_path="/test.md",
        section_path="",
        chunk_index=chunk_index,
        content=content,
        token_count=len(content) // 4,
        content_hash=content_hash or f"hash_{doc_id}_{chunk_index}",
    )


def _make_retrieved_chunk(
    doc_id: str = "doc1",
    chunk_index: int = 0,
    content: str = "test content",
    score: float = 0.5,
    bm25_rank: int | None = 1,
    vector_rank: int | None = 1,
) -> RetrievedChunk:
    """Helper to create a RetrievedChunk for testing."""
    return RetrievedChunk(
        chunk=_make_chunk(doc_id, chunk_index, content),
        score=score,
        bm25_rank=bm25_rank,
        vector_rank=vector_rank,
    )


class TestCrossEncoderRerankerEmptyList:
    """Empty candidate list handling."""

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self):
        """rerank() with empty candidates returns empty list without loading model."""
        reranker = CrossEncoderReranker()
        result = await reranker.rerank("query", [], top_k=5)
        assert result == []
        # Model should NOT have been loaded
        assert reranker._model is None


class TestCrossEncoderRerankerScoring:
    """Cross-encoder scoring and ordering."""

    @pytest.mark.asyncio
    async def test_candidates_sorted_by_ce_score(self):
        """Candidates are re-ordered by cross-encoder score descending."""
        reranker = CrossEncoderReranker()

        # Mock the cross-encoder model
        mock_model = MagicMock()
        # Scores: chunk0=0.1, chunk1=0.9, chunk2=0.5
        mock_model.predict.return_value = [0.1, 0.9, 0.5]
        reranker._model = mock_model

        candidates = [
            _make_retrieved_chunk("doc1", 0, "low relevance", score=0.5),
            _make_retrieved_chunk("doc1", 1, "high relevance", score=0.4),
            _make_retrieved_chunk("doc1", 2, "mid relevance", score=0.3),
        ]

        result = await reranker.rerank("query", candidates, top_k=5)

        assert len(result) == 3
        # Should be ordered by CE score: 0.9, 0.5, 0.1
        assert result[0].score == pytest.approx(0.9)
        assert result[1].score == pytest.approx(0.5)
        assert result[2].score == pytest.approx(0.1)
        # Original chunks should be preserved
        assert result[0].chunk.chunk_index == 1
        assert result[1].chunk.chunk_index == 2
        assert result[2].chunk.chunk_index == 0

    @pytest.mark.asyncio
    async def test_top_k_truncation(self):
        """Results are truncated to top_k."""
        reranker = CrossEncoderReranker()

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]
        reranker._model = mock_model

        candidates = [
            _make_retrieved_chunk("doc1", i, f"content {i}") for i in range(5)
        ]

        result = await reranker.rerank("query", candidates, top_k=2)

        assert len(result) == 2
        # Top 2 by CE score: 0.5 (chunk4), 0.4 (chunk3)
        assert result[0].score == pytest.approx(0.5)
        assert result[1].score == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_score_replaced_with_ce_score(self):
        """Original RRF score is replaced by cross-encoder score."""
        reranker = CrossEncoderReranker()

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.77]
        reranker._model = mock_model

        candidates = [
            _make_retrieved_chunk("doc1", 0, "content", score=0.0123),
        ]

        result = await reranker.rerank("query", candidates, top_k=5)

        assert len(result) == 1
        # Score should be CE score, not original RRF score
        assert result[0].score == pytest.approx(0.77)
        assert result[0].score != pytest.approx(0.0123)

    @pytest.mark.asyncio
    async def test_rank_metadata_preserved(self):
        """bm25_rank and vector_rank are preserved from original candidates."""
        reranker = CrossEncoderReranker()

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8]
        reranker._model = mock_model

        candidates = [
            RetrievedChunk(
                chunk=_make_chunk("doc1", 0, "content"),
                score=0.5,
                bm25_rank=3,
                vector_rank=7,
            ),
        ]

        result = await reranker.rerank("query", candidates, top_k=5)

        assert result[0].bm25_rank == 3
        assert result[0].vector_rank == 7


class TestCrossEncoderRerankerLazyLoading:
    """Model lazy loading behavior."""

    @pytest.mark.asyncio
    async def test_model_loaded_on_first_rerank(self):
        """Model is loaded on first rerank() call."""
        reranker = CrossEncoderReranker()
        assert reranker._model is None

        with patch(
            "sentence_transformers.CrossEncoder"
        ) as MockCE:
            mock_instance = MagicMock()
            mock_instance.predict.return_value = [0.5]
            MockCE.return_value = mock_instance

            candidates = [_make_retrieved_chunk()]
            await reranker.rerank("query", candidates, top_k=5)

            MockCE.assert_called_once_with("cross-encoder/ms-marco-MiniLM-L-6-v2")
            assert reranker._model is mock_instance

    @pytest.mark.asyncio
    async def test_model_reused_on_subsequent_calls(self):
        """Model is NOT re-loaded on subsequent rerank() calls."""
        reranker = CrossEncoderReranker()

        with patch(
            "sentence_transformers.CrossEncoder"
        ) as MockCE:
            mock_instance = MagicMock()
            mock_instance.predict.return_value = [0.5]
            MockCE.return_value = mock_instance

            candidates = [_make_retrieved_chunk()]

            # First call loads the model
            await reranker.rerank("query", candidates, top_k=5)
            assert MockCE.call_count == 1

            # Second call reuses the model
            await reranker.rerank("query", candidates, top_k=5)
            assert MockCE.call_count == 1  # Still 1

    @pytest.mark.asyncio
    async def test_custom_model_name(self):
        """Custom model name is passed to CrossEncoder constructor."""
        custom_model = "cross-encoder/ms-marco-MiniLM-L-12-v2"
        reranker = CrossEncoderReranker(model_name=custom_model)

        with patch(
            "sentence_transformers.CrossEncoder"
        ) as MockCE:
            mock_instance = MagicMock()
            mock_instance.predict.return_value = [0.5]
            MockCE.return_value = mock_instance

            candidates = [_make_retrieved_chunk()]
            await reranker.rerank("query", candidates, top_k=5)

            MockCE.assert_called_once_with(custom_model)


class TestCrossEncoderRerankerModelFailure:
    """Model download/load failure handling."""

    @pytest.mark.asyncio
    async def test_model_load_failure_raises_clear_error(self):
        """Clear error when model cannot be loaded."""
        reranker = CrossEncoderReranker()

        with patch(
            "sentence_transformers.CrossEncoder",
            side_effect=OSError("Connection refused"),
        ):
            candidates = [_make_retrieved_chunk()]

            with pytest.raises(RuntimeError, match="Failed to load cross-encoder model"):
                await reranker.rerank("query", candidates, top_k=5)

    @pytest.mark.asyncio
    async def test_model_load_failure_includes_model_name(self):
        """Error message includes the model name."""
        reranker = CrossEncoderReranker(model_name="my/custom-model")

        with patch(
            "sentence_transformers.CrossEncoder",
            side_effect=OSError("not found"),
        ):
            candidates = [_make_retrieved_chunk()]

            with pytest.raises(RuntimeError, match="my/custom-model"):
                await reranker.rerank("query", candidates, top_k=5)


class TestCrossEncoderRerankerPredictCall:
    """Verify the predict() call receives correct pairs."""

    @pytest.mark.asyncio
    async def test_predict_receives_query_content_pairs(self):
        """predict() is called with (query, chunk_content) pairs."""
        reranker = CrossEncoderReranker()

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5, 0.3]
        reranker._model = mock_model

        candidates = [
            _make_retrieved_chunk("doc1", 0, "first chunk content"),
            _make_retrieved_chunk("doc1", 1, "second chunk content"),
        ]

        await reranker.rerank("my query", candidates, top_k=5)

        mock_model.predict.assert_called_once_with([
            ("my query", "first chunk content"),
            ("my query", "second chunk content"),
        ])
