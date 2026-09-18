# Document Registry Specification

## Purpose

Content-hash-based document registry enabling skip-unchanged optimization, rename detection, deletion cleanup, and change detection. Deduplication is for reprocessing efficiency, not content removal.

## Requirements

### Requirement: Documents Table

The system SHALL maintain a `documents` table created by migration 002.

| Column | Type | Constraint |
|--------|------|------------|
| id | TEXT | PK (document_id = hash of source_path) |
| source_path | TEXT | UNIQUE NOT NULL |
| title | TEXT | NOT NULL |
| content_hash | TEXT | NOT NULL (SHA-256 hex of file bytes) |
| content_type | TEXT | NOT NULL (MIME or extension) |
| chunk_count | INT | NOT NULL DEFAULT 0 |
| created_at | TIMESTAMPTZ | NOT NULL |
| modified_at | TIMESTAMPTZ | NOT NULL |
| indexed_at | TIMESTAMPTZ | NOT NULL |

#### Scenario: Migration creates table

- GIVEN migration 002 is applied
- WHEN the table is queried
- THEN all columns exist with `source_path` UNIQUE and `content_hash` indexed

### Requirement: Content Hash Computation

The system MUST compute SHA-256 of each file's bytes during scan, before any parsing.

#### Scenario: Hash computed for new file

- GIVEN a file in the watch directory
- WHEN a scan runs
- THEN SHA-256 of file bytes is computed and compared against the registry

### Requirement: Skip Unchanged Files

The system SHALL skip parse/chunk/embed for files whose content hash matches the registry.

#### Scenario: Re-scan with no changes

- GIVEN 5 files in registry with matching hashes
- WHEN a scan runs
- THEN all 5 are skipped; no parse/chunk/embed work performed
- AND job progress reports `skipped: 5`

### Requirement: Detect Changed Files

The system SHALL detect files whose hash differs from the registry. Changed files MUST be re-processed; old chunks MUST be deleted before new chunks are inserted.

#### Scenario: File content modified

- GIVEN a file registered with hash `abc123`
- WHEN the file is modified (hash now `def456`) and scan runs
- THEN the file is re-parsed, re-chunked, re-embedded
- AND old chunks are deleted, new chunks inserted
- AND registry row updated with new hash and `indexed_at`

### Requirement: Detect New Files

The system SHALL detect files on disk absent from the registry. New files MUST be fully processed and a registry row inserted.

#### Scenario: New file added

- GIVEN a file not in the registry
- WHEN a scan runs
- THEN file is parsed, chunked, embedded, indexed
- AND registry row created

### Requirement: Detect Renamed Files

The system SHOULD detect renames: content hash exists in registry but with a different source path. On rename, update `source_path` and preserve chunks (no re-processing).

#### Scenario: File renamed, content unchanged

- GIVEN file at `/docs/old.md` with hash `xyz`
- WHEN file moves to `/docs/new.md` (same bytes) and scan runs
- THEN registry `source_path` updated to `/docs/new.md`
- AND existing chunks preserved without re-embedding

#### Scenario: Ambiguous rename

- GIVEN 2 files removed and 2 new files with matching hashes
- WHEN scan runs
- THEN system MAY treat as delete+insert instead of renames

### Requirement: Detect Deleted Files

The system SHALL detect registry files missing from disk. Deleted files MUST have chunks removed and registry row deleted (FR-03).

#### Scenario: File removed from disk

- GIVEN a registry file no longer on disk
- WHEN scan runs
- THEN all its chunks are deleted from the index
- AND registry row is removed

### Requirement: Duplicate Content Across Files

The system SHALL ingest files with identical content as distinct documents when both are new (not a rename). Dedup is reprocessing efficiency, not content removal.

#### Scenario: Two new files, identical content

- GIVEN `/docs/a.md` and `/docs/b.md` with identical bytes, both new
- WHEN scan runs
- THEN both ingested as separate documents with separate chunks

## Dependencies

- `migrations/002_documents.sql`
- `document-ingestion` (pipeline uses registry for skip/change decisions)
