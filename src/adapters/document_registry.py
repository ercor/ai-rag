"""Document registry adapter — tracks ingested documents for dedup.

Provides CRUD operations against the `documents` table and a pure-function
diff algorithm for detecting new, changed, renamed, and deleted files.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime

import asyncpg

from src.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentRecord:
    """A row in the documents table."""

    id: str
    source_path: str
    title: str
    content_hash: str
    content_type: str
    chunk_count: int
    created_at: datetime
    modified_at: datetime
    indexed_at: datetime


@dataclass(frozen=True)
class RenameMatch:
    """A detected rename: same content hash, different path."""

    old_path: str
    new_path: str
    record: DocumentRecord


@dataclass
class DiffResult:
    """Result of comparing scan results against the registry."""

    new: list[dict] = field(default_factory=list)
    changed: list[dict] = field(default_factory=list)
    unchanged: list[dict] = field(default_factory=list)
    renamed: list[RenameMatch] = field(default_factory=list)
    deleted: list[DocumentRecord] = field(default_factory=list)


def document_id(path: str) -> str:
    """Generate a stable document ID from the file path."""
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


class DocumentRegistry:
    """CRUD for the documents table + diff logic for dedup.

    Implements the persistence side of content-hash-based deduplication.
    """

    def __init__(self, database_url: str | None = None):
        settings = get_settings()
        self.dsn = (database_url or settings.database_url).replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=3)
        return self._pool

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def load_all(self) -> dict[str, DocumentRecord]:
        """Load all documents from the registry, keyed by source_path."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM documents")
        return {
            row["source_path"]: DocumentRecord(
                id=row["id"],
                source_path=row["source_path"],
                title=row["title"],
                content_hash=row["content_hash"],
                content_type=row["content_type"],
                chunk_count=row["chunk_count"],
                created_at=row["created_at"],
                modified_at=row["modified_at"],
                indexed_at=row["indexed_at"],
            )
            for row in rows
        }

    async def upsert(self, record: DocumentRecord) -> None:
        """Insert or update a document record."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents
                    (id, source_path, title, content_hash, content_type,
                     chunk_count, created_at, modified_at, indexed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (id) DO UPDATE SET
                    source_path = EXCLUDED.source_path,
                    title = EXCLUDED.title,
                    content_hash = EXCLUDED.content_hash,
                    content_type = EXCLUDED.content_type,
                    chunk_count = EXCLUDED.chunk_count,
                    modified_at = EXCLUDED.modified_at,
                    indexed_at = EXCLUDED.indexed_at
                """,
                record.id,
                record.source_path,
                record.title,
                record.content_hash,
                record.content_type,
                record.chunk_count,
                record.created_at,
                record.modified_at,
                record.indexed_at,
            )

    async def delete(self, doc_id: str) -> None:
        """Delete a document record by ID."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM documents WHERE id = $1", doc_id)

    async def update_path(self, doc_id: str, new_path: str) -> None:
        """Update the source_path for a document (rename detection)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE documents SET source_path = $2, modified_at = now() WHERE id = $1",
                doc_id,
                new_path,
            )

    @staticmethod
    def compute_diff(
        scan_results: list[dict],
        registry: dict[str, DocumentRecord],
    ) -> DiffResult:
        """Compare scan results against registry to detect changes.

        Algorithm:
        1. Build hash→path maps for both scan and registry
        2. Detect renames: hash in both, path differs, one-to-one matching
        3. After rename pass, classify remaining as new/changed/unchanged/deleted
        """
        diff = DiffResult()

        # Build lookup maps
        scan_by_path = {r["path"]: r for r in scan_results}
        scan_paths = set(scan_by_path.keys())
        registry_paths = set(registry.keys())

        # Build hash→path for scan (only paths not already in registry)
        # and hash→record for registry (only records whose path is not in scan)
        scan_hash_to_path: dict[str, list[str]] = {}
        for path in scan_paths - registry_paths:
            h = scan_by_path[path]["content_hash"]
            scan_hash_to_path.setdefault(h, []).append(path)

        reg_hash_to_record: dict[str, list[DocumentRecord]] = {}
        for path in registry_paths - scan_paths:
            rec = registry[path]
            reg_hash_to_record.setdefault(rec.content_hash, []).append(rec)

        # Detect renames: one-to-one hash match between disappeared and appeared paths
        renamed_old_paths: set[str] = set()
        renamed_new_paths: set[str] = set()

        for hash_val, reg_records in reg_hash_to_record.items():
            if hash_val in scan_hash_to_path:
                scan_paths_for_hash = scan_hash_to_path[hash_val]
                # Only unambiguous one-to-one matches
                if len(reg_records) == 1 and len(scan_paths_for_hash) == 1:
                    old_rec = reg_records[0]
                    new_path = scan_paths_for_hash[0]
                    diff.renamed.append(
                        RenameMatch(
                            old_path=old_rec.source_path,
                            new_path=new_path,
                            record=old_rec,
                        )
                    )
                    renamed_old_paths.add(old_rec.source_path)
                    renamed_new_paths.add(new_path)

        # After rename pass, classify remaining paths
        active_registry = {
            p: r for p, r in registry.items() if p not in renamed_old_paths
        }
        active_scan = {
            p: r for p, r in scan_by_path.items() if p not in renamed_new_paths
        }

        for path, scan_item in active_scan.items():
            if path not in active_registry:
                diff.new.append(scan_item)
            elif active_registry[path].content_hash != scan_item["content_hash"]:
                diff.changed.append(scan_item)
            else:
                diff.unchanged.append(scan_item)

        for path, record in active_registry.items():
            if path not in active_scan:
                diff.deleted.append(record)

        return diff
