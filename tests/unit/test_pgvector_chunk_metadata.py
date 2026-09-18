"""Unit tests for pgvector chunk metadata handling.

Tests:
- _row_to_chunk handles NULL page_number → None
- _row_to_chunk handles NULL anchor → None
- _row_to_chunk handles actual values
- upsert_chunks includes page_number and anchor in INSERT
"""

from unittest.mock import AsyncMock, MagicMock

from src.adapters.pgvector_index import _row_to_chunk
from src.ports.models import Chunk


class TestRowToChunkMetadata:
    """Test _row_to_chunk handles new nullable columns."""

    def test_null_page_number_returns_none(self):
        """NULL page_number → None."""
        row = {
            "document_id": "doc1",
            "document_title": "Test",
            "source_path": "/test.md",
            "section_path": "",
            "chunk_index": 0,
            "content": "content",
            "token_count": 1,
            "content_hash": "abc123",
            "page_number": None,
            "anchor": None,
        }
        chunk = _row_to_chunk(row)
        assert chunk.page_number is None
        assert chunk.anchor is None

    def test_actual_page_number_returns_int(self):
        """Non-NULL page_number → int."""
        row = {
            "document_id": "doc1",
            "document_title": "Test",
            "source_path": "/test.pdf",
            "section_path": "Section 1",
            "chunk_index": 0,
            "content": "content",
            "token_count": 1,
            "content_hash": "abc123",
            "page_number": 5,
            "anchor": "section-1",
        }
        chunk = _row_to_chunk(row)
        assert chunk.page_number == 5
        assert chunk.anchor == "section-1"

    def test_missing_columns_default_to_none(self):
        """Rows without new columns (backward compat) → None."""
        row = {
            "document_id": "doc1",
            "document_title": "Test",
            "source_path": "/test.md",
            "section_path": "",
            "chunk_index": 0,
            "content": "content",
            "token_count": 1,
            "content_hash": "abc123",
        }
        chunk = _row_to_chunk(row)
        assert chunk.page_number is None
        assert chunk.anchor is None


class TestUpsertChunksMetadata:
    """Test upsert_chunks includes new columns."""

    async def test_upsert_includes_page_number_and_anchor(self):
        """upsert_chunks INSERT includes page_number and anchor."""
        from src.adapters.pgvector_index import PgvectorIndex

        index = PgvectorIndex(database_url="postgresql://fake:fake@localhost/fake")

        chunk = Chunk(
            document_id="doc1",
            document_title="Test",
            source_path="/test.pdf",
            section_path="Section 1",
            chunk_index=0,
            content="content",
            token_count=1,
            content_hash="abc123",
            page_number=5,
            anchor="section-1",
        )

        # Mock the connection
        mock_conn = AsyncMock()

        # Create a proper async context manager for pool.acquire()
        class FakeAcquire:
            async def __aenter__(self):
                return mock_conn
            async def __aexit__(self, *args):
                pass

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = FakeAcquire()
        index._pool = mock_pool

        await index.upsert_chunks([chunk], [[0.1] * 768])

        # Verify the INSERT was called with page_number and anchor
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        sql = call_args.args[0]
        assert "page_number" in sql
        assert "anchor" in sql
