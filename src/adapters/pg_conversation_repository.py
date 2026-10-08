"""PostgreSQL-based ConversationRepository adapter.

Persists conversations and their linked answers via asyncpg.
"""

from __future__ import annotations

import logging

import asyncpg

from src.config import get_settings
from src.ports.conversation_repository import Conversation, ConversationAnswer

logger = logging.getLogger(__name__)


class PgConversationRepository:
    """Stores and retrieves conversations in PostgreSQL.

    Implements the ConversationRepository port protocol.
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

    async def create(self, title: str | None = None) -> Conversation:
        """Create a new conversation.

        Args:
            title: Optional title. If None, defaults to "New Conversation".

        Returns:
            The newly created conversation with its UUID and timestamps.
        """
        pool = await self._get_pool()
        effective_title = title if title else "New Conversation"

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO conversations (title)
                VALUES ($1)
                RETURNING id, title, created_at, updated_at
                """,
                effective_title,
            )

        return Conversation(
            id=str(row["id"]),
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_by_id(self, conversation_id: str) -> Conversation | None:
        """Retrieve a conversation by its ID.

        Args:
            conversation_id: The UUID of the conversation.

        Returns:
            The conversation if found, None otherwise.
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = $1
                """,
                conversation_id,
            )

        if row is None:
            return None

        return Conversation(
            id=str(row["id"]),
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def list(
        self, limit: int = 20, offset: int = 0
    ) -> list[Conversation]:
        """List conversations ordered by updated_at descending.

        Args:
            limit: Maximum number of conversations to return.
            offset: Number of conversations to skip.

        Returns:
            List of conversations, most recently updated first.
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

        return [
            Conversation(
                id=str(row["id"]),
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def delete(self, conversation_id: str) -> None:
        """Delete a conversation and all its linked answers.

        Cascade deletes via FK constraint.

        Args:
            conversation_id: The UUID of the conversation to delete.
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM conversations WHERE id = $1",
                conversation_id,
            )

    async def get_answers(self, conversation_id: str) -> list[ConversationAnswer]:
        """Retrieve all answers for a conversation, ordered by created_at ascending.

        Args:
            conversation_id: The UUID of the conversation.

        Returns:
            List of answers in chronological order.
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, question, answer, status, citations, created_at
                FROM answers
                WHERE conversation_id = $1
                ORDER BY created_at ASC
                """,
                conversation_id,
            )

        return [
            ConversationAnswer(
                id=str(row["id"]),
                question=row["question"],
                answer=row["answer"],
                status=row["status"],
                citations=row["citations"] or [],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def update_title(self, conversation_id: str, title: str) -> None:
        """Update the title of a conversation.

        Args:
            conversation_id: The UUID of the conversation.
            title: The new title.
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE conversations
                SET title = $1, updated_at = now()
                WHERE id = $2
                """,
                title,
                conversation_id,
            )

    async def touch(self, conversation_id: str) -> None:
        """Update the updated_at timestamp to now().

        Used to keep conversations sorted by most recent activity.

        Args:
            conversation_id: The UUID of the conversation to touch.
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE conversations
                SET updated_at = now()
                WHERE id = $1
                """,
                conversation_id,
            )
