"""Unit tests for cross-variant RRF merge (rrf_fusion_multi).

Tests cover:
- Merge of 3 variant results with overlapping chunks produces deduplicated list
- Chunks in multiple variants have higher accumulated scores
- Single variant merge is identical to single-query RRF
- All variants return identical results preserves ranking
- Empty input handling
"""

import pytest

from src.core.retrieval import RRF_K, RetrievedChunk, rrf_fusion_multi
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


def _make_retrieved_chunk(
    doc_id="doc1",
    chunk_index=0,
    score=0.5,
    bm25_rank=1,
    vector_rank=1,
):
    return RetrievedChunk(
        chunk=_make_chunk(doc_id, chunk_index),
        score=score,
        bm25_rank=bm25_rank,
        vector_rank=vector_rank,
    )


class TestRRFFusionMultiDeduplication:
    """Test deduplication across variant result lists."""

    def test_overlapping_chunks_deduplicated(self):
        """Chunks appearing in multiple variants appear only once in output."""
        # V1=[A,B,C], V2=[B,C,D], V3=[A,D,E]
        a = _make_retrieved_chunk("doc1", 0)
        b = _make_retrieved_chunk("doc1", 1)
        c = _make_retrieved_chunk("doc1", 2)
        d = _make_retrieved_chunk("doc1", 3)
        e = _make_retrieved_chunk("doc1", 4)

        v1 = [a, b, c]
        v2 = [b, c, d]
        v3 = [a, d, e]

        result = rrf_fusion_multi([v1, v2, v3], top_k=10)

        # Should have exactly 5 unique chunks
        assert len(result) == 5
        chunk_keys = {
            f"{rc.chunk.document_id}:{rc.chunk.chunk_index}"
            for rc in result
        }
        assert chunk_keys == {"doc1:0", "doc1:1", "doc1:2", "doc1:3", "doc1:4"}

    def test_empty_variant_results(self):
        """Empty input returns empty output."""
        result = rrf_fusion_multi([], top_k=5)
        assert result == []

    def test_empty_inner_lists(self):
        """Variant lists that are empty are handled gracefully."""
        result = rrf_fusion_multi([[], [], []], top_k=5)
        assert result == []


class TestRRFFusionMultiScoreAccumulation:
    """Test that chunks in multiple variants get higher scores."""

    def test_chunks_in_multiple_variants_score_higher(self):
        """A chunk appearing in 3 variants scores higher than one in 1."""
        # B appears in all 3 variants at rank 1
        b = _make_retrieved_chunk("doc1", 1)
        # A appears in only 1 variant at rank 1
        a = _make_retrieved_chunk("doc1", 0)

        v1 = [b, a]
        v2 = [b]
        v3 = [b]

        result = rrf_fusion_multi([v1, v2, v3], top_k=5)

        # B should be first (highest accumulated score)
        assert result[0].chunk.chunk_index == 1
        # A should be second
        assert result[1].chunk.chunk_index == 0
        # B's score should be higher than A's
        assert result[0].score > result[1].score

    def test_score_accumulation_math(self):
        """Verify the exact RRF score accumulation."""
        a = _make_retrieved_chunk("doc1", 0)

        # A appears at rank 1 in 2 variants
        v1 = [a]
        v2 = [a]

        result = rrf_fusion_multi([v1, v2], top_k=5)

        expected_score = 2.0 / (RRF_K + 1)
        assert result[0].score == pytest.approx(expected_score)

    def test_rank_position_affects_accumulated_score(self):
        """A chunk at rank 1 in 1 variant vs rank 2 in 2 variants."""
        a = _make_retrieved_chunk("doc1", 0)
        b = _make_retrieved_chunk("doc1", 1)

        # A at rank 1 in 1 variant: score = 1/(60+1)
        # B at rank 2 in 2 variants: score = 2/(60+2)
        v1 = [a, b]
        v2 = [b]

        result = rrf_fusion_multi([v1, v2], top_k=5)

        a_score = 1.0 / (RRF_K + 1)
        b_score = 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 2)

        # B should score higher (appears in 2 lists)
        b_result = [r for r in result if r.chunk.chunk_index == 1][0]
        a_result = [r for r in result if r.chunk.chunk_index == 0][0]
        assert b_result.score == pytest.approx(b_score)
        assert a_result.score == pytest.approx(a_score)
        assert b_result.score > a_result.score


class TestRRFFusionMultiSingleVariant:
    """Test that single-variant merge is equivalent to single-query RRF."""

    def test_single_variant_produces_rank_based_scores(self):
        """Single variant: each chunk gets 1/(k+rank)."""
        a = _make_retrieved_chunk("doc1", 0)
        b = _make_retrieved_chunk("doc1", 1)
        c = _make_retrieved_chunk("doc1", 2)

        result = rrf_fusion_multi([[a, b, c]], top_k=5)

        assert len(result) == 3
        # Rank 1 should have highest score
        assert result[0].score > result[1].score > result[2].score
        assert result[0].score == pytest.approx(1.0 / (RRF_K + 1))
        assert result[1].score == pytest.approx(1.0 / (RRF_K + 2))
        assert result[2].score == pytest.approx(1.0 / (RRF_K + 3))


class TestRRFFusionMultiIdenticalVariants:
    """Test behavior when all variants return identical results."""

    def test_identical_results_preserve_ranking(self):
        """When all variants return same chunks in same order, ranking preserved."""
        a = _make_retrieved_chunk("doc1", 0)
        b = _make_retrieved_chunk("doc1", 1)
        c = _make_retrieved_chunk("doc1", 2)

        v1 = [a, b, c]
        v2 = [a, b, c]
        v3 = [a, b, c]

        result = rrf_fusion_multi([v1, v2, v3], top_k=5)

        # Same order, just higher scores
        assert result[0].chunk.chunk_index == 0
        assert result[1].chunk.chunk_index == 1
        assert result[2].chunk.chunk_index == 2

        # Each score should be 3x the single-variant score
        assert result[0].score == pytest.approx(3.0 / (RRF_K + 1))
        assert result[1].score == pytest.approx(3.0 / (RRF_K + 2))
        assert result[2].score == pytest.approx(3.0 / (RRF_K + 3))


class TestRRFFusionMultiTopK:
    """Test top_k truncation."""

    def test_top_k_truncation(self):
        """Results are truncated to top_k."""
        chunks = [_make_retrieved_chunk("doc1", i) for i in range(10)]

        result = rrf_fusion_multi([chunks], top_k=3)

        assert len(result) == 3

    def test_top_k_across_variants(self):
        """top_k applies to the merged result, not per-variant."""
        a = _make_retrieved_chunk("doc1", 0)
        b = _make_retrieved_chunk("doc1", 1)
        c = _make_retrieved_chunk("doc1", 2)
        d = _make_retrieved_chunk("doc1", 3)

        v1 = [a, b]
        v2 = [c, d]

        result = rrf_fusion_multi([v1, v2], top_k=2)

        assert len(result) == 2
