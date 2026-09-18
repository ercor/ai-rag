# Delta for Document Ingestion

## MODIFIED Requirements

### Requirement: Directory Source Scanning

The system SHALL scan a configured local directory via a shared `IngestionService`, on startup and on `POST /v1/ingest`. The source MUST be read-only. The startup scan MUST run as a background job, not blocking application startup.

(Previously: synchronous blocking scan; pipeline duplicated in api/ingestion.py + main.py)

#### Scenario: Startup scan

- GIVEN 5 documents in watch directory
- WHEN app starts
- THEN background job discovers and queues all 5; app serves requests immediately

#### Scenario: Manual re-scan

- GIVEN 2 new documents added after startup
- WHEN `POST /v1/ingest` called
- THEN job created (see `ingestion-job-tracking`); 2 new docs processed

#### Scenario: Idempotent re-scan

- GIVEN all documents already ingested
- WHEN `POST /v1/ingest` called again
- THEN no duplicate chunks (unchanged files skipped via `document-registry`)

### Requirement: Multi-Format Parsing

The system SHALL parse PDF, DOCX, HTML, TXT, MD via `Parser` port, returning `ParsedDocument` block model (headings, paragraphs, lists, tables, page markers). Blocking parsers MUST run via `asyncio.to_thread`. Unsupported formats MUST be logged and skipped.

(Previously: parsers returned flat str; blocked event loop; lost PDF pages; dropped DOCX tables)

#### Scenario: Supported format parsed

- GIVEN a PDF file
- WHEN ingestion runs
- THEN parser returns `ParsedDocument` with page markers preserved

#### Scenario: Unsupported format skipped

- GIVEN a `.xlsx` file
- WHEN ingestion runs
- THEN logged as unsupported and skipped; others proceed

#### Scenario: Corrupt file handling

- GIVEN a zero-byte PDF
- WHEN ingestion runs
- THEN parse failure logged; document marked failed; others proceed

#### Scenario: Parser in thread

- GIVEN a blocking parser library
- WHEN ingestion runs
- THEN executes via `asyncio.to_thread`; event loop not blocked

### Requirement: Heading-Aware Chunking

The system SHALL split `ParsedDocument` blocks into chunks using per-source-type config via env vars (`CHUNK_MIN_{TYPE}`, `CHUNK_MAX_{TYPE}`, `CHUNK_OVERLAP_{TYPE}`). Chunks MUST preserve heading context, MAY include `page`/`anchor` metadata. MUST NOT split inside list items or table rows.

(Previously: single global 300–600 tokens, 10% overlap; no per-type config; no page/anchor; no boundary awareness)

#### Scenario: Normal document chunked

- GIVEN a 2000-token markdown document with 3 sections
- WHEN chunking runs
- THEN chunks produced per markdown config, each prefixed with section path

#### Scenario: Short document

- GIVEN a 100-token document
- WHEN chunking runs
- THEN a single chunk with full content

#### Scenario: Chunk metadata

- GIVEN a chunk from a PDF
- WHEN inspected
- THEN contains `document_id`, `section_path`, `token_count`, `chunk_index`, `content`, optionally `page`/`anchor`

#### Scenario: List not split mid-item

- GIVEN a 50-item markdown list
- WHEN chunking runs
- THEN items not split mid-item across chunk boundaries

## ADDED Requirements

### Requirement: Shared Ingestion Service with Bounded Concurrency

The system SHALL provide a single `IngestionService` used by both API and startup scan (no duplication). Processing MUST be bounded by semaphore: default 2 docs in flight, configurable via `INGEST_CONCURRENCY`.

#### Scenario: Single pipeline, bounded

- GIVEN 10 docs, concurrency = 2, either entry point triggers
- WHEN ingestion runs
- THEN same pipeline used; at most 2 docs processed simultaneously

### Requirement: Batched Embedding

The system SHALL batch: up to 64 texts per `/api/embed` call. Configurable via `EMBED_BATCH_SIZE`.

#### Scenario: Batching

- GIVEN 20 chunks → single call; 100 chunks → two calls (64 + 36)

### Requirement: Stale Chunk Cleanup

The system SHALL delete displaced chunks on document re-process and all chunks on document removal.

#### Scenario: Changed document

- GIVEN a document with 10 chunks re-processed into 8
- WHEN new chunks indexed
- THEN old 10 deleted; new 8 inserted

#### Scenario: Removed document

- GIVEN a document with 5 chunks no longer on disk
- WHEN scan detects deletion
- THEN all 5 chunks deleted

## REMOVED Requirements

### Requirement: Ingestion Status Reporting

(Reason: Replaced by `ingestion-job-tracking` — async job API with `GET /v1/ingest/{job_id}`)
(Migration: `POST /v1/ingest` → 202 + `job_id`; poll via `GET /v1/ingest/{job_id}`)
