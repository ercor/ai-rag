"""PostgreSQL-based AnswerRepository adapter.

Persists answer records and user feedback via asyncpg.
"""

import json
import logging
import uuid

import asyncpg

from src.config import get_settings

logger = logging.getLogger(__name__)


class PgAnswerRepository:
    """Stores and updates answer records in PostgreSQL.

    Implements the AnswerRepository port protocol.
    Uses asyncpg for async database access.
    """

    def __init__(self, database_url: str | None = None):
        settings = get_settings()
        # Strip the driver prefix for raw asyncpg
        self.dsn = (database_url or settings.database_url).replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Lazily initialize the connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=1,
                max_size=5,
            )
        return self._pool

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def save(
        self,
        answer_id: str,
        question: str,
        answer: str | None,
        status: str,
        citations: list,
        chunk_ids: list[str],
        conversation_id: str | None = None,
    ) -> None:
        """Persist a new answer record or update an existing one.

        Uses INSERT ... ON CONFLICT to handle re-saves gracefully.

        Args:
            answer_id: UUID string for the answer record.
            question: The user's question text.
            answer: The generated answer text (None if abstained).
            status: One of pending, streaming, answered,
                    insufficient_evidence, failed.
            citations: List of citation dicts with chunk metadata.
            chunk_ids: List of UUID strings for the source chunks.
            conversation_id: Optional UUID string linking to a conversation.
        """
        pool = await self._get_pool()

        # Convert chunk_ids to UUID objects for asyncpg
        uuid_chunk_ids = []
        for cid in chunk_ids:
            try:
                uuid_chunk_ids.append(uuid.UUID(str(cid)))
            except (ValueError, AttributeError):
                logger.warning("Invalid chunk_id UUID: %s", cid)

        conv_uuid = uuid.UUID(conversation_id) if conversation_id else None

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO answers (id, question, answer, status, citations, chunk_ids, conversation_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    answer = EXCLUDED.answer,
                    status = EXCLUDED.status,
                    citations = EXCLUDED.citations,
                    chunk_ids = EXCLUDED.chunk_ids
                """,
                uuid.UUID(answer_id),
                question,
                answer,
                status,
                json.dumps(citations),
                uuid_chunk_ids if uuid_chunk_ids else None,
                conv_uuid,
            )

        logger.debug(
            "Saved answer %s: status=%s, citations=%d, chunks=%d",
            answer_id,
            status,
            len(citations),
            len(chunk_ids),
        )

    async def update_vote(self, answer_id: str, vote: str) -> None:
        """Record user feedback (up/down) for an answer.

        Args:
            answer_id: UUID string for the answer record.
            vote: "up" or "down".
        """
        if vote not in ("up", "down"):
            raise ValueError(f"Invalid vote value: {vote!r}. Must be 'up' or 'down'.")

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE answers SET vote = $1 WHERE id = $2
                """,
                vote,
                uuid.UUID(answer_id),
            )

        logger.info("Updated vote for answer %s: %s", answer_id, vote)

    async def get_answer(self, answer_id: str) -> dict | None:
        """Retrieve an answer record by ID.

        Returns a dict with the answer fields, or None if not found.
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, question, answer, status, citations, chunk_ids, vote, created_at
                FROM answers
                WHERE id = $1
                """,
                uuid.UUID(answer_id),
            )

        if row is None:
            return None

        return {
            "id": str(row["id"]),
            "question": row["question"],
            "answer": row["answer"],
            "status": row["status"],
            "citations": row["citations"] if isinstance(row["citations"], list) else [],
            "chunk_ids": [str(cid) for cid in row["chunk_ids"]] if row["chunk_ids"] else [],
            "vote": row["vote"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    async def update_status(
        self,
        answer_id: str,
        status: str,
        answer: str | None = None,
        citations: list | None = None,
    ) -> None:
        """Update the status (and optionally answer/citations) of an answer record.

        Used to transition from 'streaming' to 'answered' after generation completes.
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            if answer is not None and citations is not None:
                await conn.execute(
                    """
                    UPDATE answers
                    SET status = $1, answer = $2, citations = $3
                    WHERE id = $4
                    """,
                    status,
                    answer,
                    json.dumps(citations),
                    uuid.UUID(answer_id),
                )
            else:
                await conn.execute(
                    """
                    UPDATE answers SET status = $1 WHERE id = $2
                    """,
                    status,
                    uuid.UUID(answer_id),
                )

        logger.debug("Updated answer %s: status=%s", answer_id, status)
