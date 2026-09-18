"""Unit tests for RRF fusion in src/core/retrieval.py.

Tests cover:
- Overlapping results (same chunk in both BM25 and vector)
- Disjoint results (no overlap between the two rankings)
- Empty inputs (no results from either search)
- Score ordering and top_k truncation
- Abstention logic
"""


from src.core.retrieval import (
    RRF_K,
    RetrievedChunk,
    rrf_fusion,
    should_abstain,
)
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


class TestRRFFusionOverlapping:
    """Test RRF fusion when both rankings contain the same chunks."""

    def test_single_chunk_in_both_rankings(self):
        """A chunk appearing first in both rankings gets highest score."""
        chunk = _make_chunk("doc1", 0)
        bm25 = [(chunk, 0.9)]
        vector = [(chunk, 0.95)]

        results = rrf_fusion(bm25, vector, top_k=5)

        assert len(results) == 1
        # Score = 1/(60+1) + 1/(60+1) = 2/61
        expected_score = 2.0 / (RRF_K + 1)
        assert abs(results[0].score - expected_score) < 1e-10
        assert results[0].bm25_rank == 1
        assert results[0].vector_rank == 1

    def test_multiple_overlapping_chunks(self):
        """Multiple chunks in both rankings are fused and sorted correctly."""
        chunk_a = _make_chunk("doc1", 0, "chunk A")
        chunk_b = _make_chunk("doc1", 1, "chunk B")

        bm25 = [(chunk_a, 0.9), (chunk_b, 0.7)]
        vector = [(chunk_b, 0.95), (chunk_a, 0.8)]

        results = rrf_fusion(bm25, vector, top_k=5)

        assert len(results) == 2
        # chunk_a: 1/(60+1) + 1/(60+2) = 1/61 + 1/62
        # chunk_b: 1/(60+2) + 1/(60+1) = 1/62 + 1/61
        # Both have same total score, so order depends on stable sort
        scores = [r.score for r in results]
        assert scores[0] >= scores[1]  # Sorted descending

    def test_chunk_appears_only_in_bm25(self):
        """A chunk only in BM25 still gets a valid RRF score."""
        chunk = _make_chunk("doc1", 0)
        bm25 = [(chunk, 0.9)]
        vector = []

        results = rrf_fusion(bm25, vector, top_k=5)

        assert len(results) == 1
        assert results[0].bm25_rank == 1
        assert results[0].vector_rank is None
        expected_score = 1.0 / (RRF_K + 1)
        assert abs(results[0].score - expected_score) < 1e-10


class TestRRFFusionDisjoint:
    """Test RRF fusion when rankings have no overlapping chunks."""

    def test_disjoint_rankings_merged(self):
        """Disjoint results from BM25 and vector are merged into one list."""
        chunk_a = _make_chunk("doc1", 0, "BM25 only")
        chunk_b = _make_chunk("doc2", 0, "Vector only")

        bm25 = [(chunk_a, 0.9)]
        vector = [(chunk_b, 0.95)]

        results = rrf_fusion(bm25, vector, top_k=5)

        assert len(results) == 2
        # Both have same score: 1/(60+1)
        # Order: both have equal score, so original insertion order matters
        ids = {r.chunk.document_id for r in results}
        assert ids == {"doc1", "doc2"}

    def test_disjoint_scores_are_equal(self):
        """Disjoint chunks at the same rank have identical RRF scores."""
        chunk_a = _make_chunk("doc1", 0, "A")
        chunk_b = _make_chunk("doc2", 0, "B")

        bm25 = [(chunk_a, 0.9)]
        vector = [(chunk_b, 0.95)]

        results = rrf_fusion(bm25, vector, top_k=5)

        assert len(results) == 2
        assert abs(results[0].score - results[1].score) < 1e-10


class TestRRFFusionEmpty:
    """Test RRF fusion with empty inputs."""

    def test_both_empty(self):
        """Both rankings empty -> no results."""
        results = rrf_fusion([], [], top_k=5)
        assert results == []

    def test_bm25_empty_vector_has_results(self):
        """BM25 empty but vector has results -> vector results returned."""
        chunk = _make_chunk("doc1", 0)
        vector = [(chunk, 0.9)]

        results = rrf_fusion([], vector, top_k=5)

        assert len(results) == 1
        assert results[0].bm25_rank is None
        assert results[0].vector_rank == 1

    def test_vector_empty_bm25_has_results(self):
        """Vector empty but BM25 has results -> BM25 results returned."""
        chunk = _make_chunk("doc1", 0)
        bm25 = [(chunk, 0.9)]

        results = rrf_fusion(bm25, [], top_k=5)

        assert len(results) == 1
        assert results[0].bm25_rank == 1
        assert results[0].vector_rank is None


class TestRRFFusionTopK:
    """Test top_k truncation."""

    def test_top_k_limits_results(self):
        """Results are truncated to top_k."""
        chunks = [_make_chunk("doc1", i, f"content {i}") for i in range(10)]
        bm25 = [(c, 0.9 - i * 0.05) for i, c in enumerate(chunks)]
        vector = [(c, 0.95 - i * 0.05) for i, c in enumerate(chunks)]

        results = rrf_fusion(bm25, vector, top_k=3)

        assert len(results) == 3

    def test_top_k_larger_than_results(self):
        """top_k larger than available results returns all results."""
        chunk = _make_chunk("doc1", 0)
        bm25 = [(chunk, 0.9)]
        vector = [(chunk, 0.95)]

        results = rrf_fusion(bm25, vector, top_k=100)

        assert len(results) == 1


class TestRRFDeduplication:
    """Test chunk deduplication by identity."""

    def test_same_chunk_deduplicated(self):
        """Identical chunks (same doc_id, chunk_index, content_hash) are merged."""
        chunk = _make_chunk("doc1", 0, "same content", "hash_abc")
        bm25 = [(chunk, 0.9)]
        vector = [(chunk, 0.95)]

        results = rrf_fusion(bm25, vector, top_k=5)

        assert len(results) == 1
        # Score is fused from both rankings
        expected = 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 1)
        assert abs(results[0].score - expected) < 1e-10

    def test_different_chunk_index_not_deduplicated(self):
        """Chunks with different indices are treated as distinct."""
        chunk_a = _make_chunk("doc1", 0, "content", "hash_0")
        chunk_b = _make_chunk("doc1", 1, "content", "hash_1")

        bm25 = [(chunk_a, 0.9)]
        vector = [(chunk_b, 0.95)]

        results = rrf_fusion(bm25, vector, top_k=5)

        assert len(results) == 2


class TestShouldAbstain:
    """Test abstention logic."""

    def test_empty_results_abstains(self):
        """Empty results trigger abstention."""
        assert should_abstain([]) is True

    def test_results_above_threshold_no_abstain(self):
        """Results above threshold do not abstain."""
        chunk = _make_chunk()
        results = [RetrievedChunk(chunk=chunk, score=0.5, bm25_rank=1, vector_rank=1)]
        assert should_abstain(results, min_score_threshold=0.1) is False

    def test_results_below_threshold_abstains(self):
        """All results below threshold trigger abstention."""
        chunk = _make_chunk()
        results = [RetrievedChunk(chunk=chunk, score=0.01, bm25_rank=1, vector_rank=1)]
        assert should_abstain(results, min_score_threshold=0.1) is True

    def test_zero_threshold_with_results(self):
        """Zero threshold with any results does not abstain."""
        chunk = _make_chunk()
        results = [RetrievedChunk(chunk=chunk, score=0.001, bm25_rank=1, vector_rank=1)]
        assert should_abstain(results, min_score_threshold=0.0) is False

    def test_best_score_is_used(self):
        """Abstention checks the best (first) score."""
        chunk_a = _make_chunk("doc1", 0, "good")
        chunk_b = _make_chunk("doc1", 1, "bad")
        results = [
            RetrievedChunk(chunk=chunk_a, score=0.5, bm25_rank=1, vector_rank=1),
            RetrievedChunk(chunk=chunk_b, score=0.01, bm25_rank=2, vector_rank=None),
        ]
        # Best score is 0.5, threshold is 0.1 -> no abstention
        assert should_abstain(results, min_score_threshold=0.1) is False
