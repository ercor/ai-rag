"""Shared fixtures for integration tests.

Provides a real PostgreSQL+pgvector instance via testcontainers,
applies the migration schema, and tears down after the test session.
"""

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

# Ensure testcontainers doesn't try to use Docker-in-Docker workarounds
os.environ.setdefault("DOCKER_HOST", "")

MIGRATION_SQL = Path(__file__).parent.parent.parent / "migrations" / "001_init.sql"
MIGRATION_002_SQL = Path(__file__).parent.parent.parent / "migrations" / "002_documents.sql"
MIGRATION_003_SQL = Path(__file__).parent.parent.parent / "migrations" / "003_chunk_metadata.sql"


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def pg_container():
    """Start a PostgreSQL+pgvector container for the test session.

    Uses the pgvector/pgvector:pg16 image which has the vector extension
    pre-installed. The container is shared across all integration tests
    in the session for speed.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed — pip install testcontainers[postgres]")

    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="test_rag",
    )
    container.start()
    yield container
    container.stop()


@pytest_asyncio.fixture(scope="session")
async def dsn(pg_container):
    """Return a raw asyncpg-compatible DSN (postgresql://... without driver prefix)."""
    url = pg_container.get_connection_url()
    # testcontainers returns postgresql://... (or psycopg2 driver)
    # Normalize to plain postgresql:// for asyncpg
    return url.replace("postgresql+psycopg2://", "postgresql://")


@pytest_asyncio.fixture(scope="session")
async def pool(dsn):
    """Create an asyncpg connection pool against the test database.

    Applies the migration SQL once at pool creation time.
    """
    # Apply migrations
    conn = await asyncpg.connect(dsn)
    try:
        migration_sql = MIGRATION_SQL.read_text()
        await conn.execute(migration_sql)
        migration_002_sql = MIGRATION_002_SQL.read_text()
        await conn.execute(migration_002_sql)
        migration_003_sql = MIGRATION_003_SQL.read_text()
        await conn.execute(migration_003_sql)
    finally:
        await conn.close()

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def db_conn(pool):
    """Provide a fresh database connection for each test, with cleanup."""
    async with pool.acquire() as conn:
        yield conn


@pytest_asyncio.fixture
async def clean_db(pool):
    """Truncate all tables before each test for isolation."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM answers")
        await conn.execute("DELETE FROM chunks")
        await conn.execute("DELETE FROM documents")
    yield pool
