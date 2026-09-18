"""Integration test for migration 003 — chunk metadata columns.

Verifies that the chunks table has nullable page_number (INT) and
anchor (TEXT) columns, and that existing rows have NULL for new columns.
"""

import pytest


@pytest.mark.integration
class TestMigration003:
    """Verify migration 003 adds page_number and anchor columns."""

    async def test_chunks_table_has_page_number_column(self, pool):
        """chunks table has nullable page_number INT column."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'chunks' AND column_name = 'page_number'
                """
            )
        assert len(rows) == 1
        assert rows[0]["data_type"] == "integer"
        assert rows[0]["is_nullable"] == "YES"

    async def test_chunks_table_has_anchor_column(self, pool):
        """chunks table has nullable anchor TEXT column."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'chunks' AND column_name = 'anchor'
                """
            )
        assert len(rows) == 1
        assert rows[0]["data_type"] == "text"
        assert rows[0]["is_nullable"] == "YES"

    async def test_existing_rows_have_null_for_new_columns(self, clean_db):
        """Existing chunk rows have NULL for page_number and anchor."""
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chunks (
                    document_id, document_title, source_path,
                    chunk_index, content, content_hash
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                "doc1",
                "Test",
                "/test.md",
                0,
                "content",
                "hash123",
            )
            row = await conn.fetchrow(
                "SELECT page_number, anchor FROM chunks WHERE document_id = $1",
                "doc1",
            )
        assert row["page_number"] is None
        assert row["anchor"] is None

    async def test_can_insert_with_page_number_and_anchor(self, clean_db):
        """New chunks can store page_number and anchor values."""
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chunks (
                    document_id, document_title, source_path,
                    chunk_index, content, content_hash,
                    page_number, anchor
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                "doc2",
                "PDF Doc",
                "/test.pdf",
                0,
                "content",
                "hash456",
                5,
                "section-2",
            )
            row = await conn.fetchrow(
                "SELECT page_number, anchor FROM chunks WHERE document_id = $1",
                "doc2",
            )
        assert row["page_number"] == 5
        assert row["anchor"] == "section-2"
