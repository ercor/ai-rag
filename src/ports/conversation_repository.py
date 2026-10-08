"""ConversationRepository port — adapter-agnostic interface for conversation persistence.

Defines the contract for storing and retrieving conversations and their answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class Conversation:
    """A conversation grouping multiple Q&A exchanges."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass
class ConversationAnswer:
    """An answer linked to a conversation."""

    id: str
    question: str
    answer: str | None
    status: str
    citations: list[dict]
    created_at: datetime


class ConversationRepository(Protocol):
    """Port for conversation persistence operations.

    Adapter-agnostic — no SQL or database-specific types in the interface.
    """

    async def create(self, title: str | None = None) -> Conversation:
        """Create a new conversation.

        Args:
            title: Optional title. If None, defaults to "New Conversation".

        Returns:
            The newly created conversation with its UUID and timestamps.
        """
        ...

    async def get_by_id(self, conversation_id: str) -> Conversation | None:
        """Retrieve a conversation by its ID.

        Args:
            conversation_id: The UUID of the conversation.

        Returns:
            The conversation if found, None otherwise.
        """
        ...

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
        ...

    async def delete(self, conversation_id: str) -> None:
        """Delete a conversation and all its linked answers.

        Cascade deletes via FK constraint.

        Args:
            conversation_id: The UUID of the conversation to delete.
        """
        ...

    async def get_answers(self, conversation_id: str) -> list[ConversationAnswer]:
        """Retrieve all answers for a conversation, ordered by created_at ascending.

        Args:
            conversation_id: The UUID of the conversation.

        Returns:
            List of answers in chronological order.
        """
        ...

    async def update_title(self, conversation_id: str, title: str) -> None:
        """Update the title of a conversation.

        Args:
            conversation_id: The UUID of the conversation.
            title: The new title.
        """
        ...

    async def touch(self, conversation_id: str) -> None:
        """Update the updated_at timestamp to now().

        Used to keep conversations sorted by most recent activity.

        Args:
            conversation_id: The UUID of the conversation to touch.
        """
        ...
