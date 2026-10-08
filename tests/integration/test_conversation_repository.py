"""Integration tests for ConversationRepository with real PostgreSQL."""

import pytest
import pytest_asyncio
from src.adapters.pg_conversation_repository import PgConversationRepository


# Skip if no Docker available for testcontainers
pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def conversation_repo(pg_pool):
    """ConversationRepository backed by test PostgreSQL."""
    repo = PgConversationRepository()
    repo._pool = pg_pool
    yield repo


@pytest_asyncio.fixture
async def pg_pool():
    """Create test PostgreSQL pool with conversations table."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")

    postgres = PostgresContainer("postgres:16-alpine")
    postgres.start()

    import asyncpg

    dsn = postgres.get_connection_url().replace("postgresql://", "postgresql+asyncpg://").replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)

    # Run migrations
    async with pool.acquire() as conn:
        # 001_init.sql
        await conn.execute("""
            CREATE EXTENSION IF NOT EXISTS vector;
            CREATE TABLE chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id TEXT NOT NULL,
                document_title TEXT NOT NULL,
                source_path TEXT NOT NULL,
                section_path TEXT,
                chunk_index INT NOT NULL,
                content TEXT NOT NULL,
                token_count INT,
                content_hash TEXT NOT NULL,
                embedding vector(768),
                tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
                created_at TIMESTAMPTZ DEFAULT now()
            );
            CREATE TABLE answers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                question TEXT NOT NULL,
                answer TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                citations JSONB DEFAULT '[]',
                chunk_ids UUID[],
                vote TEXT,
                created_at TIMESTAMPTZ DEFAULT now()
            );
        """)
        # 002_documents.sql (minimal)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                title TEXT NOT NULL,
                ingested_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            );
        """)
        # 004_conversations.sql
        await conn.execute("""
            CREATE TABLE conversations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title TEXT NOT NULL DEFAULT 'New Conversation',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX idx_conversations_updated ON conversations (updated_at DESC);
            ALTER TABLE answers ADD COLUMN conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE;
            CREATE INDEX idx_answers_conversation ON answers (conversation_id, created_at);
        """)

    yield pool

    await pool.close()
    postgres.stop()


class TestConversationRepositoryIntegration:
    """Integration tests with real PostgreSQL."""

    @pytest.mark.asyncio
    async def test_create_and_get_conversation(self, conversation_repo):
        """Test creating and retrieving a conversation."""
        conv = await conversation_repo.create(title="Test Chat")
        assert conv.title == "Test Chat"
        assert conv.id is not None

        retrieved = await conversation_repo.get_by_id(conv.id)
        assert retrieved is not None
        assert retrieved.id == conv.id
        assert retrieved.title == "Test Chat"

    @pytest.mark.asyncio
    async def test_list_conversations_ordered(self, conversation_repo):
        """Test listing conversations ordered by updated_at DESC."""
        conv1 = await conversation_repo.create(title="First")
        conv2 = await conversation_repo.create(title="Second")

        # Touch conv1 to make it most recent
        await conversation_repo.touch(conv1.id)

        convs = await conversation_repo.list(limit=10, offset=0)
        assert len(convs) >= 2
        # conv1 should be first (most recently updated)
        assert convs[0].id == conv1.id

    @pytest.mark.asyncio
    async def test_delete_cascades_answers(self, conversation_repo, pg_pool):
        """Test that deleting a conversation cascades to its answers."""
        import uuid

        conv = await conversation_repo.create(title="To Delete")

        # Insert an answer linked to this conversation
        async with pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO answers (id, question, status, conversation_id)
                VALUES ($1, $2, $3, $4)
                """,
                uuid.uuid4(),
                "Test question?",
                "answered",
                conv.id,
            )

        # Delete conversation
        await conversation_repo.delete(conv.id)

        # Verify conversation is gone
        assert await conversation_repo.get_by_id(conv.id) is None

        # Verify answer is also gone (cascade)
        async with pg_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM answers WHERE conversation_id = $1",
                conv.id,
            )
            assert count == 0

    @pytest.mark.asyncio
    async def test_existing_answers_without_conversation(self, conversation_repo, pg_pool):
        """Test that existing answers without conversation_id remain valid."""
        import uuid

        # Insert answer without conversation_id
        answer_id = uuid.uuid4()
        async with pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO answers (id, question, status)
                VALUES ($1, $2, $3)
                """,
                answer_id,
                "Orphan question?",
                "answered",
            )

        # Verify it exists with NULL conversation_id
        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT conversation_id FROM answers WHERE id = $1",
                answer_id,
            )
            assert row["conversation_id"] is None
