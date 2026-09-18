"""PostgreSQL + pgvector SearchIndex adapter.

Implements hybrid search (BM25 via tsquery + cosine vector search)
and idempotent chunk upsert with ON CONFLICT deduplication.
"""

import logging
import re

import asyncpg
from pgvector.asyncpg import register_vector

from src.config import get_settings
from src.ports.models import Chunk

logger = logging.getLogger(__name__)

# Characters that are special in tsquery — must be sanitized
_TSQUERY_SPECIAL = re.compile(r"[&|!():*<>'\\]")


def _sanitize_tsquery(query: str) -> str:
    """Sanitize user input for safe tsquery construction.

    Strips special tsquery operators and builds a safe plainto_tsquery-compatible
    string. Each word is quoted to prevent operator injection.
    """
    # Remove special tsquery characters
    cleaned = _TSQUERY_SPECIAL.sub(" ", query)
    # Split into words, filter empties
    words = [w.strip() for w in cleaned.split() if w.strip()]
    if not words:
        return ""
    # Join with spaces — plainto_tsquery will handle AND logic
    return " ".join(words)


def _row_to_chunk(row: asyncpg.Record) -> Chunk:
    """Convert a database row to a Chunk dataclass."""
    return Chunk(
        document_id=row["document_id"],
        document_title=row["document_title"],
        source_path=row["source_path"],
        section_path=row.get("section_path") or "",
        chunk_index=row["chunk_index"],
        content=row["content"],
        token_count=row.get("token_count") or 0,
        content_hash=row["content_hash"],
        page_number=row.get("page_number"),
        anchor=row.get("anchor"),
    )


class PgvectorIndex:
    """PostgreSQL + pgvector search index.

    Implements the SearchIndex port protocol.
    Uses asyncpg for async database access and pgvector for vector operations.
    """

    def __init__(self, database_url: str | None = None):
        settings = get_settings()
        # Strip the driver prefix for raw asyncpg
        self.dsn = (database_url or settings.database_url).replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Lazily initialize the connection pool with pgvector support."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=1,
                max_size=5,
                init=self._init_connection,
            )
        return self._pool

    @staticmethod
    async def _init_connection(conn: asyncpg.Connection) -> None:
        """Initialize each connection with pgvector type support."""
        await register_vector(conn)

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def upsert_chunks(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        """Insert or update chunks with their embeddings.

        Uses ON CONFLICT on the dedup unique index
        (document_id, chunk_index, content_hash) to skip duplicates.
        Re-ingesting the same document is idempotent.
        """
        if not chunks:
            return

        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunk/embedding count mismatch: {len(chunks)} chunks, "
                f"{len(embeddings)} embeddings"
            )

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            for chunk, embedding in zip(chunks, embeddings):
                await conn.execute(
                    """
                    INSERT INTO chunks (
                        document_id, document_title, source_path,
                        section_path, chunk_index, content,
                        token_count, content_hash, embedding,
                        page_number, anchor
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
                    )
                    ON CONFLICT (document_id, chunk_index, content_hash)
                    DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        document_title = EXCLUDED.document_title,
                        source_path = EXCLUDED.source_path,
                        section_path = EXCLUDED.section_path,
                        token_count = EXCLUDED.token_count,
                        page_number = EXCLUDED.page_number,
                        anchor = EXCLUDED.anchor
                    """,
                    chunk.document_id,
                    chunk.document_title,
                    chunk.source_path,
                    chunk.section_path,
                    chunk.chunk_index,
                    chunk.content,
                    chunk.token_count,
                    chunk.content_hash,
                    embedding,
                    chunk.page_number,
                    chunk.anchor,
                )

        logger.info("Upserted %d chunks with embeddings", len(chunks))

    async def delete_chunks(self, document_id: str) -> int:
        """Delete all chunks for a document. Returns count deleted."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            count = await conn.execute(
                "DELETE FROM chunks WHERE document_id = $1",
                document_id,
            )

        # asyncpg returns a status string like "DELETE 3"
        deleted = int(count.split()[-1]) if count else 0
        logger.info("Deleted %d chunks for document %s", deleted, document_id)
        return deleted

    async def bm25_search(
        self, query: str, k: int
    ) -> list[tuple[Chunk, float]]:
        """Full-text search via tsquery with ts_rank scoring.

        Uses plainto_tsquery for safe input handling (no operator injection).
        Returns (chunk, score) pairs sorted by descending relevance.
        """
        sanitized = _sanitize_tsquery(query)
        if not sanitized:
            return []

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *, ts_rank(tsv, plainto_tsquery('english', $1)) AS score
                FROM chunks
                WHERE tsv @@ plainto_tsquery('english', $1)
                ORDER BY score DESC
                LIMIT $2
                """,
                sanitized,
                k,
            )

        results = [(_row_to_chunk(row), float(row["score"])) for row in rows]
        logger.debug("BM25 search for '%s': %d results", query, len(results))
        return results

    async def vector_search(
        self, embedding: list[float], k: int
    ) -> list[tuple[Chunk, float]]:
        """Approximate nearest-neighbor search via cosine distance.

        Returns (chunk, score) pairs sorted by descending similarity.
        Score = 1 - cosine_distance (so higher = more similar).
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *, 1 - (embedding <=> $1) AS score
                FROM chunks
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> $1
                LIMIT $2
                """,
                embedding,
                k,
            )

        results = [(_row_to_chunk(row), float(row["score"])) for row in rows]
        logger.debug("Vector search: %d results", len(results))
        return results
