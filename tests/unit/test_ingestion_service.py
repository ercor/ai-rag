"""Unit tests for IngestionService.

Tests the full pipeline with mock ports:
- skip-unchanged (hash match → no parse/chunk/embed calls)
- new file (full pipeline)
- changed file (delete old chunks + re-process)
- deleted file (delete chunks + registry delete)
- renamed file (update_path, no re-process)
- per-file failure handling
"""

import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.adapters.document_registry import DocumentRecord, DocumentRegistry
from src.core.ingestion_service import IngestionService


def _doc_id(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def _make_record(path: str, content_hash: str, chunk_count: int = 3) -> DocumentRecord:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return DocumentRecord(
        id=_doc_id(path),
        source_path=path,
        title="Test",
        content_hash=content_hash,
        content_type=".md",
        chunk_count=chunk_count,
        created_at=now,
        modified_at=now,
        indexed_at=now,
    )


def _scan_item(path: str, content_hash: str, title: str = "t", size: int = 10) -> dict:
    return {
        "path": path,
        "title": title,
        "extension": ".md",
        "content_hash": content_hash,
        "size": size,
    }


def _make_mocks():
    """Create mock port instances for IngestionService."""
    source = AsyncMock()
    parser = AsyncMock()
    chunker = MagicMock()
    embedder = AsyncMock()
    search_index = AsyncMock()
    registry = AsyncMock(spec=DocumentRegistry)
    return source, parser, chunker, embedder, search_index, registry


def _make_chunk(content: str = "chunk content"):
    from src.ports.models import Chunk

    return Chunk(
        document_id="doc1",
        document_title="Test",
        source_path="/docs/test.md",
        section_path="",
        chunk_index=0,
        content=content,
        token_count=2,
        content_hash="chunkhash",
    )


def _make_parsed_doc():
    """Create a ParsedDocument for mocking parser returns."""
    from src.ports.models import Paragraph, ParsedDocument

    return ParsedDocument(
        blocks=[Paragraph(text="Some text content")],
        metadata={"title": "Test", "source_path": "/docs/test.md", "content_type": ".md"},
    )


class TestIngestionServiceSkipUnchanged:
    async def test_skip_unchanged_files(self):
        """Files with matching hash → no parse/chunk/embed calls."""
        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = [_scan_item("/docs/a.md", "hash_a")]
        registry.load_all.return_value = {
            "/docs/a.md": _make_record("/docs/a.md", "hash_a"),
        }

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        assert result.skipped == 1
        assert result.processed == 0
        parser.parse.assert_not_called()
        chunker.split.assert_not_called()
        embedder.embed_batch.assert_not_called()

    async def test_all_unchanged_returns_zero_processed(self):
        """5 unchanged files → skipped=5, processed=0."""
        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        scan_results = [_scan_item(f"/docs/{n}.md", f"h{n}") for n in range(5)]
        source.scan.return_value = scan_results
        registry.load_all.return_value = {
            f"/docs/{n}.md": _make_record(f"/docs/{n}.md", f"h{n}")
            for n in range(5)
        }

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        assert result.skipped == 5
        assert result.processed == 0
        assert result.chunks == 0


class TestIngestionServiceNewFile:
    async def test_new_file_full_pipeline(self):
        """New file → parse → chunk → embed → upsert → registry upsert."""
        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = [_scan_item("/docs/new.md", "hash_new", size=100)]
        registry.load_all.return_value = {}

        chunk = _make_chunk()
        parser.parse.return_value = _make_parsed_doc()
        chunker.split.return_value = [chunk]
        embedder.embed_batch.return_value = [[0.1] * 768]

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        assert result.processed == 1
        assert result.chunks == 1
        parser.parse.assert_called_once_with("/docs/new.md")
        chunker.split.assert_called_once()
        embedder.embed_batch.assert_called_once()
        search_index.upsert_chunks.assert_called_once()
        registry.upsert.assert_called_once()


class TestIngestionServiceChangedFile:
    async def test_changed_file_deletes_old_chunks(self):
        """Changed file → delete old chunks → re-process → upsert new."""
        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = [_scan_item("/docs/a.md", "hash_new", size=100)]
        registry.load_all.return_value = {
            "/docs/a.md": _make_record("/docs/a.md", "hash_old"),
        }

        chunk = _make_chunk()
        parser.parse.return_value = _make_parsed_doc()
        chunker.split.return_value = [chunk]
        embedder.embed_batch.return_value = [[0.1] * 768]
        search_index.delete_chunks.return_value = 3

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        assert result.processed == 1
        search_index.delete_chunks.assert_called_once_with(_doc_id("/docs/a.md"))
        search_index.upsert_chunks.assert_called_once()
        registry.upsert.assert_called_once()


class TestIngestionServiceDeletedFile:
    async def test_deleted_file_cleanup(self):
        """Deleted file → delete chunks + registry delete."""
        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = []
        old_record = _make_record("/docs/gone.md", "hash_gone", chunk_count=5)
        registry.load_all.return_value = {"/docs/gone.md": old_record}
        search_index.delete_chunks.return_value = 5

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        search_index.delete_chunks.assert_called_once_with(old_record.id)
        registry.delete.assert_called_once_with(old_record.id)
        parser.parse.assert_not_called()
        assert result.processed == 0


class TestIngestionServiceRenamedFile:
    async def test_rename_updates_path_no_reprocess(self):
        """Renamed file → update_path, no parse/chunk/embed."""
        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = [
            _scan_item("/docs/new_name.md", "hash_r", title="new_name", size=50),
        ]
        registry.load_all.return_value = {
            "/docs/old_name.md": _make_record("/docs/old_name.md", "hash_r"),
        }

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        registry.update_path.assert_called_once()
        parser.parse.assert_not_called()
        chunker.split.assert_not_called()
        embedder.embed_batch.assert_not_called()
        search_index.delete_chunks.assert_not_called()
        assert result.processed == 0
        assert result.skipped == 0


class TestIngestionServiceFailureHandling:
    async def test_per_file_failure_continues(self):
        """One file fails → recorded in failures, processing continues."""
        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = [
            _scan_item("/docs/good.md", "hash_g"),
            _scan_item("/docs/bad.md", "hash_b"),
        ]
        registry.load_all.return_value = {}

        chunk = _make_chunk()
        parser.parse.side_effect = [Exception("Parse error"), _make_parsed_doc()]
        chunker.split.return_value = [chunk]
        embedder.embed_batch.return_value = [[0.1] * 768]

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        assert result.failed == 1
        assert result.processed == 1
        assert len(result.failures) == 1
        failed_path = result.failures[0]["path"]
        assert failed_path in ("/docs/good.md", "/docs/bad.md")

    async def test_empty_content_counted_as_failure(self):
        """File that parses to empty blocks → counted as failure."""
        from src.ports.models import ParsedDocument

        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = [_scan_item("/docs/empty.md", "hash_e")]
        registry.load_all.return_value = {}
        parser.parse.return_value = ParsedDocument(blocks=[], metadata={})

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        assert result.failed == 1
        assert result.processed == 0
        chunker.split.assert_not_called()


class TestIngestionServiceEmptyScan:
    async def test_empty_scan_returns_zeros(self):
        """No files found → all zeros result."""
        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = []
        registry.load_all.return_value = {}

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        assert result.processed == 0
        assert result.skipped == 0
        assert result.chunks == 0
        assert result.failed == 0


class TestIngestionServiceSemaphore:
    async def test_semaphore_bounds_concurrency(self):
        """At most N docs processed concurrently (N from config)."""
        import asyncio

        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        # 5 files to process
        source.scan.return_value = [
            _scan_item(f"/docs/file{i}.md", f"hash{i}") for i in range(5)
        ]
        registry.load_all.return_value = {}

        chunk = _make_chunk()
        parser.parse.return_value = _make_parsed_doc()
        chunker.split.return_value = [chunk]
        embedder.embed_batch.return_value = [[0.1] * 768]

        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0

        async def slow_parse(path):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)  # Simulate slow parsing
            concurrent_count -= 1
            return _make_parsed_doc()

        parser.parse.side_effect = slow_parse

        # Create service with concurrency=2
        service = IngestionService(
            source, parser, chunker, embedder, search_index, registry,
            ingest_concurrency=2,
        )
        await service.run()

        # Should never exceed 2 concurrent
        assert max_concurrent <= 2

    async def test_semaphore_default_concurrency(self):
        """Default concurrency is 2."""
        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = [_scan_item("/docs/a.md", "hash_a")]
        registry.load_all.return_value = {}

        chunk = _make_chunk()
        parser.parse.return_value = _make_parsed_doc()
        chunker.split.return_value = [chunk]
        embedder.embed_batch.return_value = [[0.1] * 768]

        # No ingest_concurrency specified → default 2
        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        result = await service.run()

        assert result.processed == 1


class TestIngestionServiceProgress:
    async def test_progress_callback_receives_updates(self):
        """Progress callback receives atomic counter updates."""
        from src.core.job_registry import JobState

        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = [
            _scan_item("/docs/a.md", "hash_a"),
            _scan_item("/docs/b.md", "hash_b"),
        ]
        registry.load_all.return_value = {}

        chunk = _make_chunk()
        parser.parse.return_value = _make_parsed_doc()
        chunker.split.return_value = [chunk]
        embedder.embed_batch.return_value = [[0.1] * 768]

        # Create a JobState to track progress
        job = JobState(job_id="test-job", state="running", total=2)

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        await service.run(progress=job)

        # Job should be updated with final counts
        assert job.processed == 2
        assert job.chunks == 2

    async def test_progress_tracks_skipped(self):
        """Progress callback tracks skipped files."""
        from src.core.job_registry import JobState

        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        # 2 unchanged files
        source.scan.return_value = [
            _scan_item("/docs/a.md", "hash_a"),
            _scan_item("/docs/b.md", "hash_b"),
        ]
        registry.load_all.return_value = {
            "/docs/a.md": _make_record("/docs/a.md", "hash_a"),
            "/docs/b.md": _make_record("/docs/b.md", "hash_b"),
        }

        job = JobState(job_id="test-job", state="running", total=2)

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        await service.run(progress=job)

        assert job.skipped == 2
        assert job.processed == 0

    async def test_progress_tracks_failures(self):
        """Progress callback tracks failed files."""
        from src.core.job_registry import JobState

        source, parser, chunker, embedder, search_index, registry = _make_mocks()

        source.scan.return_value = [
            _scan_item("/docs/good.md", "hash_g"),
            _scan_item("/docs/bad.md", "hash_b"),
        ]
        registry.load_all.return_value = {}

        chunk = _make_chunk()
        parser.parse.side_effect = [_make_parsed_doc(), Exception("Parse error")]
        chunker.split.return_value = [chunk]
        embedder.embed_batch.return_value = [[0.1] * 768]

        job = JobState(job_id="test-job", state="running", total=2)

        service = IngestionService(source, parser, chunker, embedder, search_index, registry)
        await service.run(progress=job)

        assert job.processed == 1
        assert job.failed == 1
        assert len(job.failures) == 1
