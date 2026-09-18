"""Integration tests for DocumentRegistry CRUD against testcontainers.

Verifies upsert, load_all, delete, update_path against a real PostgreSQL
instance with migration 002 applied.
"""

from datetime import datetime, timezone

import pytest

from src.adapters.document_registry import DocumentRecord, DocumentRegistry, document_id


def _make_record(
    source_path: str,
    content_hash: str,
    title: str = "Test Doc",
    content_type: str = ".md",
    chunk_count: int = 3,
) -> DocumentRecord:
    doc_id = document_id(source_path)
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return DocumentRecord(
        id=doc_id,
        source_path=source_path,
        title=title,
        content_hash=content_hash,
        content_type=content_type,
        chunk_count=chunk_count,
        created_at=now,
        modified_at=now,
        indexed_at=now,
    )


@pytest.mark.integration
class TestDocumentRegistryCRUD:
    async def test_upsert_and_load_all(self, clean_db, dsn):
        """Upsert a record, then load_all returns it."""
        registry = DocumentRegistry(database_url=dsn)
        record = _make_record("/docs/test.md", "abc123")

        await registry.upsert(record)
        loaded = await registry.load_all()

        assert "/docs/test.md" in loaded
        assert loaded["/docs/test.md"].content_hash == "abc123"
        assert loaded["/docs/test.md"].title == "Test Doc"
        assert loaded["/docs/test.md"].chunk_count == 3
        await registry.close()

    async def test_upsert_updates_existing(self, clean_db, dsn):
        """Upserting same ID updates the record."""
        registry = DocumentRegistry(database_url=dsn)
        record = _make_record("/docs/test.md", "hash_v1")
        await registry.upsert(record)

        updated = _make_record("/docs/test.md", "hash_v2", chunk_count=5)
        await registry.upsert(updated)

        loaded = await registry.load_all()
        assert loaded["/docs/test.md"].content_hash == "hash_v2"
        assert loaded["/docs/test.md"].chunk_count == 5
        await registry.close()

    async def test_delete_removes_record(self, clean_db, dsn):
        """Delete removes the record from the registry."""
        registry = DocumentRegistry(database_url=dsn)
        record = _make_record("/docs/gone.md", "hash_gone")
        await registry.upsert(record)

        await registry.delete(record.id)
        loaded = await registry.load_all()

        assert "/docs/gone.md" not in loaded
        await registry.close()

    async def test_update_path_changes_source_path(self, clean_db, dsn):
        """update_path changes the source_path for a document."""
        registry = DocumentRegistry(database_url=dsn)
        record = _make_record("/docs/old.md", "hash_xyz")
        await registry.upsert(record)

        await registry.update_path(record.id, "/docs/new.md")
        loaded = await registry.load_all()

        assert "/docs/old.md" not in loaded
        assert "/docs/new.md" in loaded
        assert loaded["/docs/new.md"].content_hash == "hash_xyz"
        assert loaded["/docs/new.md"].id == record.id
        await registry.close()

    async def test_source_path_unique_constraint(self, clean_db, dsn):
        """Inserting two records with same source_path but different IDs fails."""
        registry = DocumentRegistry(database_url=dsn)
        rec1 = _make_record("/docs/unique.md", "hash_1")
        await registry.upsert(rec1)

        # Create a record with different ID but same source_path
        rec2 = DocumentRecord(
            id="different_id",
            source_path="/docs/unique.md",
            title="Other",
            content_hash="hash_2",
            content_type=".md",
            chunk_count=1,
            created_at=rec1.created_at,
            modified_at=rec1.modified_at,
            indexed_at=rec1.indexed_at,
        )
        with pytest.raises(Exception):
            await registry.upsert(rec2)
        await registry.close()

    async def test_load_all_empty_registry(self, clean_db, dsn):
        """Empty registry returns empty dict."""
        registry = DocumentRegistry(database_url=dsn)
        loaded = await registry.load_all()
        assert loaded == {}
        await registry.close()
