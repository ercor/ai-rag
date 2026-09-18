"""AnswerRepository port — persists answer records to the database."""

from typing import Protocol


class AnswerRepository(Protocol):
    """Stores and updates answer records in the database.

    Implementations: asyncpg (PostgreSQL), SQLite, etc.
    """

    async def save(
        self,
        answer_id: str,
        question: str,
        answer: str,
        status: str,
        citations: list,
        chunk_ids: list,
    ) -> None:
        """Persist a new answer record or update an existing one.

        `status` is one of: pending, streaming, answered,
        insufficient_evidence, failed.
        """
        ...

    async def update_vote(self, answer_id: str, vote: str) -> None:
        """Record user feedback (up/down) for an answer."""
        ...
