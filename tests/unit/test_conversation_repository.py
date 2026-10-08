"""Unit tests for ConversationRepository port and PgConversationRepository adapter."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from src.ports.conversation_repository import Conversation, ConversationAnswer
from src.adapters.pg_conversation_repository import PgConversationRepository


@pytest.fixture
def mock_pool():
    """Mock asyncpg pool."""
    pool = MagicMock()
    conn = AsyncMock()
    # Make acquire() return an async context manager
    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None
    pool.acquire.return_value = cm
    return pool, conn


@pytest.fixture
def repo(mock_pool):
    """PgConversationRepository with mocked pool."""
    pool, _ = mock_pool
    with patch("src.adapters.pg_conversation_repository.get_settings") as mock_settings:
        mock_settings.return_value.database_url = "postgresql://test"
        r = PgConversationRepository()
        r._pool = pool
        return r


class TestConversationRepository:
    """Tests for ConversationRepository port."""

    def test_conversation_dataclass(self):
        """Test Conversation dataclass creation."""
        conv = Conversation(
            id="conv-123",
            title="Test Conversation",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            updated_at=datetime(2024, 1, 1, 12, 30, 0),
        )
        assert conv.id == "conv-123"
        assert conv.title == "Test Conversation"

    def test_conversation_answer_dataclass(self):
        """Test ConversationAnswer dataclass creation."""
        answer = ConversationAnswer(
            id="answer-456",
            question="What is RAG?",
            answer="RAG is Retrieval-Augmented Generation",
            status="answered",
            citations=[{"index": 1, "document_id": "doc-1"}],
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        assert answer.id == "answer-456"
        assert answer.question == "What is RAG?"
        assert len(answer.citations) == 1


class TestPgConversationRepository:
    """Tests for PgConversationRepository adapter."""

    @pytest.mark.asyncio
    async def test_create_conversation(self, repo, mock_pool):
        """Test creating a conversation."""
        pool, conn = mock_pool
        conn.fetchrow.return_value = {
            "id": "conv-123",
            "title": "Test Conversation",
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
            "updated_at": datetime(2024, 1, 1, 12, 0, 0),
        }

        conv = await repo.create(title="Test Conversation")

        assert conv.id == "conv-123"
        assert conv.title == "Test Conversation"
        conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_conversation_default_title(self, repo, mock_pool):
        """Test creating a conversation with default title."""
        pool, conn = mock_pool
        conn.fetchrow.return_value = {
            "id": "conv-123",
            "title": "New Conversation",
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
            "updated_at": datetime(2024, 1, 1, 12, 0, 0),
        }

        conv = await repo.create()

        assert conv.title == "New Conversation"

    @pytest.mark.asyncio
    async def test_get_by_id(self, repo, mock_pool):
        """Test getting a conversation by ID."""
        pool, conn = mock_pool
        conn.fetchrow.return_value = {
            "id": "conv-123",
            "title": "Test Conversation",
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
            "updated_at": datetime(2024, 1, 1, 12, 30, 0),
        }

        conv = await repo.get_by_id("conv-123")

        assert conv is not None
        assert conv.id == "conv-123"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo, mock_pool):
        """Test getting a non-existent conversation."""
        pool, conn = mock_pool
        conn.fetchrow.return_value = None

        conv = await repo.get_by_id("non-existent")

        assert conv is None

    @pytest.mark.asyncio
    async def test_list_conversations(self, repo, mock_pool):
        """Test listing conversations."""
        pool, conn = mock_pool
        conn.fetch.return_value = [
            {
                "id": "conv-1",
                "title": "First",
                "created_at": datetime(2024, 1, 1),
                "updated_at": datetime(2024, 1, 2),
            },
            {
                "id": "conv-2",
                "title": "Second",
                "created_at": datetime(2024, 1, 1),
                "updated_at": datetime(2024, 1, 1),
            },
        ]

        convs = await repo.list(limit=20, offset=0)

        assert len(convs) == 2
        assert convs[0].id == "conv-1"
        assert convs[1].id == "conv-2"

    @pytest.mark.asyncio
    async def test_delete_conversation(self, repo, mock_pool):
        """Test deleting a conversation."""
        pool, conn = mock_pool
        conn.execute.return_value = "DELETE 1"

        await repo.delete("conv-123")

        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_answers(self, repo, mock_pool):
        """Test getting answers for a conversation."""
        pool, conn = mock_pool
        conn.fetch.return_value = [
            {
                "id": "answer-1",
                "question": "Q1",
                "answer": "A1",
                "status": "answered",
                "citations": [],
                "created_at": datetime(2024, 1, 1, 12, 0, 0),
            },
            {
                "id": "answer-2",
                "question": "Q2",
                "answer": "A2",
                "status": "answered",
                "citations": [],
                "created_at": datetime(2024, 1, 1, 12, 5, 0),
            },
        ]

        answers = await repo.get_answers("conv-123")

        assert len(answers) == 2
        assert answers[0].id == "answer-1"
        assert answers[1].id == "answer-2"

    @pytest.mark.asyncio
    async def test_update_title(self, repo, mock_pool):
        """Test updating conversation title."""
        pool, conn = mock_pool
        conn.execute.return_value = "UPDATE 1"

        await repo.update_title("conv-123", "New Title")

        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_touch(self, repo, mock_pool):
        """Test touching conversation to update timestamp."""
        pool, conn = mock_pool
        conn.execute.return_value = "UPDATE 1"

        await repo.touch("conv-123")

        conn.execute.assert_called_once()
