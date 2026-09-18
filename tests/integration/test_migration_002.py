"""Integration tests for migration 002 — documents table.

Verifies the documents table exists with all required columns,
source_path UNIQUE constraint, and content_hash index.
"""

import pytest


@pytest.mark.integration
class TestMigration002:
    async def test_documents_table_exists(self, pool):
        """The documents table is created by migration 002."""
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'documents'
                )
                """
            )
        assert exists is True

    async def test_documents_table_has_all_columns(self, pool):
        """All required columns exist with correct types."""
        async with pool.acquire() as conn:
            columns = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'documents'
                ORDER BY ordinal_position
                """
            )
        col_map = {row["column_name"]: row for row in columns}

        expected = {
            "id": "text",
            "source_path": "text",
            "title": "text",
            "content_hash": "text",
            "content_type": "text",
            "chunk_count": "integer",
            "created_at": "timestamp with time zone",
            "modified_at": "timestamp with time zone",
            "indexed_at": "timestamp with time zone",
        }
        for col_name, expected_type in expected.items():
            assert col_name in col_map, f"Missing column: {col_name}"
            assert col_map[col_name]["data_type"] == expected_type, (
                f"Column {col_name}: expected type '{expected_type}', "
                f"got '{col_map[col_name]['data_type']}'"
            )

    async def test_source_path_is_unique(self, pool):
        """source_path has a UNIQUE constraint."""
        async with pool.acquire() as conn:
            # Insert a row
            await conn.execute(
                """
                INSERT INTO documents (id, source_path, title, content_hash, content_type)
                VALUES ('test1', '/unique/path.md', 'Test', 'hash1', '.md')
                """
            )
            # Attempt duplicate source_path should fail
            with pytest.raises(Exception) as exc_info:
                await conn.execute(
                    """
                    INSERT INTO documents (id, source_path, title, content_hash, content_type)
                    VALUES ('test2', '/unique/path.md', 'Test2', 'hash2', '.md')
                    """
                )
            err_msg = str(exc_info.value).lower()
            assert "unique" in err_msg or "duplicate" in err_msg

            # Cleanup
            await conn.execute("DELETE FROM documents WHERE id IN ('test1', 'test2')")

    async def test_content_hash_is_indexed(self, pool):
        """An index exists on content_hash column."""
        async with pool.acquire() as conn:
            indexes = await conn.fetch(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'documents'
                """
            )
        hash_indexes = [
            idx for idx in indexes
            if "content_hash" in idx["indexdef"]
        ]
        assert len(hash_indexes) >= 1, (
            f"No index found on content_hash. Existing indexes: "
            f"{[idx['indexname'] for idx in indexes]}"
        )
