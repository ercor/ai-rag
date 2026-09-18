"""IngestionService — consolidated ingestion pipeline.

Replaces the duplicated pipeline logic in api/ingestion.py and main.py.
Orchestrates: scan → diff → parse → chunk → embed → upsert with dedup.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.adapters.document_registry import DocumentRecord, DocumentRegistry, document_id
from src.ports.chunker import Chunker
from src.ports.document_source import DocumentSource
from src.ports.embedder import Embedder
from src.ports.parser import Parser
from src.ports.search_index import SearchIndex

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Summary of an ingestion run."""

    processed: int = 0
    skipped: int = 0
    chunks: int = 0
    failed: int = 0
    failures: list[dict] = field(default_factory=list)


class IngestionService:
    """Consolidated ingestion pipeline with document registry dedup.

    Takes all port dependencies via constructor (hexagonal pattern).
    """

    def __init__(
        self,
        source: DocumentSource,
        parser: Parser,
        chunker: Chunker,
        embedder: Embedder,
        search_index: SearchIndex,
        registry: DocumentRegistry,
        ingest_concurrency: int = 2,
    ):
        self.source = source
        self.parser = parser
        self.chunker = chunker
        self.embedder = embedder
        self.search_index = search_index
        self.registry = registry
        self.ingest_concurrency = ingest_concurrency

    async def run(self, progress: object | None = None) -> IngestionResult:
        """Full pipeline: scan → diff → parse → chunk → embed → upsert.

        Args:
            progress: optional JobState for live counter updates.

        Returns:
            IngestionResult with counts of processed, skipped, chunks, failed.
        """
        result = IngestionResult()

        # Step 1: Scan for documents
        scan_results = await self.source.scan()

        # Step 2: Load registry and compute diff
        registry_records = await self.registry.load_all()
        diff = DocumentRegistry.compute_diff(scan_results, registry_records)

        logger.info(
            "Ingestion diff: new=%d, changed=%d, unchanged=%d, renamed=%d, deleted=%d",
            len(diff.new),
            len(diff.changed),
            len(diff.unchanged),
            len(diff.renamed),
            len(diff.deleted),
        )

        result.skipped = len(diff.unchanged)

        # Update progress with total and skipped
        if progress is not None:
            progress.total = len(scan_results)
            progress.skipped = result.skipped

        # Step 3: Handle renames (update path, no re-processing)
        for rename in diff.renamed:
            try:
                await self.registry.update_path(rename.record.id, rename.new_path)
                logger.info(
                    "Renamed: %s → %s (chunks preserved)",
                    rename.old_path,
                    rename.new_path,
                )
            except Exception as exc:
                logger.error("Failed to update path for rename %s: %s", rename.old_path, exc)
                result.failed += 1
                result.failures.append({"path": rename.old_path, "error": str(exc)})
                if progress is not None:
                    progress.failed = result.failed
                    progress.failures = result.failures.copy()

        # Step 4: Handle deletions (delete chunks + registry row)
        for record in diff.deleted:
            try:
                await self.search_index.delete_chunks(record.id)
                await self.registry.delete(record.id)
                logger.info(
                    "Deleted: %s (%d chunks removed)",
                    record.source_path,
                    record.chunk_count,
                )
            except Exception as exc:
                logger.error("Failed to delete %s: %s", record.source_path, exc)
                result.failed += 1
                result.failures.append({"path": record.source_path, "error": str(exc)})
                if progress is not None:
                    progress.failed = result.failed
                    progress.failures = result.failures.copy()

        # Step 5: Process new and changed files with bounded concurrency
        to_process = diff.new + diff.changed
        is_changed = {item["path"] for item in diff.changed}

        semaphore = asyncio.Semaphore(self.ingest_concurrency)

        async def process_file(file_meta: dict) -> None:
            """Process a single file under semaphore control."""
            async with semaphore:
                path = file_meta["path"]
                title = file_meta["title"]
                doc_id = document_id(path)

                try:
                    # For changed files, delete old chunks first
                    if path in is_changed:
                        await self.search_index.delete_chunks(doc_id)

                    # Parse → ParsedDocument
                    parsed_doc = await self.parser.parse(path)
                    if not parsed_doc or not parsed_doc.blocks:
                        logger.warning("Empty content after parsing: %s", path)
                        result.failed += 1
                        result.failures.append(
                            {"path": path, "error": "Empty content after parsing"}
                        )
                        if progress is not None:
                            progress.failed = result.failed
                            progress.failures = result.failures.copy()
                        return

                    # Determine source type from file extension
                    source_type = file_meta.get("extension", "")

                    # Chunk with block-aware chunker
                    chunks = self.chunker.split(
                        parsed_doc, doc_id, title, path, source_type
                    )
                    if not chunks:
                        logger.warning("No chunks produced for: %s", path)
                        result.failed += 1
                        result.failures.append({"path": path, "error": "No chunks produced"})
                        if progress is not None:
                            progress.failed = result.failed
                            progress.failures = result.failures.copy()
                        return

                    # Embed
                    texts = [c.content for c in chunks]
                    embeddings = await self.embedder.embed_batch(texts)

                    # Upsert chunks
                    await self.search_index.upsert_chunks(chunks, embeddings)

                    # Upsert registry record
                    now = datetime.now(timezone.utc)
                    record = DocumentRecord(
                        id=doc_id,
                        source_path=path,
                        title=title,
                        content_hash=file_meta["content_hash"],
                        content_type=file_meta.get("extension", ""),
                        chunk_count=len(chunks),
                        created_at=now,
                        modified_at=now,
                        indexed_at=now,
                    )
                    await self.registry.upsert(record)

                    result.processed += 1
                    result.chunks += len(chunks)

                    # Update progress
                    if progress is not None:
                        progress.processed = result.processed
                        progress.chunks = result.chunks

                    logger.info("Ingested %s: %d chunks", path, len(chunks))

                except Exception as exc:
                    logger.error("Failed to process %s: %s", path, exc, exc_info=True)
                    result.failed += 1
                    result.failures.append({"path": path, "error": str(exc)})
                    if progress is not None:
                        progress.failed = result.failed
                        progress.failures = result.failures.copy()

        # Process all files concurrently (bounded by semaphore)
        if to_process:
            await asyncio.gather(*(process_file(f) for f in to_process))

        return result
