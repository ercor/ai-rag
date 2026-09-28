"""Reranker port — re-scores retrieval candidates by cross-encoder relevance.

Adapter-agnostic Protocol. Concrete implementations live in src/adapters/.
"""

from typing import Protocol

from src.core.retrieval import RetrievedChunk


class Reranker(Protocol):
    """Re-score and re-order candidate chunks by relevance to a query.

    Implementations: CrossEncoderReranker (sentence-transformers), etc.
    """

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """Return at most *top_k* candidates sorted by descending relevance.

        The returned list MUST contain at most *top_k* elements.
        An empty *candidates* list MUST return an empty list.
        """
        ...
