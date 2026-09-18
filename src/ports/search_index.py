"""SearchIndex port — hybrid search (BM25 + vector) and chunk persistence."""

from typing import Protocol

from src.ports.models import Chunk


class SearchIndex(Protocol):
    """Manages chunk storage and hybrid retrieval.

    Implementations: pgvector (PostgreSQL), dedicated vector DB, etc.
    """

    async def bm25_search(
        self, query: str, k: int
    ) -> list[tuple[Chunk, float]]:
        """Full-text search via BM25/tsquery. Returns (chunk, score) pairs."""
        ...

    async def vector_search(
        self, embedding: list[float], k: int
    ) -> list[tuple[Chunk, float]]:
        """Approximate nearest-neighbor search via cosine similarity.

        Returns (chunk, score) pairs sorted by descending similarity.
        """
        ...

    async def upsert_chunks(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        """Insert or update chunks with their embeddings.

        Must be idempotent — re-ingesting the same document should not
        create duplicates (uses content_hash for dedup).
        """
        ...

    async def delete_chunks(self, document_id: str) -> int:
        """Delete all chunks for a document. Returns count deleted."""
        ...
