# Document Ingestion Specification

## Purpose

Define the document ingestion pipeline: scanning a local directory, parsing supported file formats, and splitting documents into heading-aware chunks ready for embedding.

## Requirements

### Requirement: Directory Source Scanning

The system SHALL scan a configured local directory for documents on startup and on manual trigger (`POST /v1/ingest`).

The source MUST be read-only — ingestion MUST NOT modify, move, or delete source files.

#### Scenario: Startup scan

- GIVEN the watched directory contains 5 documents
- WHEN the application starts
- THEN all 5 documents are discovered and queued for parsing

#### Scenario: Manual re-scan

- GIVEN 2 new documents are added to the directory after startup
- WHEN `POST /v1/ingest` is called
- THEN only the 2 new documents are parsed and stored

#### Scenario: Idempotent re-scan

- GIVEN all documents are already ingested
- WHEN `POST /v1/ingest` is called again
- THEN no duplicate chunks are created

### Requirement: Multi-Format Parsing

The system SHALL parse PDF, DOCX, HTML, TXT, and MD files via the `Parser` port.

Each parser MUST extract text content. Unsupported formats MUST be logged and skipped without failing the batch.

#### Scenario: Supported format parsed

- GIVEN a PDF file in the source directory
- WHEN ingestion runs
- THEN the parser extracts text content from the PDF

#### Scenario: Unsupported format skipped

- GIVEN a `.xlsx` file in the source directory
- WHEN ingestion runs
- THEN the file is logged as unsupported and skipped; other files are still processed

#### Scenario: Corrupt file handling

- GIVEN a zero-byte PDF file
- WHEN ingestion runs
- THEN the parse failure is logged; the document is marked as failed; other documents proceed

### Requirement: Heading-Aware Chunking

The system SHALL split parsed documents into chunks of 300–600 tokens with 10% overlap, prepending the section path (heading hierarchy) to each chunk.

Chunks MUST preserve heading context so retriever can filter/rank by section.

#### Scenario: Normal document chunked

- GIVEN a 2000-token markdown document with 3 sections
- WHEN chunking runs
- THEN 4–7 chunks are produced, each 300–600 tokens, each prefixed with its section path

#### Scenario: Short document

- GIVEN a 100-token document
- WHEN chunking runs
- THEN a single chunk is produced containing the full content

#### Scenario: Chunk metadata

- GIVEN a chunk is produced
- WHEN inspected
- THEN it contains: `document_id`, `section_path`, `token_count`, `chunk_index`, `content`

### Requirement: Ingestion Status Reporting

The system SHALL return ingestion results including counts of documents processed, chunks created, and failures.

#### Scenario: Status response

- GIVEN ingestion processes 10 docs, creates 45 chunks, 1 fails
- WHEN the ingestion endpoint responds
- THEN response includes `{"processed": 10, "chunks": 45, "failed": 1, "failures": [...]}`
