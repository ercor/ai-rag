"""Integration tests for the full ingestion pipeline.

Uses testcontainers PostgreSQL to verify:
- Idempotency: second run skips all files
- Stale cleanup: modified file → old chunks gone, new chunks present
- Deletion: removed file → chunks gone, registry row gone
"""

import hashlib
import math
import random
from pathlib import Path

import pytest

from src.adapters.document_registry import DocumentRegistry, document_id
from src.adapters.pgvector_index import PgvectorIndex
from src.core.ingestion_service import IngestionService


def _fake_embedding(dim=768, seed=42):
    """Generate a deterministic unit-length fake embedding vector."""
    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec]


class FakeSource:
    """In-memory document source for testing."""

    def __init__(self, files: dict[str, str]):
        self._files = files

    def set_files(self, files: dict[str, str]):
        self._files = files

    async def scan(self) -> list[dict]:
        results = []
        for path, content in self._files.items():
            content_bytes = content.encode("utf-8")
            results.append({
                "path": path,
                "title": Path(path).stem,
                "extension": Path(path).suffix,
                "content_hash": hashlib.sha256(content_bytes).hexdigest(),
                "size": len(content_bytes),
            })
        return results


class FakeParser:
    """Returns the file content as-is (path → content lookup)."""

    def __init__(self, contents: dict[str, str]):
        self._contents = contents

    def set_contents(self, contents: dict[str, str]):
        self._contents = contents

    async def parse(self, path: str) -> str:
        return self._contents.get(path, "")


class FakeChunker:
    """Produces one chunk per file with deterministic content."""

    def split(self, text: str, doc_id: str, doc_title: str, source: str):
        from src.ports.models import Chunk

        if not text or not text.strip():
            return []
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return [
            Chunk(
                document_id=doc_id,
                document_title=doc_title,
                source_path=source,
                section_path="",
                chunk_index=0,
                content=text[:200],
                token_count=len(text.split()),
                content_hash=content_hash,
            )
        ]


class FakeEmbedder:
    """Returns deterministic fake embeddings."""

    _counter = 0

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        for _ in texts:
            FakeEmbedder._counter += 1
            results.append(_fake_embedding(seed=FakeEmbedder._counter))
        return results


@pytest.mark.integration
class TestIngestionPipeline:
    async def test_idempotent_second_run_skips_all(self, clean_db, dsn, tmp_path):
        """Second run with no changes → all files skipped."""
        # Setup
        files = {"/docs/a.md": "Content A", "/docs/b.md": "Content B"}
        source = FakeSource(files)
        parser = FakeParser(files)
        chunker = FakeChunker()
        embedder = FakeEmbedder()
        search_index = PgvectorIndex(database_url=dsn)
        registry = DocumentRegistry(database_url=dsn)

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)

        # First run: process both files
        result1 = await service.run()
        assert result1.processed == 2
        assert result1.skipped == 0
        assert result1.chunks == 2

        # Second run: all should be skipped
        result2 = await service.run()
        assert result2.processed == 0
        assert result2.skipped == 2
        assert result2.chunks == 0

        await search_index.close()
        await registry.close()

    async def test_modified_file_stale_cleanup(self, clean_db, dsn, tmp_path):
        """Modified file → old chunks deleted, new chunks inserted."""
        files = {"/docs/doc.md": "Original content"}
        source = FakeSource(files)
        parser = FakeParser(files)
        chunker = FakeChunker()
        embedder = FakeEmbedder()
        search_index = PgvectorIndex(database_url=dsn)
        registry = DocumentRegistry(database_url=dsn)

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)

        # First run
        result1 = await service.run()
        assert result1.processed == 1

        # Modify the file
        files["/docs/doc.md"] = "Updated content that is different"
        source.set_files(files)
        parser.set_contents(files)

        # Second run: should re-process
        result2 = await service.run()
        assert result2.processed == 1
        assert result2.chunks == 1

        # Verify only one chunk exists (old one replaced)
        async with search_index._pool.acquire() as conn:
            doc_id = document_id("/docs/doc.md")
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM chunks WHERE document_id = $1", doc_id
            )
        assert count == 1

        await search_index.close()
        await registry.close()

    async def test_deleted_file_cleanup(self, clean_db, dsn, tmp_path):
        """Removed file → chunks deleted, registry row removed."""
        files = {"/docs/keep.md": "Keep me", "/docs/remove.md": "Remove me"}
        source = FakeSource(files)
        parser = FakeParser(files)
        chunker = FakeChunker()
        embedder = FakeEmbedder()
        search_index = PgvectorIndex(database_url=dsn)
        registry = DocumentRegistry(database_url=dsn)

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)

        # First run: ingest both
        result1 = await service.run()
        assert result1.processed == 2

        # Remove one file
        del files["/docs/remove.md"]
        source.set_files(files)
        parser.set_contents(files)

        # Second run: should detect deletion
        result2 = await service.run()
        assert result2.skipped == 1  # keep.md unchanged

        # Verify removed file's chunks are gone
        async with search_index._pool.acquire() as conn:
            removed_doc_id = document_id("/docs/remove.md")
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM chunks WHERE document_id = $1", removed_doc_id
            )
        assert count == 0

        # Verify registry row is gone
        loaded = await registry.load_all()
        assert "/docs/remove.md" not in loaded
        assert "/docs/keep.md" in loaded

        await search_index.close()
        await registry.close()

    async def test_new_file_added(self, clean_db, dsn, tmp_path):
        """New file added → processed and registered."""
        files = {"/docs/first.md": "First content"}
        source = FakeSource(files)
        parser = FakeParser(files)
        chunker = FakeChunker()
        embedder = FakeEmbedder()
        search_index = PgvectorIndex(database_url=dsn)
        registry = DocumentRegistry(database_url=dsn)

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)

        # First run
        await service.run()

        # Add new file
        files["/docs/second.md"] = "Second content"
        source.set_files(files)
        parser.set_contents(files)

        # Second run
        result = await service.run()
        assert result.processed == 1
        assert result.skipped == 1

        loaded = await registry.load_all()
        assert "/docs/second.md" in loaded

        await search_index.close()
        await registry.close()
