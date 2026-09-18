"""Retrieval core — RRF (Reciprocal Rank Fusion) over hybrid search.

Fuses BM25 and vector search results using RRF with k=60,
deduplicates by chunk identity, and applies abstention logic
when no chunks meet the minimum score threshold.
"""

import logging
from dataclasses import dataclass

from src.ports.models import Chunk

logger = logging.getLogger(__name__)

# RRF constant — standard value from Cormack et al.
RRF_K = 60


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk with its fused RRF score and source ranking info."""

    chunk: Chunk
    score: float
    bm25_rank: int | None  # None if not found in BM25 results
    vector_rank: int | None  # None if not found in vector results


def rrf_fusion(
    bm25_results: list[tuple[Chunk, float]],
    vector_results: list[tuple[Chunk, float]],
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Fuse BM25 and vector search results using Reciprocal Rank Fusion.

    RRF score = sum(1 / (k + rank_i)) for each ranking list where
    the chunk appears. k=60 is the standard constant.

    Chunks are deduplicated by (document_id, chunk_index, content_hash).
    Results are sorted by descending RRF score and truncated to top_k.

    Args:
        bm25_results: (chunk, score) pairs from BM25/tsquery search,
                      sorted by descending relevance.
        vector_results: (chunk, score) pairs from vector cosine search,
                        sorted by descending similarity.
        top_k: Maximum number of fused results to return.

    Returns:
        List of RetrievedChunk sorted by descending RRF score.
    """
    # Build chunk identity -> accumulated RRF score + rank info
    fused: dict[str, dict] = {}

    # Process BM25 rankings
    for rank, (chunk, _score) in enumerate(bm25_results, start=1):
        key = _chunk_key(chunk)
        if key not in fused:
            fused[key] = {
                "chunk": chunk,
                "score": 0.0,
                "bm25_rank": None,
                "vector_rank": None,
            }
        fused[key]["score"] += 1.0 / (RRF_K + rank)
        fused[key]["bm25_rank"] = rank

    # Process vector rankings
    for rank, (chunk, _score) in enumerate(vector_results, start=1):
        key = _chunk_key(chunk)
        if key not in fused:
            fused[key] = {
                "chunk": chunk,
                "score": 0.0,
                "bm25_rank": None,
                "vector_rank": None,
            }
        fused[key]["score"] += 1.0 / (RRF_K + rank)
        fused[key]["vector_rank"] = rank

    # Convert to sorted list
    results = [
        RetrievedChunk(
            chunk=entry["chunk"],
            score=entry["score"],
            bm25_rank=entry["bm25_rank"],
            vector_rank=entry["vector_rank"],
        )
        for entry in fused.values()
    ]

    # Sort by descending RRF score
    results.sort(key=lambda r: r.score, reverse=True)

    # Truncate to top_k
    results = results[:top_k]

    logger.debug(
        "RRF fusion: %d BM25 + %d vector -> %d fused (top_k=%d)",
        len(bm25_results),
        len(vector_results),
        len(results),
        top_k,
    )

    return results


def should_abstain(
    results: list[RetrievedChunk],
    min_score_threshold: float = 0.0,
) -> bool:
    """Determine whether the retriever should abstain from answering.

    Abstention triggers when:
    - No chunks were retrieved (empty results), OR
    - All chunks have RRF scores below the minimum threshold.

    Args:
        results: Fused retrieval results from rrf_fusion().
        min_score_threshold: Minimum RRF score required to proceed.

    Returns:
        True if the system should abstain (no answer), False otherwise.
    """
    if not results:
        logger.info("Abstention: no chunks retrieved")
        return True

    best_score = results[0].score
    if best_score < min_score_threshold:
        logger.info(
            "Abstention: best RRF score %.6f below threshold %.6f",
            best_score,
            min_score_threshold,
        )
        return True

    return False


def _chunk_key(chunk: Chunk) -> str:
    """Generate a deduplication key for a chunk.

    Uses (document_id, chunk_index, content_hash) as the identity tuple,
    matching the database unique constraint.
    """
    return f"{chunk.document_id}:{chunk.chunk_index}:{chunk.content_hash}"
